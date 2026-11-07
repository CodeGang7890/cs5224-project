"""Telling the customer what is happening with their order / booking, on WhatsApp and by email.

Two different documents (app/documents.py):
- an INVOICE when they place the order / booking (status pending payment): what they ordered, the
  amount to pay and where to pay it. Sent on WhatsApp and by email, with the invoice PDF.
- a RECEIPT once the payment is received: "we received your payment", with the receipt PDF.
A failed payment gets a WhatsApp message only (there is nothing to attach).

Each channel is skipped when the customer has no way to be reached on it.

Pub/Sub can deliver an event twice, and a repeated event sends the message again.
A customer who gets a message twice is better off than one who never gets it.

Free-form WhatsApp text only works within 24 hours of the customer's last message. Past that Meta
refuses it (SendError, not retryable): it's logged, and the payment still stands. Sending later
needs an approved message template.
"""

import logging

from . import email_sender, whatsapp_sender
from .documents import BOOKING, INVOICE, Document, local, money
from .models import PAYMENT_RECEIVED, PENDING_PAYMENT

logger = logging.getLogger(__name__)


def _what(document: Document) -> str:
    return 'booking' if document.kind == BOOKING else 'order'


def _message_us(document: Document) -> str:
    """How the customer can reach the business, for an email: "just message Kopi & Toast on WhatsApp at
    +65 9123 4567", or, when its number isn't known, "just message Kopi & Toast in your WhatsApp chat"."""
    if document.business_whatsapp:
        return f'just message {document.business_name} on WhatsApp at {document.business_whatsapp}'
    return f'just message {document.business_name} in your WhatsApp chat'


def _summary(document: Document) -> str:
    """What was ordered / booked, in one line."""
    if document.booking:
        booking = document.booking
        start, end = local(booking.start), local(booking.end)
        with_whom = f' with {booking.provider}' if booking.provider else ''
        return f'{booking.service}{with_whom}, {start:%A, %d %B %Y}, {start:%H:%M} to {end:%H:%M}'
    shown = [f'{line.quantity} × {line.description}' for line in document.lines[:5]]
    if len(document.lines) > 5:
        shown.append(f'and {len(document.lines) - 5} more')
    return ', '.join(shown)


def invoice_message_text(document: Document, link: str | None = None) -> str:
    """The WhatsApp message with the invoice. `link` is where to open the invoice PDF, if there is one."""
    what = _what(document)
    lines = [
        f'Hi {document.customer_name}, thank you for your {what} with {document.business_name}! '
        f'Here is your invoice {document.number}.',
        '',
        f'{what.capitalize()}: {_summary(document)}',
        f'Amount to pay: {money(document.total, document.currency)}',
    ]
    if document.payment_url:
        lines.append(f'Pay here: {document.payment_url}')
    if link:
        lines.append(f'Invoice (PDF): {link}')
    lines += ['', "We'll send you a receipt once your payment is received."]
    return '\n'.join(lines)


def invoice_email_subject_and_text(document: Document) -> tuple[str, str]:
    """The email with the invoice attached."""
    what = _what(document)
    subject = f'Invoice for your {what} with {document.business_name}: {money(document.total, document.currency)} to pay'
    lines = [
        f'Hi {document.customer_name},',
        '',
        f'Thank you for your {what} with {document.business_name}. '
        f'Your invoice ({document.number}) is attached to this email as a PDF.',
        '',
        f'{what.capitalize()}: {_summary(document)}',
        f'Amount to pay: {money(document.total, document.currency)}',
    ]
    if document.payment_url:
        lines += ['', f'Pay online: {document.payment_url}']
    lines += [
        '',
        "Once we receive your payment, we'll send you a receipt.",
        '',
        f'If anything looks wrong, {_message_us(document)}.',
        '',
        'Thank you,',
        document.business_name,
    ]
    return subject, '\n'.join(lines)


def receipt_message_text(document: Document, link: str | None = None) -> str:
    """The WhatsApp message for a payment that was received. `link` opens the receipt PDF, if there is one."""
    text = (
        f'Hi {document.customer_name}, we received your payment of {money(document.total, document.currency)} '
        f'for your {_what(document)}. Thank you!\n\nYour receipt: {document.number}'
    )
    if link:
        text += f'\nReceipt (PDF): {link}'
    return text


