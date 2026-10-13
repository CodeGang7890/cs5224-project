"""When services can be booked, and keeping the providers' weeks in step with the bookings.

Each product_app.ServiceProvider has a WeeklyAvailability per week (a week without one is all
unavailable): one letter per 15-minute block, in local time (settings.SCHEDULE_TIME_ZONE):
O available, U unavailable, H on hold (booked, payment pending), X booked (paid or done).
- The business opens and closes blocks (O / U): set_slots() for days and times over a range of
  weeks, copy_week() to repeat a week, or by editing a week (product_app's API, which never lets
  it touch H / X).
- The bookings set H / X: sync_booking() writes a booking into its provider's weeks (H while its
  order_status is pending payment, X once paid or completed) over its whole time, the service's
  duration and its buffer (the buffer only where it isn't U, e.g. after closing).
  release_booking() turns them back to O when the booking is deleted or moved. checkout_app's
  signals call them on every save / delete of a ScheduleItem.
- A service can start at `start` (on the 15-minute grid, at least MIN_NOTICE from now) with one of
  its active providers if every block of its duration is O in that provider's weeks, no block of
  its buffer is H / X, and (a safety net: the letters say the same) none of the provider's
  bookings overlaps it.
"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from product_app.models import (
    BOOKED_LETTERS,
    SLOT_AVAILABLE,
    SLOT_BOOKED,
    SLOT_MINUTES,
    SLOT_ON_HOLD,
    SLOT_UNAVAILABLE,
    UNAVAILABLE_WEEK,
    Service,
    ServiceProvider,
    WeeklyAvailability,
    block_index,
)

from .models import OrderStatus, ScheduleItem

SLOT = timedelta(minutes=SLOT_MINUTES)
# A booking must start at least this long from now.
MIN_NOTICE = timedelta(minutes=60)
# The most days free_slots() looks through at once.
SLOT_SEARCH_DAYS_MAX = 31
# The most weeks set_slots() / copy_week() change at once.
WEEKS_CHANGED_MAX = 26

HOLD_STATUSES = (OrderStatus.PENDING_PAYMENT,)  # their blocks are H
BOOKED_STATUSES = (OrderStatus.PAYMENT_RECEIVED, OrderStatus.ORDER_COMPLETED)  # X
FREED_STATUSES = (OrderStatus.PAYMENT_FAILED,)  # take up no time: their blocks are back to O


def schedule_tz() -> ZoneInfo:
    """The time zone of the weekly availabilities' blocks."""
    return ZoneInfo(settings.SCHEDULE_TIME_ZONE)


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


def week_block(monday: date, moment: datetime) -> int:
    """Blocks from `monday` 00:00 (local) to `moment`, floored: 0–671 inside that week, negative
    before it, 672 or more after it (local wall-clock time, like the letters)."""
    since = local(moment).replace(tzinfo=None) - datetime.combine(monday, time())
    return since // SLOT


def _grid(start: datetime, end: datetime):
    """The block starts from `start` (floored to the grid) until `end`."""
    moment = floor_to_grid(start)
    while moment < end:
        yield moment
        moment += SLOT


def load_weeks(provider_ids: Iterable[int], start: datetime, end: datetime, lock: bool = False) -> dict:
    """The providers' WeeklyAvailability rows covering `start`..`end`: {(provider_id, monday): row}."""
    first, last = week_start(local(start).date()), week_start(local(end).date())
    rows = WeeklyAvailability.objects.filter(service_provider_id__in=list(provider_ids), week__range=(first, last))
    return {(row.service_provider_id, row.week): row for row in (rows.select_for_update() if lock else rows)}


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


def bookings_between(provider_ids: Iterable[int], start: datetime, end: datetime):
    """The bookings of these providers that take up any time between `start` and `end` (not the
    ones whose payment failed: they free their time)."""
    return ScheduleItem.objects.filter(
        service_provider_id__in=list(provider_ids), start_time__lt=end, blocked_until__gt=start
    ).exclude(order_status__in=FREED_STATUSES)


def service_providers(service: Service, lock: bool = False) -> list[ServiceProvider]:
    """The service's active providers, in pk order (locked with SELECT ... FOR UPDATE if `lock`)."""
    queryset = ServiceProvider.objects.filter(
        services=service, business_id=service.business_id, is_active=True
    ).order_by('pk')
    return list(queryset.select_for_update() if lock else queryset)


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


