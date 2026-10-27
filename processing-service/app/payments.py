"""
The payment flow: what a payment event does to the order or booking it's for.

For one event `{payment_reference, status, amount?}`, in one transaction:
1. Find the product order (OrderItem) or booking (ScheduleItem) with that payment reference, and
   lock its row; none → PaymentNotFoundError.
2. Check the amount against the order's / booking's total: a successful payment must carry the
   exact total; a failed payment's amount (when present) must match it too. A mismatch → an error
   that is acked (redelivering it would never help).
3. Update its status: success → payment_received, fail → payment_failed. Only a pending payment
   changes; the same event again (Pub/Sub delivers at least once) changes nothing; anything else
   (e.g. a completed or already failed order) → PaymentStatusConflictError (a failed payment is
   final: no retry).
4. What else changes:
   - a product order: nothing stored. configuration-service derives each product's on hold /
     sold / available quantities from the orders' statuses (checkout_app.stock): payment_received
     still holds the quantities (sold once completed), payment_failed holds nothing, so they're
     available again.
   - a booking: its provider's weekly availabilities are stored letters, written by Django
     signals that don't run here, so schedule.py paints them: paid → X (taken), failed → O (free).
5. For a payment that was received: the invoice (app/invoice.py) is rendered and
   uploaded (app/storage.py). It also runs for a repeated event, so if the upload failed (the
   consumer nacks, Pub/Sub redelivers) the retry makes the invoice. The object name is fixed, so
   doing it twice just overwrites it.
6. The customer is told (app/notifications.py): on WhatsApp for received and failed payments, with the
   invoice link when there is one; by email for received ones, with the invoice PDF attached. One
   channel failing doesn't stop the other. A message that couldn't be sent but could be later raises,
   so the event is redelivered and a refusal is only logged.
"""

import logging
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import invoice, notifications, schedule, storage
from .models import PAYMENT_FAILED, PAYMENT_RECEIVED, PENDING_PAYMENT, OrderItem, ScheduleItem

logger = logging.getLogger(__name__)

SUCCESS, FAIL = 'success', 'fail'
STATUS_AFTER = {SUCCESS: PAYMENT_RECEIVED, FAIL: PAYMENT_FAILED}
TWO_DECIMALS = Decimal('0.01')


class PaymentEventError(Exception):
    """The event can't be applied. Redelivering it wouldn't help, so the consumer acks it."""


class PaymentNotFoundError(PaymentEventError):
    """No order or booking has this payment reference."""


class PaymentStatusConflictError(PaymentEventError):
    """The order / booking isn't waiting for this payment (e.g. already completed, or failed)."""


@dataclass(frozen=True)
class PaymentResult:
    kind: str  # 'order' or 'booking'
    id: int
    old_status: str
    new_status: str
    invoice_uri: str | None = None  # gs:// of the uploaded invoice (payment received, with a bucket)
    invoice_link: str | None = None  # a link for the customer to open it

    @property
    def changed(self) -> bool:
        return self.old_status != self.new_status


def find_item(session: Session, payment_reference: str) -> OrderItem | ScheduleItem:
    """The order or booking with this payment reference, its row locked until the commit."""
    for model in (OrderItem, ScheduleItem):
        item = session.scalars(
            select(model).where(model.payment_reference == payment_reference).with_for_update()
        ).first()
        if item is not None:
            return item
    raise PaymentNotFoundError(f'No order or booking has payment reference {payment_reference}')


def finish(session: Session, result: PaymentResult) -> PaymentResult:
    """Makes and uploads the invoice, then tells the customer (WhatsApp, and email with the PDF attached)."""
    item = session.get(OrderItem if result.kind == 'order' else ScheduleItem, result.id)
    document = invoice.build_invoice(session, item)
    business_id = item.business_id
    session.rollback()  # no connection held during the upload and the message
    pdf = None
    if result.new_status == PAYMENT_RECEIVED:
        pdf = invoice.render_pdf(document)
        name = invoice.object_name(document.payment_reference)
        uri = storage.upload_invoice(pdf, name)
        result = replace(result, invoice_uri=uri, invoice_link=storage.invoice_link(name) if uri else None)
    notifications.notify_customer(business_id, document, result.new_status, result.invoice_link, pdf)
    return result


def _amount(value: float | None) -> Decimal | None:
    """The event's amount as a Decimal. `str` first, so 3.60 is not 3.59999…."""
    return None if value is None else Decimal(str(value))


def apply_payment(session: Session, payment_reference: str, status: str, amount: float | None = None) -> PaymentResult:
    """Applies one payment event and commits it, then makes the invoice and tells the customer."""
    with session.begin():
        item = find_item(session, payment_reference)
        kind = 'order' if isinstance(item, OrderItem) else 'booking'
        expected = invoice.build_invoice(session, item).total
        paid = _amount(amount)
        if paid is None:
            if status == SUCCESS:
                raise PaymentEventError(f'Payment {payment_reference}: a successful payment must carry its amount')
        elif paid != expected:
            raise PaymentEventError(f'Payment {payment_reference}: amount {paid} does not match the {kind} total {expected}')
        new_status = STATUS_AFTER[status]
        result = PaymentResult(kind, item.id, item.order_status, new_status)
        if item.order_status == new_status:
            logger.info('Payment %s: %s #%s is already %s (a repeated event)', payment_reference, kind, item.id, new_status)
        elif item.order_status != PENDING_PAYMENT:
            # A failed payment is final: there is no retry by design.
            raise PaymentStatusConflictError(
                f'Payment {payment_reference} ({status}): {kind} #{item.id} is {item.order_status}, not {PENDING_PAYMENT}'
            )
        else:
            item.order_status = new_status
            item.updated_time = datetime.now(UTC)  # Django's auto_now, which doesn't run here
            if isinstance(item, ScheduleItem):
                if new_status == PAYMENT_RECEIVED:
                    schedule.mark_booked(session, item)  # H → X: the time is taken
                else:
                    schedule.release(session, item)  # H → O: the time is free again
            # A product order needs nothing else: its stock follows from order_status (module docstring).
    # From `result`: the committed item's attributes are expired, and reading them would reload it.
    logger.info('Payment %s: %s #%s %s → %s', payment_reference, kind, result.id, result.old_status, new_status)

    return finish(session, result)
