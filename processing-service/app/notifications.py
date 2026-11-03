"""Telling the customer how their payment went: on WhatsApp, and by email when the payment was received.

Sent after the payment is committed (app/payments.py). Each channel is skipped when the customer
has no way to be reached on it:
- WhatsApp: needs a phone number. Says whether the payment was received or failed, with the invoice link when there is one.
- Email: needs an `email` detail from the chat, and EMAIL_ENABLED (app/config.py). Only for a received
  payment, with the invoice PDF attached (so no link is needed).

Pub/Sub can deliver an event twice, and a repeated event sends the message again.
A customer who gets a message twice is better off than one who never gets it.

Free-form WhatsApp text only works within 24 hours of the customer's last message. Past that Meta
refuses it (SendError, not retryable): it's logged, and the payment still stands. Sending later
needs an approved message template.
"""

import logging

from . import email_sender, whatsapp_sender
from .invoice import BOOKING, Invoice, local, money
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


def message_customer(business_id: int, invoice: Invoice, new_status: str, invoice_link: str | None = None) -> bool:
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


def email_subject_and_text(invoice: Invoice) -> tuple[str, str]:
    """The email for a received payment"""
    what = 'booking' if invoice.kind == BOOKING else 'order'
    subject = f'Payment received: your {what} with {invoice.business_name}'
    lines = [
        f'Hi {invoice.customer_name},',
        '',
        f'Thank you! {invoice.business_name} has received your payment of {money(invoice.total, invoice.currency)} '
        f'for your {what}.',
    ]
    if invoice.booking:
        booking = invoice.booking
        start, end = local(booking.start), local(booking.end)
        with_whom = f' with {booking.provider}' if booking.provider else ''
        lines += ['', f'Your booking: {booking.service}{with_whom}, {start:%A, %d %B %Y}, {start:%H:%M} to {end:%H:%M}.']
    lines += [
        '',
        f'Your invoice ({invoice.number}) is attached to this email as a PDF. Please keep it for your records.',
        '',
        f'If anything looks wrong, just message {invoice.business_name} in your WhatsApp chat.',
        '',
        'Thank you,',
        invoice.business_name,
    ]
    return subject, '\n'.join(lines)


def email_customer(invoice: Invoice, new_status: str, invoice_pdf: bytes | None) -> bool:
    """Emails the invoice for a received payment. Returns whether it was sent or not."""
    if new_status != PAYMENT_RECEIVED or not invoice_pdf:
        return False
    if not invoice.customer_email:
        logger.info('%s: no email address to send the invoice to', invoice.number)
        return False
    subject, text = email_subject_and_text(invoice)
    attachment = email_sender.Attachment(f'{invoice.number}.pdf', invoice_pdf)
    try:
        sent = email_sender.send_email(subject, text, invoice.customer_email, attachments=[attachment])
    except email_sender.EmailError as exc:
        if exc.retryable:
            raise
        logger.error('%s: could not email the customer: %s', invoice.number, exc)
        return False
    if sent:
        logger.info('%s: emailed the invoice to the customer', invoice.number)
    return sent


def notify_customer(
    business_id: int, invoice: Invoice, new_status: str, invoice_link: str | None = None, invoice_pdf: bytes | None = None
) -> None:
    """Tells the customer on WhatsApp and by email."""
    retry = None
    for send in (
        lambda: message_customer(business_id, invoice, new_status, invoice_link),
        lambda: email_customer(invoice, new_status, invoice_pdf),
    ):
        try:
            send()
        except (whatsapp_sender.SendError, email_sender.EmailError) as exc:
            logger.warning('%s: a message could not be sent yet: %s', invoice.number, exc)
            retry = retry or exc
    if retry:
        raise retry
