"""When services can be booked, and writing bookings into the providers' weeks: a port of
configuration-service's checkout_app/schedule.py (the parts the chat flow uses) to SQLAlchemy.

Each product_app ServiceProvider has a WeeklyAvailability per week (a week without one is all
unavailable): one letter per 15-minute block, in local time (config.SCHEDULE_TIME_ZONE):
O available, U unavailable, H on hold (booked, payment pending), X booked (paid or done).
- A service can start at `start` (on the 15-minute grid, an allowed start of the service, at least
  MIN_NOTICE from now) with one of its active providers if every block of its duration is O in that
  provider's weeks, no block of its buffer is H / X, and none of the provider's bookings overlaps it.
- sync_booking() writes a new booking into its provider's weeks (Django runs it from a signal on
  every ScheduleItem save; signals don't run here, so checkout.place_booking() calls it).
"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import config
from ..models import ScheduleItem, Service, ServiceProvider, WeeklyAvailability, service_service_providers
from . import dates

# product_app.models: one letter per 15-minute block of a provider's week.
SLOT_MINUTES = 15
SLOTS_PER_DAY = 24 * 60 // SLOT_MINUTES  # 96
DAYS_PER_WEEK = 7
AVAILABILITY_LENGTH = SLOTS_PER_DAY * DAYS_PER_WEEK  # 672
SLOT_AVAILABLE = 'O'
SLOT_UNAVAILABLE = 'U'
SLOT_ON_HOLD = 'H'
SLOT_BOOKED = 'X'
BOOKED_LETTERS = (SLOT_ON_HOLD, SLOT_BOOKED)
UNAVAILABLE_WEEK = SLOT_UNAVAILABLE * AVAILABILITY_LENGTH

# checkout_app.models.OrderStatus
PENDING_PAYMENT = 'pending_payment'
PAYMENT_RECEIVED = 'payment_received'
ORDER_COMPLETED = 'order_completed'
PAYMENT_FAILED = 'payment_failed'

SLOT = timedelta(minutes=SLOT_MINUTES)
# A booking must start at least this long from now.
MIN_NOTICE = timedelta(minutes=60)
# The most days free_slots() looks through at once.
SLOT_SEARCH_DAYS_MAX = 31

HOLD_STATUSES = (PENDING_PAYMENT,)  # their blocks are H
BOOKED_STATUSES = (PAYMENT_RECEIVED, ORDER_COMPLETED)  # X
FREED_STATUSES = (PAYMENT_FAILED,)  # take up no time: their blocks are back to O


def block_index(weekday: int, minute_of_day: int) -> int:
    """The index in a week's letters of the block at `minute_of_day` on `weekday` (Monday = 0)."""
    return weekday * SLOTS_PER_DAY + minute_of_day // SLOT_MINUTES


def schedule_tz() -> ZoneInfo:
    """The time zone of the weekly availabilities' blocks."""
    return ZoneInfo(config.SCHEDULE_TIME_ZONE)


def local(moment: datetime) -> datetime:
    return moment.astimezone(schedule_tz())


def local_midnight(day: date) -> datetime:
    return datetime.combine(day, time(0), tzinfo=schedule_tz())


def is_on_grid(moment: datetime) -> bool:
    """Whether `moment` starts a 15-minute block (local time)."""
    moment = local(moment)
    return moment.second == 0 and moment.microsecond == 0 and moment.minute % SLOT_MINUTES == 0


def floor_to_grid(moment: datetime) -> datetime:
    moment = local(moment)
    return moment.replace(minute=moment.minute - moment.minute % SLOT_MINUTES, second=0, microsecond=0)


def next_on_grid(moment: datetime) -> datetime:
    """The first block start at or after `moment`."""
    floor = floor_to_grid(moment)
    return floor if floor == local(moment) else floor + SLOT


def starts_on_interval(moment: datetime, interval_minutes: int) -> bool:
    """Whether `moment` is an allowed start for a service starting every `interval_minutes`:
    counted from local midnight (30 → 9:00, 9:30…; 60 → 9:00, 10:00…)."""
    if not is_on_grid(moment):
        return False
    moment = local(moment)
    return (moment.hour * 60 + moment.minute) % max(interval_minutes, SLOT_MINUTES) == 0


def day_starts(day: date, interval_minutes: int):
    """The allowed starts of `day` (local), every `interval_minutes` from midnight, in order."""
    step = timedelta(minutes=max(interval_minutes, SLOT_MINUTES))
    midnight, moment = local_midnight(day), local_midnight(day)
    while moment < midnight + timedelta(days=1):
        yield moment
        moment += step


def format_clock(moment: datetime) -> str:
    """A local time of day for customers, e.g. "9am", "9:30am"."""
    moment = local(moment)
    hour = moment.hour % 12 or 12
    minutes = f':{moment.minute:02d}' if moment.minute else ''
    return f'{hour}{minutes}{"am" if moment.hour < 12 else "pm"}'