def receipt_email_subject_and_text(document: Document) -> tuple[str, str]:
    """The email for a payment that was received, with the receipt attached."""
    what = _what(document)
    subject = f'Payment received: your {what} with {document.business_name}'
    lines = [
        f'Hi {document.customer_name},',
        '',
        f'Thank you! {document.business_name} has received your payment of {money(document.total, document.currency)} '
        f'for your {what}.',
    ]
    if document.booking:
        lines += ['', f'Your booking: {_summary(document)}.']
    lines += [
        '',
        f'Your receipt ({document.number}) is attached to this email as a PDF. Please keep it for your records.',
        '',
        f'If anything looks wrong, {_message_us(document)}.',
        '',
        'Thank you,',
        document.business_name,
    ]
    return subject, '\n'.join(lines)


def failed_message_text(document: Document) -> str:
    what = _what(document)
    return (
        f"Hi {document.customer_name}, your payment for your {what} ({document.number}) didn't go through, "
        f'so the {what} was not confirmed. Please try it again if you still want it. Thank you!'
    )


def message_text(document: Document, status: str, link: str | None = None) -> str:
    """The WhatsApp message for the order's / booking's status: pending payment (the invoice), payment
    received (the receipt) or anything else (a failed payment)."""
    if status == PENDING_PAYMENT:
        return invoice_message_text(document, link)
    if status == PAYMENT_RECEIVED:
        return receipt_message_text(document, link)
    return failed_message_text(document)


def email_subject_and_text(document: Document) -> tuple[str, str]:
    """The email for the document: the invoice's or the receipt's, by its type."""
    if document.doc_type == INVOICE:
        return invoice_email_subject_and_text(document)
    return receipt_email_subject_and_text(document)


def message_customer(business_id: int, document: Document, status: str, link: str | None = None) -> bool:
    """Sends the WhatsApp message. Returns whether it was sent. Raises SendError only when trying again
    could help (so the event is redelivered). A refusal is logged and returns False."""
    if not document.customer_phone:
        logger.info('%s: no phone number to tell (a sandbox chat, or the chat was deleted)', document.number)
        return False
    try:
        whatsapp_sender.send_text(business_id, document.customer_phone, message_text(document, status, link))
    except whatsapp_sender.SendError as exc:
        if exc.retryable:
            raise
        logger.error('%s: could not tell the customer: %s', document.number, exc)
        return False
    logger.info('%s: told the customer (%s)', document.number, status)
    return True


def email_customer(document: Document, status: str, pdf: bytes | None) -> bool:
    """Emails the document (the invoice for a pending payment, the receipt for a received one) with its
    PDF attached. Returns whether it was sent (False: not applicable, or email is switched off). Raises
    EmailError only when trying again could help; a refusal is logged and returns False."""
    if status not in (PENDING_PAYMENT, PAYMENT_RECEIVED) or not pdf:
        return False
    if not document.customer_email:
        logger.info('%s: no email address to send it to', document.number)
        return False
    subject, text = email_subject_and_text(document)
    attachment = email_sender.Attachment(f'{document.number}.pdf', pdf)
    try:
        sent = email_sender.send_email(subject, text, document.customer_email, attachments=[attachment])
    except email_sender.EmailError as exc:
        if exc.retryable:
            raise
        logger.error('%s: could not email the customer: %s', document.number, exc)
        return False
    if sent:
        logger.info('%s: emailed it to the customer', document.number)
    return sent


def notify_customer(
    business_id: int, document: Document, status: str, link: str | None = None, pdf: bytes | None = None
) -> None:
    """Tells the customer on WhatsApp and by email. One channel failing doesn't stop the other: both are
    tried, then the first failure that could work later is raised, so the event is redelivered (which
    may send the other channel's message again: better twice than never)."""
    retry = None
    for send in (
        lambda: message_customer(business_id, document, status, link),
        lambda: email_customer(document, status, pdf),
    ):
        try:
            send()
        except (whatsapp_sender.SendError, email_sender.EmailError) as exc:
            logger.warning('%s: a message could not be sent yet: %s', document.number, exc)
            retry = retry or exc
    if retry:
        raise retry