def start_problem(service: Service, start: datetime, now: datetime | None = None, lock: bool = False) -> str | None:
    """Why `service` can't be booked at `start` (a sentence for the customer), or None if it can."""
    now = now or timezone.now()
    if not service.is_active:
        return f'{service.name} is not available for booking at the moment.'
    if not is_on_grid(start):
        return f'Bookings start on the quarter hour (every {SLOT_MINUTES} minutes).'
    if not starts_on_interval(start, service.start_interval_minutes):
        return interval_problem(service, start)
    if start < now + MIN_NOTICE:
        return 'That time is too soon: bookings must be at least an hour from now.'
    providers = service_providers(service, lock=lock)
    times = booking_times(service, start)
    weeks = load_weeks([p.pk for p in providers], times.start, times.blocked_until, lock=lock)
    bookings = list(bookings_between([p.pk for p in providers], times.start, times.blocked_until))
    if free_provider(service, start, providers, weeks, bookings) is None:
        return f'{format_slot(start)} is not available for {service.name}.'
    return None


def free_slots(service: Service, date_from: date, date_to: date, now: datetime | None = None) -> list[datetime]:
    """Every start time from `date_from` to `date_to` (inclusive, local dates; at most
    SLOT_SEARCH_DAYS_MAX days) at which `service` can be booked, in order: only its allowed starts
    (every `start_interval_minutes` from local midnight)."""
    now = now or timezone.now()
    date_to = min(date_to, date_from + timedelta(days=SLOT_SEARCH_DAYS_MAX - 1))
    if not service.is_active or date_to < date_from:
        return []
    window_end = local_midnight(date_to + timedelta(days=1))
    start = max(local_midnight(date_from), next_on_grid(now + MIN_NOTICE))
    providers = service_providers(service)
    if not providers or start >= window_end:
        return []
    longest = booking_times(service, window_end).blocked_until
    ids = [p.pk for p in providers]
    weeks = load_weeks(ids, start, longest)
    bookings = list(bookings_between(ids, start, longest))
    slots = []
    day = local(start).date()
    while day <= date_to:
        for moment in day_starts(day, service.start_interval_minutes):
            if start <= moment < window_end and free_provider(service, moment, providers, weeks, bookings) is not None:
                slots.append(moment)
        day += timedelta(days=1)
    return slots


def week_calendar(provider: ServiceProvider, day: date) -> tuple[WeeklyAvailability | None, list[ScheduleItem]]:
    """The week of `day` (Monday to Sunday) of a provider: its WeeklyAvailability (None if it has
    none yet: all unavailable), and the bookings taking up any of its time."""
    monday = week_start(day)
    row = WeeklyAvailability.objects.filter(service_provider=provider, week=monday).first()
    start, end = local_midnight(monday), local_midnight(monday + timedelta(days=7))
    bookings = list(
        bookings_between([provider.pk], start, end).select_related('service', 'chat_session').order_by('start_time')
    )
    return row, bookings


# --- Writing bookings into the weeks ------------------------------------------------------------

def booking_letter(booking: ScheduleItem) -> str:
    return SLOT_BOOKED if booking.order_status in BOOKED_STATUSES else SLOT_ON_HOLD


def _paint(provider_id: int, start: datetime, end: datetime, blocked_until: datetime,
           paint: Callable[[str, bool], str], create: bool) -> None:
    """Sets the provider's blocks from `start` to `blocked_until` to paint(letter, in_duration),
    `in_duration` being before `end`. With `create`, weeks the duration falls in that have no row
    get one (all U before painting). Locks the rows (call inside a transaction)."""
    with transaction.atomic():
        weeks = load_weeks([provider_id], start, blocked_until, lock=True)
        changed: dict[tuple[int, date], list[str]] = {}
        for moment in _grid(start, blocked_until):
            monday, index = _block(moment)
            key = (provider_id, monday)
            if key not in weeks:
                if not (create and moment < end):
                    continue
                weeks[key] = WeeklyAvailability.objects.create(service_provider_id=provider_id, week=monday)
            letters = changed.setdefault(key, list(weeks[key].availability))
            letters[index] = paint(letters[index], moment < end)
        for key, letters in changed.items():
            row = weeks[key]
            new = ''.join(letters)
            if new != row.availability:
                # update(), not save(): during a cascade delete the row may already be gone.
                WeeklyAvailability.objects.filter(pk=row.pk).update(availability=new)
                row.availability = new


def sync_booking(booking: ScheduleItem) -> None:
    """Writes `booking` into its provider's weeks: H while pending payment, X once paid or
    completed, over its duration, and over its buffer where that isn't U. A booking whose payment
    failed frees its time instead (H / X back to O)."""
    if booking.service_provider_id is None:
        return
    if booking.order_status in FREED_STATUSES:
        release_booking(booking.service_provider_id, booking.start_time, booking.end_time, booking.blocked_until)
        return
    letter = booking_letter(booking)
    _paint(
        booking.service_provider_id, booking.start_time, booking.end_time, booking.blocked_until,
        lambda current, in_duration: letter if in_duration or current != SLOT_UNAVAILABLE else current,
        create=True,
    )


