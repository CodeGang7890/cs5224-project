"""Telling the customer how their payment went, on WhatsApp.

Sent after the payment is committed (app/payments.py). 
Nothing is sent if the customer has no phone number or it is a dummy customer.
The invoice link is added when there is one.

Pub/Sub can deliver an event twice, and a repeated event sends the message again.
A customer who gets a message twice is better off than one who never gets it.

Free-form WhatsApp text only works within 24 hours of the customer's last message. Past that Meta
refuses it (SendError, not retryable): it's logged, and the payment still stands. Sending later
needs an approved message template.
"""

import logging

from . import whatsapp_sender
from .invoice import BOOKING, Invoice, money
from .models import PAYMENT_RECEIVED

logger = logging.getLogger(__name__)


def message_text(invoice: Invoice, new_status: str, invoice_link: str | None = None) -> str:
    """The message for a payment that was received or failed."""
    what = 'booking' if invoice.kind == BOOKING else 'order'
    if new_status == PAYMENT_RECEIVED:
        text = (
            f'Hi {invoice.customer_name}, we received your payment of {money(invoice.total, invoice.currency)} '
            f'for your {what} ({invoice.number}). Thank you!'
        )
        if invoice_link:
            text += f'\n\nYour invoice: {invoice_link}'
        return text
    return (
        f"Hi {invoice.customer_name}, your payment for your {what} ({invoice.number}) didn't go through, "
        f'so the {what} was not confirmed. Please try it again if you still want it. Thank you!'
    )


def notify_customer(business_id: int, invoice: Invoice, new_status: str, invoice_link: str | None = None) -> bool:
    """Sends the message. Returns whether it was sent. Raises SendError only when trying again could
    help (so the payment event is redelivered); a refusal is logged and returns False."""
    if not invoice.customer_phone:
        logger.info('%s: no phone number to tell (a sandbox chat, or the chat was deleted)', invoice.number)
        return False
    try:
        whatsapp_sender.send_text(business_id, invoice.customer_phone, message_text(invoice, new_status, invoice_link))
    except whatsapp_sender.SendError as exc:
        if exc.retryable:
            raise
        logger.error('%s: could not tell the customer: %s', invoice.number, exc)
        return False
    logger.info('%s: told the customer (%s)', invoice.number, new_status)
    return True
