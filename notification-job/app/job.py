"""The notification job, run every hour (cron.sh). Each run:

1. Payment reminders: orders (OrderItem) and bookings (ScheduleItem) still pending payment that
   were made 1 to 2 hours ago, [1 h, 2 h) before the hour (created_time in (hour − 2 h, hour − 1 h]).
2. Appointment reminders: bookings starting 23 to 24 hours from now, [23 h, 24 h) after the hour
   (start_time in [hour + 23 h, hour + 24 h)), unless their payment failed (they hold no time).
3. WhatsApp reconnect alerts, to the business's users: its WhatsApp access token (from Embedded Signup,
   e.g. 60 days) expires in 7 days, in 1 day, or has just expired (the alert's point,
   access_token_expires_time − 7 d / 1 d / 0, in (hour − 1 h, hour]). Only connections Meta still
   reports connected (a disconnected or banned one has a bigger problem, shown in the app).
   Reconnecting with Facebook gives a new token and expiry, so no more alerts for the old one.

"The hour" is the run's time rounded down to the hour (9:11:30 pm → 9 pm), so the windows of
consecutive hourly runs follow each other without gaps or overlaps: each item gets each reminder
once.

The appointment reminders are SENT, on WhatsApp (to the chat's phone number, through
configuration-service) and by email (to the booking's `email` detail), each when the customer has a
way to be reached on it.

The payment reminders and the alerts are still only logged (the phone number or email addresses and
a draft message): sending them is a TODO.
"""

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app import config, email_sender, whatsapp_sender
from app.db import get_session
from app.models import (
    CONNECTED,
    PAYMENT_FAILED,
    PENDING_PAYMENT,
    BusinessUser,
    OrderItem,
    ScheduleItem,
    WhatsAppConfiguration,
)

logger = logging.getLogger(__name__)

PAYMENT_REMINDER_AFTER = (timedelta(hours=1), timedelta(hours=2))  # [1 h, 2 h) after it was made
APPOINTMENT_REMINDER_BEFORE = (timedelta(hours=23), timedelta(hours=24))  # [23 h, 24 h) before it starts
# Reconnect alerts this long before the WhatsApp access token expires (0: once it has). The first matches
# configuration-service's ACCESS_TOKEN_EXPIRY_WARNING (when the app starts warning): change both together.
RECONNECT_ALERTS_BEFORE = (timedelta(days=7), timedelta(days=1), timedelta(0))
HOUR = timedelta(hours=1)


@dataclass(frozen=True)
class Reminder:
    kind: str  # 'payment' or 'appointment'
    item: str  # e.g. 'order #12', 'booking #3'
    phone_number: str | None  # None: no number to send to (a sandbox chat without one, or the chat was deleted)
    message: str  # the WhatsApp message
    business_id: int = 0  # whose WhatsApp number it is sent from
    email: str | None = None  # None: no valid `email` detail to send to
    email_subject: str = ''
    email_text: str = ''


@dataclass(frozen=True)
class Alert:
    kind: str  # 'whatsapp_reconnect'
    business: str  # e.g. 'business #4 (Lumen & Lens)'
    emails: list[str]  # the business's active users' addresses (empty: none has one)
    message: str


@dataclass(frozen=True)
class RunResult:
    hour: datetime
    payment_reminders: list[Reminder]
    appointment_reminders: list[Reminder]
    reconnect_alerts: list[Alert]
    failed_reminders: list[Reminder] = field(default_factory=list)


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


EMAIL_ADDRESS = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')


def _email_address(details: dict) -> str | None:
    """The customer's email address: their `email` detail, if it looks like one."""
    if not isinstance(details, dict):
        return None
    value = next((v for k, v in details.items() if isinstance(k, str) and k.lower() == 'email'), None)
    email = value.strip() if isinstance(value, str) else ''
    return email if EMAIL_ADDRESS.match(email) else None


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
    """The reminder for a booking that starts in about 24 hours: the WhatsApp message, and the email."""
    details = booking.schedule_data.get('details', {})
    customer = _customer(details, booking.chat_session)
    service = booking.schedule_data['service']['name']
    business = booking.business
    when = _when(booking.start_time)
    unpaid = booking.order_status == PENDING_PAYMENT

    message = (
        f'Hi {customer}, a reminder from {business.business_name}: your {service} (booking #{booking.id}) '
        f'starts in about 24 hours, on {when}. See you tomorrow! Reply here if you need to change anything.'
    )
    if unpaid:
        message += f' It is still waiting for payment: please pay with reference {booking.payment_reference}.'

    lines = [
        f'Hi {customer},',
        '',
        f'This is a reminder from {business.business_name}: your {service} (booking #{booking.id}) starts in about 24 hours.',
        '',
        f'Time: {when}',
    ]
    if business.location:
        lines.append(f'Location: {business.location}')
    if unpaid:
        lines += ['', f'It is still waiting for payment, so please pay with reference {booking.payment_reference} to keep your time.']
    lines += [
        '',
        f'If you need to change anything, just message {business.business_name} in your WhatsApp chat.',
        '',
        'See you soon,',
        business.business_name,
    ]
    return Reminder(
        'appointment', f'booking #{booking.id}', _phone_number(booking), message,
        business_id=booking.business_id,
        email=_email_address(details),
        email_subject=f'Reminder: your {service} with {business.business_name} starts in about 24 hours',
        email_text='\n'.join(lines),
    )


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


