"""Calendar helpers for the tests, ported from configuration-service's
checkout_app/tests/test_schedule.py and product_app/tests.py (open_hours)."""

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.chat_flow import dates, schedule
from app.chat_flow.checkout import new_payment_reference
from app.chat_flow.schedule import AVAILABILITY_LENGTH, PENDING_PAYMENT, block_index, week_start
from app.models import ScheduleItem, WeeklyAvailability

TZ = ZoneInfo('Asia/Singapore')


def open_hours(*ranges, letter='O', base=None) -> str:
    """A week's letters with `letter` in each `(weekday, 'HH:MM', 'HH:MM')` range (0 = Monday)
    and U elsewhere (or `base`), e.g. open_hours((0, '09:00', '12:00'))."""
    letters = list(base or 'U' * AVAILABILITY_LENGTH)
    for weekday, start, end in ranges:
        first = block_index(weekday, int(start[:2]) * 60 + int(start[3:]))
        last = block_index(weekday, int(end[:2]) * 60 + int(end[3:])) if end != '24:00' else block_index(weekday + 1, 0)
        for index in range(first, last):
            letters[index] = letter
    return ''.join(letters)


def future_monday(weeks: int = 2) -> date:
    """A Monday far enough ahead that every slot in tests is bookable (past MIN_NOTICE)."""
    return week_start(dates.now().astimezone(TZ).date()) + timedelta(weeks=weeks)


def at(day: date, hhmm: str) -> datetime:
    """A local (Singapore) time on `day`."""
    return datetime.combine(day, time(int(hhmm[:2]), int(hhmm[3:])), tzinfo=TZ)


def open_week(sessions: sessionmaker, provider, monday: date, *ranges) -> WeeklyAvailability:
    """The provider's week of `monday`, with the `(weekday, 'HH:MM', 'HH:MM')` ranges open (O)."""
    with sessions.begin() as db:
        week = db.scalars(
            select(WeeklyAvailability).where(WeeklyAvailability.service_provider_id == provider.id, WeeklyAvailability.week == monday)
        ).first()
        if week is None:
            week = WeeklyAvailability(service_provider_id=provider.id, week=monday)
            db.add(week)
        week.availability = open_hours(*ranges)
    return week


def letters(sessions: sessionmaker, provider, monday: date) -> str:
    """The provider's letters for the week (U if it has none)."""
    with sessions() as db:
        week = db.scalars(
            select(WeeklyAvailability).where(WeeklyAvailability.service_provider_id == provider.id, WeeklyAvailability.week == monday)
        ).first()
    return week.availability if week else 'U' * AVAILABILITY_LENGTH


def day_letters(sessions: sessionmaker, provider, day: date, start: str = '00:00', end: str = '24:00') -> str:
    """The provider's letters on `day` between two times, e.g. 'OOHHHH'."""
    week = letters(sessions, provider, week_start(day))
    first = day.weekday() * 96 + (int(start[:2]) * 60 + int(start[3:])) // 15
    last = day.weekday() * 96 + (int(end[:2]) * 60 + int(end[3:])) // 15
    return week[first:last]


def book(sessions: sessionmaker, service, provider, start, status=PENDING_PAYMENT, **fields) -> ScheduleItem:
    """A booking saved straight to the database (not through place_booking), and written into the
    provider's week, as Django's signal does on save."""
    end = start + timedelta(minutes=service.duration_minutes)
    now = datetime.now(UTC)
    chat_session = fields.pop('chat_session', None)
    values = {
        'business_id': service.business_id,
        'service_id': service.id,
        'service_provider_id': provider.id if provider else None,
        'start_time': start,
        'end_time': end,
        'blocked_until': end + timedelta(minutes=service.buffer_minutes),
        'order_status': status,
        'schedule_data': {
            'service': {
                'service_id': service.id, 'name': service.name, 'price': str(service.price),
                'duration_minutes': service.duration_minutes, 'buffer_minutes': service.buffer_minutes,
            },
            'details': {},
        },
        'chat_session_id': chat_session.id if chat_session else None,
        'is_sandbox': False,
        'payment_reference': new_payment_reference(),
        'created_time': now,
        'updated_time': now,
        **fields,
    }
    with sessions.begin() as db:
        booking = ScheduleItem(**values)
        db.add(booking)
        db.flush()
        schedule.sync_booking(db, booking)
    return booking