def interval_problem(service: Service, start: datetime) -> str:
    """Why `start` isn't an allowed start of `service`, with the nearest allowed ones as examples."""
    interval = service.start_interval_minutes
    starts = list(day_starts(local(start).date(), interval))
    before = [s for s in starts if s < start][-1:]
    after = [s for s in starts if s > start][:2 - len(before) or 1]
    examples = ' or '.join(format_clock(s) for s in before + after)
    every = 'hour' if interval == 60 else f'{interval // 60} hours' if interval % 60 == 0 else f'{interval} minutes'
    return f'{service.name} can only start every {every} (for example {examples}).'


def week_start(day: date) -> date:
    """The Monday of `day`'s week (a WeeklyAvailability's `week`)."""
    return day - timedelta(days=day.weekday())


def _block(moment: datetime) -> tuple[date, int]:
    """The week (Monday) and the block index in it of the block starting at `moment`."""
    moment = local(moment)
    return week_start(moment.date()), block_index(moment.weekday(), moment.hour * 60 + moment.minute)


def _grid(start: datetime, end: datetime):
    """The block starts from `start` (floored to the grid) until `end`."""
    moment = floor_to_grid(start)
    while moment < end:
        yield moment
        moment += SLOT


def load_weeks(db: Session, provider_ids: Iterable[int], start: datetime, end: datetime, lock: bool = False) -> dict:
    """The providers' WeeklyAvailability rows covering `start`..`end`: {(provider_id, monday): row}."""
    first, last = week_start(local(start).date()), week_start(local(end).date())
    query = select(WeeklyAvailability).where(
        WeeklyAvailability.service_provider_id.in_(list(provider_ids)), WeeklyAvailability.week.between(first, last)
    )
    rows = db.scalars(query.with_for_update() if lock else query).all()
    return {(row.service_provider_id, row.week): row for row in rows}


def letter_at(weeks: dict, provider_id: int, moment: datetime) -> str:
    """The provider's letter for the block starting at `moment` (U if that week has no row)."""
    monday, index = _block(moment)
    row = weeks.get((provider_id, monday))
    return row.availability[index] if row else SLOT_UNAVAILABLE


@dataclass(frozen=True)
class Booking:
    """Where a booking of a service starting at `start` would go."""

    start: datetime
    end: datetime  # end of the service
    blocked_until: datetime  # end + buffer


def booking_times(service: Service, start: datetime) -> Booking:
    end = start + timedelta(minutes=service.duration_minutes)
    return Booking(start=start, end=end, blocked_until=end + timedelta(minutes=service.buffer_minutes))


def fits(weeks: dict, provider_id: int, times: Booking) -> bool:
    """The whole duration is O, and none of the buffer is booked (it may be U)."""
    return all(letter_at(weeks, provider_id, m) == SLOT_AVAILABLE for m in _grid(times.start, times.end)) and not any(
        letter_at(weeks, provider_id, m) in BOOKED_LETTERS for m in _grid(times.end, times.blocked_until)
    )


def overlaps(bookings: Iterable[ScheduleItem], start: datetime, until: datetime) -> bool:
    return any(booking.start_time < until and booking.blocked_until > start for booking in bookings)


def bookings_between(db: Session, provider_ids: Iterable[int], start: datetime, end: datetime, exclude_id: int | None = None):
    """The bookings of these providers that take up any time between `start` and `end` (not the
    ones whose payment failed: they free their time)."""
    query = select(ScheduleItem).where(
        ScheduleItem.service_provider_id.in_(list(provider_ids)),
        ScheduleItem.start_time < end,
        ScheduleItem.blocked_until > start,
        ScheduleItem.order_status.not_in(FREED_STATUSES),
    )
    if exclude_id is not None:
        query = query.where(ScheduleItem.id != exclude_id)
    return db.scalars(query).all()


def service_providers(db: Session, service: Service, lock: bool = False) -> list[ServiceProvider]:
    """The service's active providers, in pk order (locked with SELECT ... FOR UPDATE if `lock`)."""
    query = (
        select(ServiceProvider)
        .join(service_service_providers, service_service_providers.c.serviceprovider_id == ServiceProvider.id)
        .where(
            service_service_providers.c.service_id == service.id,
            ServiceProvider.business_id == service.business_id,
            ServiceProvider.is_active.is_(True),
        )
        .order_by(ServiceProvider.id)
    )
    return list(db.scalars(query.with_for_update(of=ServiceProvider) if lock else query).all())


def free_provider(
    service: Service, start: datetime, providers: list[ServiceProvider], weeks: dict, bookings: list[ScheduleItem]
) -> ServiceProvider | None:
    """The first of `providers` (in order) who can take `service` at `start`, or None. `weeks` /
    `bookings`: their weeks and bookings around that time (load_weeks / bookings_between)."""
    times = booking_times(service, start)
    for provider in providers:
        own = [booking for booking in bookings if booking.service_provider_id == provider.pk]
        if fits(weeks, provider.pk, times) and not overlaps(own, times.start, times.blocked_until):
            return provider
    return None


