"""Writing a booking's payment outcome into its service provider's weekly availabilities.

A port of configuration-service's checkout_app.schedule.sync_booking() / release_booking(), which
Django runs from signals on every ScheduleItem save: this service updates the rows through
SQLAlchemy, so those signals don't run, and it must paint the letters itself, the same way:
- paid → X over the booking's duration, and over its buffer where the block isn't U (creating a
  week that has no row, for the duration);
- payment failed → its H / X blocks back to O (its time is free again).

Weeks are in local time (config.SCHEDULE_TIME_ZONE, as in configuration-service): one letter per
15-minute block from Monday 00:00.
"""

from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import config
from .models import (
    BOOKED_LETTERS,
    SLOT_AVAILABLE,
    SLOT_BOOKED,
    SLOT_MINUTES,
    SLOT_UNAVAILABLE,
    SLOTS_PER_DAY,
    UNAVAILABLE_WEEK,
    ScheduleItem,
    WeeklyAvailability,
)

SLOT = timedelta(minutes=SLOT_MINUTES)


def local(moment: datetime) -> datetime:
    if moment.tzinfo is None:  # SQLite (tests) returns naive datetimes; PostgreSQL's are aware
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(ZoneInfo(config.SCHEDULE_TIME_ZONE))


def week_start(day: date) -> date:
    return day - timedelta(days=day.weekday())


def block(moment: datetime) -> tuple[date, int]:
    """The week (Monday) and the index in its letters of the block starting at `moment`."""
    moment = local(moment)
    return week_start(moment.date()), moment.weekday() * SLOTS_PER_DAY + (moment.hour * 60 + moment.minute) // SLOT_MINUTES


def grid(start: datetime, end: datetime):
    """The block starts from `start` (floored to the grid) until `end`."""
    moment = local(start)
    moment = moment.replace(minute=moment.minute - moment.minute % SLOT_MINUTES, second=0, microsecond=0)
    end = local(end)
    while moment < end:
        yield moment
        moment += SLOT


def paint(session: Session, booking: ScheduleItem, letter_for: Callable[[str, bool], str], create: bool) -> None:
    """Sets the booking's blocks (start → blocked_until) to letter_for(current, in_duration),
    locking the provider's week rows (SELECT … FOR UPDATE, as Django's _paint does)."""
    provider_id = booking.service_provider_id
    first, last = week_start(local(booking.start_time).date()), week_start(local(booking.blocked_until).date())
    rows = session.scalars(
        select(WeeklyAvailability)
        .where(WeeklyAvailability.service_provider_id == provider_id, WeeklyAvailability.week.between(first, last))
        .with_for_update()
    ).all()
    weeks = {row.week: row for row in rows}
    letters: dict[date, list[str]] = {}
    end = local(booking.end_time)
    for moment in grid(booking.start_time, booking.blocked_until):
        monday, index = block(moment)
        if monday not in weeks:
            if not (create and moment < end):
                continue
            weeks[monday] = WeeklyAvailability(service_provider_id=provider_id, week=monday, availability=UNAVAILABLE_WEEK)
            session.add(weeks[monday])
        week_letters = letters.setdefault(monday, list(weeks[monday].availability))
        week_letters[index] = letter_for(week_letters[index], moment < end)
    for monday, week_letters in letters.items():
        weeks[monday].availability = ''.join(week_letters)


def mark_booked(session: Session, booking: ScheduleItem) -> None:
    """Paid: the booking's time is taken (X), its buffer too where the provider is open."""
    if booking.service_provider_id is None:
        return
    paint(
        session, booking,
        lambda current, in_duration: SLOT_BOOKED if in_duration or current != SLOT_UNAVAILABLE else current,
        create=True,
    )


def release(session: Session, booking: ScheduleItem) -> None:
    """Payment failed: the booking's H / X blocks are available (O) again."""
    if booking.service_provider_id is None:
        return
    paint(
        session, booking,
        lambda current, in_duration: SLOT_AVAILABLE if current in BOOKED_LETTERS else current,
        create=False,
    )
