"""Client for payment-ingester's create-payment endpoint (POST /payments).

The chat flow calls it right after an order / booking is saved: payment-ingester creates the
Xendit payment (link) with its secret key and returns Xendit's payment id and the link. The
customer pays on Xendit's hosted page; the result comes back through Xendit's webhook
(payment-ingester → Pub/Sub → processing-service), not through this call.
"""

import logging

import httpx

from . import config

logger = logging.getLogger(__name__)


class PaymentClientError(Exception):
    """payment-ingester is unreachable, or refused / failed to create the payment."""


def create_payment(
    kind: str,
    item_id: int,
    amount,
    payment_reference: str,
    customer: dict[str, str],
    description: str | None = None,
    expiry_minutes: int | None = None,
) -> dict[str, str]:
    """Create the Xendit payment (link) for the placed order / booking.

    `customer`: `given_name` and `email` (from the chat's details). Returns
    `{'xendit_payment_id', 'payment_url'}`; raises `PaymentClientError` on any failure (the
    caller degrades gracefully: the confirmation message carries a note instead of a link).
    """
    body = {
        'kind': kind,
        'item_id': item_id,
        'amount': float(amount),
        'payment_reference': payment_reference,
        'customer': {'given_name': customer['given_name'], 'email': customer['email']},
    }
    if expiry_minutes is not None:
        body['expiry_minutes'] = expiry_minutes
    if description:
        body['description'] = description

    try:
        response = httpx.post(
            f'{config.PAYMENT_INGESTER_URL}/payments',
            json=body,
            headers={'X-Internal-Api-Key': config.INTERNAL_API_KEY},
            timeout=config.PAYMENT_CREATE_TIMEOUT_SECONDS,
        )
    except httpx.HTTPError as exc:
        logger.error('payment-ingester is unreachable: %s', exc)
        raise PaymentClientError(f'payment-ingester is unreachable: {exc}') from exc

    if response.status_code >= 400:
        try:
            detail = response.json().get('detail', '')
        except ValueError:
            detail = response.text[:300]
        logger.error('payment-ingester answered %s: %s', response.status_code, detail)
        raise PaymentClientError(f'payment-ingester answered {response.status_code}: {detail}')

    try:
        data = response.json()
        return {'xendit_payment_id': data['xendit_payment_id'], 'payment_url': data['payment_url']}
    except (ValueError, KeyError) as exc:
        logger.error('Unexpected answer from payment-ingester: %s', response.text[:300])
        raise PaymentClientError(f'Unexpected answer from payment-ingester: {response.text[:300]}') from exc