def reconnect_alert(config: WhatsAppConfiguration, emails: list[str], now: datetime) -> Alert:
    business = config.business.business_name
    number = config.display_phone_number or f'phone number ID {config.phone_number_id}'
    if config.access_token_expires_time <= now:
        message = (
            f"Hi {business}, your WhatsApp connection ({number}) has expired, so your assistant can't reply to "
            'customers on WhatsApp. Reconnect it with Facebook on the Home page of Ansera Business Admin.'
        )
    else:
        message = (
            f'Hi {business}, your WhatsApp connection ({number}) expires on {_when(config.access_token_expires_time)}. '
            'Reconnect it with Facebook on the Home page of Ansera Business Admin before then, or your assistant '
            "won't be able to reply to customers on WhatsApp."
        )
    return Alert('whatsapp_reconnect', f'business #{config.business_id} ({business})', emails, message)


def reconnect_alerts(session: Session, hour: datetime) -> list[Alert]:
    """Connected WhatsApp connections whose access token expires 7 days / 1 day after `hour`, or expired,
    i.e. each alert point (the expiry minus 7 d / 1 d / 0) is in (hour − 1 h, hour]."""
    configs = []
    for before in RECONNECT_ALERTS_BEFORE:
        configs += session.scalars(
            select(WhatsAppConfiguration)
            .where(
                WhatsAppConfiguration.status == CONNECTED,
                WhatsAppConfiguration.access_token_expires_time > hour + before - HOUR,
                WhatsAppConfiguration.access_token_expires_time <= hour + before,
            )
            .options(selectinload(WhatsAppConfiguration.business))
            .order_by(WhatsAppConfiguration.access_token_expires_time, WhatsAppConfiguration.id)
        )
    emails: dict[int, list[str]] = {}  # the business's active users' addresses
    if configs:
        users = session.execute(
            select(BusinessUser.business_id, BusinessUser.email)
            .where(
                BusinessUser.business_id.in_({config.business_id for config in configs}),
                BusinessUser.is_active,
                BusinessUser.email != '',
            )
            .order_by(BusinessUser.id)
        )
        for business_id, email in users:
            emails.setdefault(business_id, []).append(email)
    return [reconnect_alert(config, emails.get(config.business_id, []), hour) for config in configs]


def _send_whatsapp(reminder: Reminder) -> bool:
    """Sends the WhatsApp message. Returns whether it was sent. Raises SendError only when trying again
    could help. A refusal is logged and returns False."""
    if not reminder.phone_number:
        logger.info('Reminder for %s: no phone number for WhatsApp (a sandbox chat without one, or the chat was deleted)', reminder.item)
        return False
    try:
        whatsapp_sender.send_text(reminder.business_id, reminder.phone_number, reminder.message)
    except whatsapp_sender.SendError as exc:
        if exc.retryable:
            raise
        logger.error('Reminder for %s: not sent on WhatsApp: %s', reminder.item, exc)
        return False
    logger.info('Reminder for %s: sent on WhatsApp to %s', reminder.item, reminder.phone_number)
    return True


def _send_email(reminder: Reminder) -> bool:
    """Emails the reminder. Returns whether it was sent (False: no address, or email is switched off).
    Raises EmailError only when trying again could help; a refusal is logged and returns False."""
    if not reminder.email:
        logger.info('Reminder for %s: no email address', reminder.item)
        return False
    try:
        sent = email_sender.send_email(reminder.email_subject, reminder.email_text, reminder.email)
    except email_sender.EmailError as exc:
        if exc.retryable:
            raise
        logger.error('Reminder for %s: not emailed: %s', reminder.item, exc)
        return False
    if sent:
        logger.info('Reminder for %s: emailed to %s', reminder.item, reminder.email)
    return sent


def send_reminder(reminder: Reminder) -> None:
    """Sends the reminder on WhatsApp and by email. One channel failing doesn't stop the other: both are
    tried, then the first failure that could work later is raised."""
    retry = None
    for send in (_send_whatsapp, _send_email):
        try:
            send(reminder)
        except (whatsapp_sender.SendError, email_sender.EmailError) as exc:
            logger.warning('Reminder for %s: could not be sent yet: %s', reminder.item, exc)
            retry = retry or exc
    if retry:
        raise retry


def _log(reminder: Reminder) -> None:
    to = reminder.phone_number or 'no phone number (sandbox chat without one, or the chat was deleted)'
    # TODO: send it to the customer (WhatsApp API), e.g. through the outbound messages queue.
    logger.info('TODO: send %s reminder for %s to %s: %s', reminder.kind, reminder.item, to, reminder.message)


def _log_alert(alert: Alert) -> None:
    to = ', '.join(alert.emails) or "no email address (none of the business's users has one)"
    # TODO: send it to the business's users (email), e.g. through an outbound notifications queue.
    logger.warning('TODO: send %s alert for %s to %s: %s', alert.kind, alert.business, to, alert.message)


def run(session_factory: Callable[[], Session] = get_session, now: datetime | None = None) -> RunResult:
    hour = floor_to_hour(now or datetime.now(UTC))
    with session_factory() as session:
        payments = payment_reminders(session, hour)
        appointments = appointment_reminders(session, hour)
        alerts = reconnect_alerts(session, hour)
    logger.info(
        'Run for %s: %d payment reminders, %d appointment reminders, %d WhatsApp reconnect alerts',
        hour.isoformat(), len(payments), len(appointments), len(alerts),
    )
    for reminder in payments:
        _log(reminder)  # TODO: send the payment reminders too
    failed = []
    for reminder in appointments:
        try:
            send_reminder(reminder)
        except (whatsapp_sender.SendError, email_sender.EmailError):
            failed.append(reminder)  # already logged, the others still go out
    for alert in alerts:
        _log_alert(alert)
    if failed:
        logger.error('%d of %d appointment reminders could not be sent yet', len(failed), len(appointments))
    return RunResult(hour, payments, appointments, alerts, failed)
