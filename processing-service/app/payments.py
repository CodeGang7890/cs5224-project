"""The payment flow: what a payment event does to the order or booking it's for.

A draft (the user asked; to be filled in). For one event `{payment_reference, status}`, in one
transaction:
1. Find the product order (OrderItem) or booking (ScheduleItem) with that payment reference, and
   lock its row; none → PaymentNotFoundError.
2. Update its status: success → payment_received, fail → payment_failed. Only a pending payment
   changes; the same event again (Pub/Sub delivers at least once) changes nothing; anything else
   (e.g. a completed order) → PaymentStatusConflictError.
3. What else changes:
   - a product order: nothing stored. configuration-service derives each product's on hold /
     sold / available quantities from the orders' statuses (checkout_app.stock): payment_received
     still holds the quantities (sold once completed), payment_failed holds nothing, so they're
     available again.
   - a booking: its provider's weekly availabilities are stored letters, written by Django
     signals that don't run here, so schedule.py paints them: paid → X (taken), failed → O (free).
4. TODO: the invoice; TODO: tell the customer (after the commit).
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import schedule
from .models import PAYMENT_FAILED, PAYMENT_RECEIVED, PENDING_PAYMENT, OrderItem, ScheduleItem

logger = logging.getLogger(__name__)

SUCCESS, FAIL = 'success', 'fail'
STATUS_AFTER = {SUCCESS: PAYMENT_RECEIVED, FAIL: PAYMENT_FAILED}


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


def apply_payment(session: Session, payment_reference: str, status: str) -> PaymentResult:
    """Applies one payment event and commits it (see the module docstring)."""
    with session.begin():
        item = find_item(session, payment_reference)
        kind = 'order' if isinstance(item, OrderItem) else 'booking'
        new_status = STATUS_AFTER[status]
        result = PaymentResult(kind, item.id, item.order_status, new_status)
        if item.order_status == new_status:
            logger.info('Payment %s: %s #%s is already %s (a repeated event)', payment_reference, kind, item.id, new_status)
            return result
        if item.order_status != PENDING_PAYMENT:
            # TODO: e.g. a successful retry after a failed payment: re-hold the stock / time if it's still free.
            raise PaymentStatusConflictError(
                f'Payment {payment_reference} ({status}): {kind} #{item.id} is {item.order_status}, not {PENDING_PAYMENT}'
            )

        item.order_status = new_status
        item.updated_time = datetime.now(UTC)  # Django's auto_now, which doesn't run here
        if isinstance(item, ScheduleItem):
            if new_status == PAYMENT_RECEIVED:
                schedule.mark_booked(session, item)  # H → X: the time is taken
            else:
                schedule.release(session, item)  # H → O: the time is free again
        # A product order needs nothing else: its stock follows from order_status (module docstring).

        if new_status == PAYMENT_RECEIVED:
            # TODO: generate the invoice (PDF) and upload it to object storage (Google Cloud Storage).
            pass
    # From `result`: the committed item's attributes are expired, and reading them would reload it.
    logger.info('Payment %s: %s #%s %s → %s', payment_reference, kind, result.id, result.old_status, new_status)

    # TODO: tell the customer the outcome (and send the invoice link) through the WhatsApp API or the
    # Gmail API. After the commit, so a failed message doesn't undo the payment.
    return result
