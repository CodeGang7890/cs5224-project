"""Changing an order's / booking's status: complete_order() / complete_booking(), the business marks
a paid one as completed. Orders and bookings are placed by messaging-service's chat flow (its
port of the former place_order / place_booking), and their payments are applied by
processing-service."""

from django.db import transaction

from .models import OrderItem, OrderStatus, ScheduleItem


class StatusChangeError(Exception):
    """The order / booking can't move to the status asked for (a sentence for the business)."""


def _status_label(status: str) -> str:
    return OrderStatus(status).label.lower() if status in OrderStatus.values else status


def complete_order(order_id: int) -> OrderItem:
    """Marks a paid order as completed: payment received → order completed (its products move from
    on hold to sold). Any other status raises StatusChangeError. The row is locked, so two clicks
    at once can't both pass the check."""
    with transaction.atomic():
        order = OrderItem.objects.select_for_update().get(pk=order_id)
        if order.order_status != OrderStatus.PAYMENT_RECEIVED:
            raise StatusChangeError(
                f'Only orders with payment received can be marked as completed (this one is '
                f'{_status_label(order.order_status)}).'
            )
        order.order_status = OrderStatus.ORDER_COMPLETED
        order.save(update_fields=['order_status', 'updated_time'])
    return order


def complete_booking(booking_id: int) -> ScheduleItem:
    """Marks a paid booking as completed: payment received → order completed (its time stays
    booked, X). Any other status raises StatusChangeError. Saved with save(), so the signals keep
    the provider's week in step."""
    with transaction.atomic():
        booking = ScheduleItem.objects.select_for_update().get(pk=booking_id)
        if booking.order_status != OrderStatus.PAYMENT_RECEIVED:
            raise StatusChangeError(
                f'Only bookings with payment received can be marked as completed (this one is '
                f'{_status_label(booking.order_status)}).'
            )
        booking.order_status = OrderStatus.ORDER_COMPLETED
        booking.save(update_fields=['order_status', 'updated_time'])
    return booking
