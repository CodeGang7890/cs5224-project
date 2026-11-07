"""Xendit Payment Sessions API client: creates the hosted payment link the customer pays on.

The customer never enters card details on our platform: we create a Payment Session
(``POST /sessions`` with ``mode: PAYMENT_LINK``) using Xendit's secret key and send the
``payment_link_url`` to the customer (in the chat). The customer pays on Xendit's hosted page;
Xendit then tells us the result by webhook (app/xendit_webhook.py).

Xendit API basics (test mode for now; the same endpoints in live mode with live keys):
- Base URL ``https://api.xendit.co``, ``Authorization: Basic base64("<secret_key>:")``.
- Create session: ``POST /sessions`` with ``reference_id`` (our ``payment_reference``), the
  amount, the customer's name and email, and the success / cancel return URLs (HTTPS only).
  The response carries Xendit's ``payment_session_id`` and the ``payment_link_url``.
- Webhooks: Xendit posts events (for us: ``payment_session.completed`` and
  ``payment_session.expired``, plus optionally ``payment.failure``) to our /webhook, with the
  webhook token in the ``x-callback-token`` header.
"""

import base64
import logging
import re
from datetime import UTC, datetime, timedelta

import httpx

from . import config

logger = logging.getLogger(__name__)


class XenditError(Exception):
    """The payment could not be created."""


class XenditApiError(XenditError):
    """Xendit answered and refused (its status code and detail), or the request couldn't be made."""

    def __init__(self, status_code: int, detail: str):
        super().__init__(f'Xendit answered {status_code}: {detail}')
        self.status_code = status_code
        self.detail = detail


class XenditUnavailableError(XenditError):
    """Xendit could not be reached (network / timeout / not configured)."""


def _auth_header() -> str:
    # Xendit's API authenticates with the secret key as the Basic username (empty password).
    token = base64.b64encode(f'{config.XENDIT_SECRET_KEY}:'.encode()).decode()
    return f'Basic {token}'


def _individual_detail(given_name: str) -> dict[str, str]:
    """Xendit's individual detail (alphanumeric only; ``given_names`` is required)."""
    parts = [part for part in re.split(r'[^0-9A-Za-z]+', given_name) if part]
    if not parts:
        return {'given_names': 'Customer'}
    if len(parts) == 1:
        return {'given_names': parts[0]}
    return {'given_names': parts[0], 'surname': ''.join(parts[1:])}


def create_payment(
    amount: float,
    external_reference: str,
    customer: dict[str, str],
    description: str | None = None,
    expiry_minutes: int | None = None,
) -> dict[str, str]:
    """Create the payment session (hosted link) the customer of this order / booking pays on.

    ``external_reference`` is our ``payment_reference`` (Xendit's ``reference_id``): Xendit echoes
    it back in its webhooks, which is how the result is matched to the order / booking.
    ``customer``: ``given_name`` and ``email`` (collected in the chat). Returns
    ``{'xendit_payment_id', 'payment_url'}`` (the session's id and hosted checkout link).
    """
    if not config.XENDIT_SECRET_KEY:
        raise XenditUnavailableError('Xendit is not configured (XENDIT_SECRET_KEY is not set).')
    email = customer['email'].strip()
    if len(email) > 50:
        raise XenditApiError(400, 'The customer email is longer than Xendit\'s 50-character limit.')

    body: dict = {
        'reference_id': external_reference,
        'session_type': 'PAY',
        'mode': 'PAYMENT_LINK',
        'amount': float(amount),
        'currency': config.XENDIT_CURRENCY,
        'country': config.XENDIT_COUNTRY,
        'customer': {
            'type': 'INDIVIDUAL',
            'reference_id': external_reference,
            'email': email,
            'individual_detail': _individual_detail(customer['given_name']),
        },
        'expires_at': (
            datetime.now(UTC) + timedelta(
                seconds=config.XENDIT_SESSION_EXPIRY_SECONDS if expiry_minutes is None else expiry_minutes * 60
            )
        ).strftime('%Y-%m-%dT%H:%M:%SZ'),
    }
    if config.XENDIT_ALLOWED_PAYMENT_CHANNELS:
        body['allowed_payment_channels'] = config.XENDIT_ALLOWED_PAYMENT_CHANNELS
    if description:
        body['description'] = description[:1000]
    # Xendit requires HTTPS return URLs; locally they're left empty (its own result page is used).
    if config.XENDIT_SUCCESS_URL.startswith('https://'):
        body['success_return_url'] = config.XENDIT_SUCCESS_URL
    if config.XENDIT_FAILURE_URL.startswith('https://'):
        body['cancel_return_url'] = config.XENDIT_FAILURE_URL

    try:
        response = httpx.post(
            f'{config.XENDIT_API_BASE_URL}/sessions',
            json=body,
            headers={'Authorization': _auth_header()},
            timeout=config.XENDIT_TIMEOUT_SECONDS,
        )
    except httpx.HTTPError as exc:
        logger.error('Could not reach Xendit: %s', exc)
        raise XenditUnavailableError(f'Could not reach Xendit: {exc}') from exc

    if response.status_code >= 400:
        logger.error('Xendit refused the payment session: %s %s', response.status_code, response.text[:500])
        raise XenditApiError(response.status_code, response.text[:500])

    try:
        data = response.json()
        payment_session_id = data['payment_session_id']
        payment_url = data['payment_link_url']
        if not payment_url:
            raise KeyError('payment_link_url')
        return {'xendit_payment_id': payment_session_id, 'payment_url': payment_url}
    except (ValueError, KeyError, TypeError) as exc:
        logger.error('Unexpected answer from Xendit: %s', response.text[:500])
        raise XenditApiError(response.status_code, f'Unexpected response: {response.text[:500]}') from exc
