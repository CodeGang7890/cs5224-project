"""Xendit webhook handler: verify the callback token, extract the payment result, publish it.

Xendit signs each webhook by sending the configured webhook token in the ``x-callback-token``
header (dashboard: Settings > Webhooks). We compare it with ``XENDIT_WEBHOOK_SECRET``; an empty
secret rejects every webhook, so it must be set before testing with Xendit.

The events we act on:
- ``payment_session.completed``: the hosted payment link was paid → ``success``.
- ``payment_session.expired``: the link expired unpaid → ``fail``.
- ``payment.failure`` (Payment v3, optional): a payment attempt failed → ``fail``.
- ``payment.capture`` / ``payment.succeeded`` (Payment v3, optional): the payment succeeded.
"""

import hmac
import logging
from typing import Any

from . import config

logger = logging.getLogger(__name__)


class WebhookVerificationError(ValueError):
    """The webhook's callback token is missing or wrong."""


class InvalidWebhookError(ValueError):
    """The webhook payload is invalid or not an event we act on."""


SUCCESS_EVENTS = {'payment_session.completed', 'payment.capture', 'payment.succeeded'}
FAILURE_EVENTS = {'payment_session.expired', 'payment.failure'}
SUCCESS_STATUSES = {None, 'COMPLETED', 'SUCCEEDED'}
FAILURE_STATUSES = {None, 'EXPIRED', 'FAILED', 'CANCELED'}


def verify_signature(token: str | None) -> bool:
    """True when the ``x-callback-token`` header is the configured webhook token."""
    if not config.XENDIT_WEBHOOK_SECRET:
        logger.warning('XENDIT_WEBHOOK_SECRET is not set; rejecting the webhook')
        return False
    if not token:
        logger.warning('Missing Xendit x-callback-token header')
        return False
    if not hmac.compare_digest(config.XENDIT_WEBHOOK_SECRET, token):
        logger.warning('Invalid Xendit x-callback-token')
        return False
    return True


def _amount(*values: Any) -> float | None:
    """The first usable amount among the given values (Xendit sends a number, or a string)."""
    for value in values:
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str) and value.strip():
            try:
                return float(value)
            except ValueError:
                continue
    return None


def parse_webhook(payload: dict[str, Any]) -> dict[str, Any]:
    """Parse a Xendit webhook payload and extract the payment result.

    Both the Payment Session webhooks and the Payment v3 webhooks carry our reference as
    ``data.reference_id`` (the legacy ``reference`` / ``external_reference`` names are accepted
    too). The amount is ``data.amount`` (sessions) or ``data.request_amount`` (payments).
    """
    event = payload.get('event') or payload.get('event_type')
    if event not in SUCCESS_EVENTS | FAILURE_EVENTS:
        logger.debug('Ignoring webhook event: %s', event)
        raise InvalidWebhookError(f'Unsupported event: {event}')

    data = payload.get('data', {})
    if not isinstance(data, dict):
        raise InvalidWebhookError('Missing or invalid data field')

    reference = data.get('reference_id') or data.get('reference') or data.get('external_reference')
    if not reference:
        raise InvalidWebhookError('Missing payment reference')

    status = data.get('status')
    if event in SUCCESS_EVENTS:
        if status not in SUCCESS_STATUSES:
            raise InvalidWebhookError(f'Unexpected status for {event}: {status}')
        mapped_status = 'success'
    else:
        if status not in FAILURE_STATUSES:
            raise InvalidWebhookError(f'Unexpected status for {event}: {status}')
        mapped_status = 'fail'

    return {
        'payment_reference': reference,
        'status': mapped_status,
        'xendit_payment_id': data.get('payment_id') or data.get('payment_session_id') or data.get('id'),
        'amount': _amount(data.get('amount'), data.get('request_amount')),
        'currency': data.get('currency'),
        'event_id': payload.get('id') or payload.get('event_id'),
    }


def create_webhook_response() -> dict[str, str]:
    """Create success response for Xendit webhook."""
    return {'status': 'success', 'message': 'Webhook received'}