def start_problem(db: Session, service: Service, start: datetime, now: datetime | None = None, lock: bool = False) -> str | None:
    """Why `service` can't be booked at `start` (a sentence for the customer), or None if it can."""
    now = now or dates.now()
    if not service.is_active:
        return f'{service.name} is not available for booking at the moment.'
    if not is_on_grid(start):
        return f'Bookings start on the quarter hour (every {SLOT_MINUTES} minutes).'
    if not starts_on_interval(start, service.start_interval_minutes):
        return interval_problem(service, start)
    if start < now + MIN_NOTICE:
        return 'That time is too soon: bookings must be at least an hour from now.'
    providers = service_providers(db, service, lock=lock)
    times = booking_times(service, start)
    weeks = load_weeks(db, [p.pk for p in providers], times.start, times.blocked_until, lock=lock)
    bookings = list(bookings_between(db, [p.pk for p in providers], times.start, times.blocked_until))
    if free_provider(service, start, providers, weeks, bookings) is None:
        return f'{format_slot(start)} is not available for {service.name}.'
    return None


def free_slots(db: Session, service: Service, date_from: date, date_to: date, now: datetime | None = None) -> list[datetime]:
    """Every start time from `date_from` to `date_to` (inclusive, local dates; at most
    SLOT_SEARCH_DAYS_MAX days) at which `service` can be booked, in order: only its allowed starts
    (every `start_interval_minutes` from local midnight)."""
    now = now or dates.now()
    date_to = min(date_to, date_from + timedelta(days=SLOT_SEARCH_DAYS_MAX - 1))
    if not service.is_active or date_to < date_from:
        return []
    window_end = local_midnight(date_to + timedelta(days=1))
    start = max(local_midnight(date_from), next_on_grid(now + MIN_NOTICE))
    providers = service_providers(db, service)
    if not providers or start >= window_end:
        return []
    longest = booking_times(service, window_end).blocked_until
    ids = [p.pk for p in providers]
    weeks = load_weeks(db, ids, start, longest)
    bookings = list(bookings_between(db, ids, start, longest))
    slots = []
    day = local(start).date()
    while day <= date_to:
        for moment in day_starts(day, service.start_interval_minutes):
            if start <= moment < window_end and free_provider(service, moment, providers, weeks, bookings) is not None:
                slots.append(moment)
        day += timedelta(days=1)
    return slots


# --- Writing bookings into the weeks ------------------------------------------------------------

def booking_letter(booking: ScheduleItem) -> str:
    return SLOT_BOOKED if booking.order_status in BOOKED_STATUSES else SLOT_ON_HOLD


def _paint(db: Session, provider_id: int, start: datetime, end: datetime, blocked_until: datetime,
           paint: Callable[[str, bool], str], create: bool) -> None:
    """Sets the provider's blocks from `start` to `blocked_until` to paint(letter, in_duration),
    `in_duration` being before `end`. With `create`, weeks the duration falls in that have no row
    get one (all U before painting). Locks the rows (call inside a transaction)."""
    weeks = load_weeks(db, [provider_id], start, blocked_until, lock=True)
    changed: dict[tuple[int, date], list[str]] = {}
    for moment in _grid(start, blocked_until):
        monday, index = _block(moment)
        key = (provider_id, monday)
        if key not in weeks:
            if not (create and moment < end):
                continue
            weeks[key] = WeeklyAvailability(service_provider_id=provider_id, week=monday, availability=UNAVAILABLE_WEEK)
            db.add(weeks[key])
        letters = changed.setdefault(key, list(weeks[key].availability))
        letters[index] = paint(letters[index], moment < end)
    for key, letters in changed.items():
        weeks[key].availability = ''.join(letters)
    db.flush()


def sync_booking(db: Session, booking: ScheduleItem) -> None:
    """Writes `booking` into its provider's weeks: H while pending payment, X once paid or
    completed, over its duration, and over its buffer where that isn't U. A booking whose payment
    failed frees its time instead (H / X back to O)."""
    if booking.service_provider_id is None:
        return
    if booking.order_status in FREED_STATUSES:
        _paint(
            db, booking.service_provider_id, booking.start_time, booking.end_time, booking.blocked_until,
            lambda current, in_duration: SLOT_AVAILABLE if current in BOOKED_LETTERS else current, create=False,
        )
        return
    letter = booking_letter(booking)
    _paint(
        db, booking.service_provider_id, booking.start_time, booking.end_time, booking.blocked_until,
        lambda current, in_duration: letter if in_duration or current != SLOT_UNAVAILABLE else current,
        create=True,
    )


def format_slot(start: datetime) -> str:
    """A start time for customers, in local time, e.g. "Tue 14 Oct, 2:30pm"."""
    moment = local(start)
    hour = moment.hour % 12 or 12
    minutes = f':{moment.minute:02d}' if moment.minute else ''
    return f'{moment:%a} {moment.day} {moment:%b}, {hour}{minutes}{"am" if moment.hour < 12 else "pm"}'