def release_booking(provider_id: int | None, start: datetime, end: datetime, blocked_until: datetime) -> None:
    """A booking's time is free again (deleted, or moved): its H / X blocks go back to O."""
    if provider_id is None:
        return
    _paint(
        provider_id, start, end, blocked_until,
        lambda current, in_duration: SLOT_AVAILABLE if current in BOOKED_LETTERS else current,
        create=False,
    )


# --- The business opening and closing blocks ----------------------------------------------------

@dataclass
class WeeksChange:
    """What set_slots() / copy_week() did."""

    weeks: list[WeeklyAvailability]  # every week changed or created, in order
    changed: int = 0  # blocks that changed
    skipped: int = 0  # blocks left alone because they're booked (H / X)


def _week_row(weeks: dict, provider: ServiceProvider, monday: date) -> WeeklyAvailability:
    if monday not in weeks:
        weeks[monday] = WeeklyAvailability.objects.filter(service_provider=provider, week=monday).select_for_update().first() \
            or WeeklyAvailability(service_provider=provider, week=monday)
    return weeks[monday]


def set_slots(
    provider: ServiceProvider, date_from: date, date_to: date, weekdays: Iterable[int],
    time_from: time, time_to: time | None, available: bool = True,
) -> WeeksChange:
    """Opens (O) or closes (U) the blocks from `time_from` to `time_to` (None: midnight) on every
    day from `date_from` to `date_to` (inclusive) whose weekday (0 = Monday) is in `weekdays`.
    Booked blocks (H / X) are left as they are. Missing weeks are created. One transaction, with the
    provider locked (like messaging-service's place_booking), so a booking can't be made at the same moment."""
    weekdays = set(weekdays)
    letter = SLOT_AVAILABLE if available else SLOT_UNAVAILABLE
    change = WeeksChange(weeks=[])
    with transaction.atomic():
        ServiceProvider.objects.select_for_update().filter(pk=provider.pk).first()
        weeks: dict[date, WeeklyAvailability] = {}
        letters: dict[date, list[str]] = {}
        day = date_from
        while day <= date_to:
            if day.weekday() in weekdays:
                start = datetime.combine(day, time_from, tzinfo=schedule_tz())
                end = datetime.combine(day, time_to, tzinfo=schedule_tz()) if time_to else local_midnight(day + timedelta(days=1))
                for moment in _grid(start, end):
                    monday, index = _block(moment)
                    row = _week_row(weeks, provider, monday)
                    week_letters = letters.setdefault(monday, list(row.availability))
                    if week_letters[index] in BOOKED_LETTERS:
                        change.skipped += 1
                    elif week_letters[index] != letter:
                        week_letters[index] = letter
                        change.changed += 1
            day += timedelta(days=1)
        change.weeks = _save_weeks(weeks, letters)
    return change


def copy_week(provider: ServiceProvider, source: date, targets: Iterable[date]) -> WeeksChange:
    """Copies the open / closed blocks of the week `source` (a Monday) to the weeks `targets`
    (Mondays): a block booked in the source (H / X) counts as open there. Booked blocks in a target
    are left as they are. Missing weeks are created; one transaction, the provider locked."""
    change = WeeksChange(weeks=[])
    with transaction.atomic():
        ServiceProvider.objects.select_for_update().filter(pk=provider.pk).first()
        row = WeeklyAvailability.objects.filter(service_provider=provider, week=source).first()
        pattern = [
            SLOT_AVAILABLE if letter != SLOT_UNAVAILABLE else SLOT_UNAVAILABLE
            for letter in (row.availability if row else UNAVAILABLE_WEEK)
        ]
        weeks: dict[date, WeeklyAvailability] = {}
        letters: dict[date, list[str]] = {}
        for monday in sorted(set(targets) - {source}):
            target = _week_row(weeks, provider, monday)
            week_letters = letters.setdefault(monday, list(target.availability))
            for index, letter in enumerate(pattern):
                if week_letters[index] in BOOKED_LETTERS:
                    if letter == SLOT_UNAVAILABLE:
                        change.skipped += 1  # a booked block can't be closed
                elif week_letters[index] != letter:
                    week_letters[index] = letter
                    change.changed += 1
        change.weeks = _save_weeks(weeks, letters)
    return change


def _save_weeks(weeks: dict, letters: dict) -> list[WeeklyAvailability]:
    saved = []
    for monday in sorted(weeks):
        row = weeks[monday]
        new = ''.join(letters[monday])
        if row.pk is None or new != row.availability:
            row.availability = new
            row.full_clean()
            row.save()
        saved.append(row)
    return saved


def format_slot(start: datetime) -> str:
    """A start time for customers, in local time, e.g. "Tue 14 Oct, 2:30pm"."""
    moment = local(start)
    hour = moment.hour % 12 or 12
    minutes = f':{moment.minute:02d}' if moment.minute else ''
    return f'{moment:%a} {moment.day} {moment:%b}, {hour}{minutes}{"am" if moment.hour < 12 else "pm"}'
