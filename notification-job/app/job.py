"""The notification job, run every hour (cron.sh). Each run:

1. Payment reminders: orders (OrderItem) and bookings (ScheduleItem) still pending payment that
   were made 1 to 2 hours ago, [1 h, 2 h) before the hour (created_time in (hour − 2 h, hour − 1 h]).
2. Appointment reminders: bookings starting 23 to 24 hours from now, [23 h, 24 h) after the hour
   (start_time in [hour + 23 h, hour + 24 h)), unless their payment failed (they hold no time).

"The hour" is the run's time rounded down to the hour (9:11:30 pm → 9 pm), so the windows of
consecutive hourly runs follow each other without gaps or overlaps: each item gets each reminder
once. For now each reminder is only logged (the customer's phone number and a draft message):
sending it (WhatsApp) is a TODO.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app import config
from app.db import get_session
from app.models import PAYMENT_FAILED, PENDING_PAYMENT, OrderItem, ScheduleItem

logger = logging.getLogger(__name__)

PAYMENT_REMINDER_AFTER = (timedelta(hours=1), timedelta(hours=2))  # [1 h, 2 h) after it was made
APPOINTMENT_REMINDER_BEFORE = (timedelta(hours=23), timedelta(hours=24))  # [23 h, 24 h) before it starts


@dataclass(frozen=True)
class Reminder:
    kind: str  # 'payment' or 'appointment'
    item: str  # e.g. 'order #12', 'booking #3'
    phone_number: str | None  # None: no number to send to (a sandbox chat without one, or the chat was deleted)
    message: str


@dataclass(frozen=True)
class RunResult:
    hour: datetime
    payment_reminders: list[Reminder]
    appointment_reminders: list[Reminder]


def floor_to_hour(moment: datetime) -> datetime:
    """`moment` rounded down to the hour, in UTC (9:11:30 pm → 9:00 pm). The schedule time zone's
    offset is whole hours (Asia/Singapore: +8), so that's the same hour there."""
    return moment.astimezone(UTC).replace(minute=0, second=0, microsecond=0)


def _local(moment: datetime) -> datetime:
    return moment.astimezone(ZoneInfo(config.SCHEDULE_TIME_ZONE))


def _when(moment: datetime) -> str:
    """A local date and time for customers, e.g. "Sat 10 Oct, 2:30pm"."""
    moment = _local(moment)
    minutes = f':{moment.minute:02d}' if moment.minute else ''
    return f'{moment:%a} {moment.day} {moment:%b}, {moment.hour % 12 or 12}{minutes}{"am" if moment.hour < 12 else "pm"}'


def _customer(details: dict, chat_session) -> str:
    """How to greet the customer: their `name` detail, else the chat's display name."""
    name = details.get('name') if isinstance(details, dict) else None
    if isinstance(name, str) and name.strip():
        return name.strip()
    return chat_session.display_name if chat_session is not None and chat_session.display_name else 'there'


def _phone_number(item) -> str | None:
    return item.chat_session.phone_number or None if item.chat_session is not None else None


def _order_total(order: OrderItem) -> str:
    items = order.order_data.get('items', []) if isinstance(order.order_data, dict) else []
    cents = sum(round(float(item['unit_price']) * 100) * item['quantity'] for item in items)
    return f'{cents / 100:.2f}'


def payment_reminder_for_order(order: OrderItem) -> Reminder:
    customer = _customer(order.order_data.get('details', {}), order.chat_session)
    message = (
        f'Hi {customer}, this is {order.business.business_name}. Your order #{order.id} (total ${_order_total(order)}) '
        f'is still waiting for payment. Please complete it with payment reference {order.payment_reference}, '
        'or reply here if you need any help.'
    )
    return Reminder('payment', f'order #{order.id}', _phone_number(order), message)


def payment_reminder_for_booking(booking: ScheduleItem) -> Reminder:
    customer = _customer(booking.schedule_data.get('details', {}), booking.chat_session)
    service = booking.schedule_data['service']
    message = (
        f'Hi {customer}, this is {booking.business.business_name}. Your booking #{booking.id} for {service["name"]} '
        f'on {_when(booking.start_time)} (${service["price"]}) is still waiting for payment. Please complete it with '
        f'payment reference {booking.payment_reference} to keep your time, or reply here if you need any help.'
    )
    return Reminder('payment', f'booking #{booking.id}', _phone_number(booking), message)


def appointment_reminder(booking: ScheduleItem) -> Reminder:
    customer = _customer(booking.schedule_data.get('details', {}), booking.chat_session)
    service = booking.schedule_data['service']
    message = (
        f'Hi {customer}, a reminder from {booking.business.business_name}: your {service["name"]} '
        f'(booking #{booking.id}) is tomorrow, {_when(booking.start_time)}. See you then! '
        'Reply here if you need to change anything.'
    )
    if booking.order_status == PENDING_PAYMENT:
        message += f' It is still waiting for payment: please pay with reference {booking.payment_reference}.'
    return Reminder('appointment', f'booking #{booking.id}', _phone_number(booking), message)


def payment_reminders(session: Session, hour: datetime) -> list[Reminder]:
    """Orders and bookings pending payment, made [1 h, 2 h) before `hour`."""
    newest, oldest = hour - PAYMENT_REMINDER_AFTER[0], hour - PAYMENT_REMINDER_AFTER[1]
    reminders = []
    for model, remind in ((OrderItem, payment_reminder_for_order), (ScheduleItem, payment_reminder_for_booking)):
        items = session.scalars(
            select(model)
            .where(model.order_status == PENDING_PAYMENT, model.created_time > oldest, model.created_time <= newest)
            .options(selectinload(model.business), selectinload(model.chat_session))
            .order_by(model.created_time, model.id)
        )
        reminders += [remind(item) for item in items]
    return reminders


def appointment_reminders(session: Session, hour: datetime) -> list[Reminder]:
    """Bookings starting [23 h, 24 h) after `hour`, except those whose payment failed."""
    first, last = hour + APPOINTMENT_REMINDER_BEFORE[0], hour + APPOINTMENT_REMINDER_BEFORE[1]
    bookings = session.scalars(
        select(ScheduleItem)
        .where(ScheduleItem.order_status != PAYMENT_FAILED, ScheduleItem.start_time >= first, ScheduleItem.start_time < last)
        .options(selectinload(ScheduleItem.business), selectinload(ScheduleItem.chat_session))
        .order_by(ScheduleItem.start_time, ScheduleItem.id)
    )
    return [appointment_reminder(booking) for booking in bookings]


def _log(reminder: Reminder) -> None:
    to = reminder.phone_number or 'no phone number (sandbox chat without one, or the chat was deleted)'
    # TODO: send it to the customer (WhatsApp API), e.g. through the outbound messages queue.
    logger.info('TODO: send %s reminder for %s to %s: %s', reminder.kind, reminder.item, to, reminder.message)


def run(session_factory: Callable[[], Session] = get_session, now: datetime | None = None) -> RunResult:
    hour = floor_to_hour(now or datetime.now(UTC))
    with session_factory() as session:
        payments = payment_reminders(session, hour)
        appointments = appointment_reminders(session, hour)
    logger.info(
        'Run for %s: %d payment reminders, %d appointment reminders', hour.isoformat(), len(payments), len(appointments)
    )
    for reminder in payments + appointments:
        _log(reminder)
    return RunResult(hour, payments, appointments)
