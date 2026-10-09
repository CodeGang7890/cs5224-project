"""When services can be booked: the weekly availabilities (recurring templates) minus the bookings.

A product_app.WeeklyAvailability stores only its weekly template: one letter per 15-minute block
of the week, in local time (settings.SCHEDULE_TIME_ZONE), and only O blocks can be booked. The
bookings (ScheduleItem) are on real dates, so what's free on a given day is worked out here:
- a booking takes up its availability from `start_time` to `blocked_until` (the service's
  duration plus its buffer), in every status (pending payment, paid, completed);
- a service can start at `start` if one of its availabilities has the service's whole duration in
  O blocks, and no booking of that availability overlaps `start` .. `start + duration + buffer`
  (the buffer needn't be in O blocks: it's time without the customer, e.g. after closing);
- starts are on the 15-minute grid, at least MIN_NOTICE from now.
week_calendar() draws a week's bookings over the template: pending payment as H, paid or
completed as X (like a product's on hold / sold quantities, derived from the orders).
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.utils import timezone

from product_app.models import (
    AVAILABILITY_LENGTH,
    SLOT_AVAILABLE,
    SLOT_MINUTES,
    SLOT_ON_HOLD,
    SLOT_TAKEN,
    Service,
    WeeklyAvailability,
    block_index,
)

from .models import OrderStatus, ScheduleItem

SLOT = timedelta(minutes=SLOT_MINUTES)
# A booking must start at least this long from now.
MIN_NOTICE = timedelta(minutes=60)
# The most days free_slots() looks through at once.
SLOT_SEARCH_DAYS_MAX = 31

HOLD_STATUSES = (OrderStatus.PENDING_PAYMENT,)  # shown as H in a week's calendar
TAKEN_STATUSES = (OrderStatus.PAYMENT_RECEIVED, OrderStatus.ORDER_COMPLETED)  # shown as X


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


def next_on_grid(moment: datetime) -> datetime:
    """The first block start at or after `moment`."""
    moment = local(moment)
    floor = moment.replace(minute=moment.minute - moment.minute % SLOT_MINUTES, second=0, microsecond=0)
    return floor if floor == moment else floor + SLOT


def _index(moment: datetime) -> int:
    moment = local(moment)
    return block_index(moment.weekday(), moment.hour * 60 + moment.minute)


def template_open(availability: str, start: datetime, end: datetime) -> bool:
    """Whether every block from `start` (on the grid) to `end` is O in the weekly template."""
    first, count = _index(start), -(-int((end - start).total_seconds()) // (SLOT_MINUTES * 60))
    return all(availability[(first + k) % AVAILABILITY_LENGTH] == SLOT_AVAILABLE for k in range(count))


def overlaps(bookings: Iterable[ScheduleItem], start: datetime, until: datetime) -> bool:
    return any(booking.start_time < until and booking.blocked_until > start for booking in bookings)


def bookings_between(availability_ids: Iterable[int], start: datetime, end: datetime):
    """The bookings of these availabilities that take up any time between `start` and `end`."""
    return ScheduleItem.objects.filter(
        weekly_availability_id__in=list(availability_ids), start_time__lt=end, blocked_until__gt=start
    )


@dataclass(frozen=True)
class Booking:
    """Where a booking of a service starting at `start` would go."""

    start: datetime
    end: datetime  # end of the service
    blocked_until: datetime  # end + buffer


def booking_times(service: Service, start: datetime) -> Booking:
    end = start + timedelta(minutes=service.duration_minutes)
    return Booking(start=start, end=end, blocked_until=end + timedelta(minutes=service.buffer_minutes))


def free_availability(
    service: Service, start: datetime, availabilities: list[WeeklyAvailability], bookings: list[ScheduleItem]
) -> WeeklyAvailability | None:
    """The first of `availabilities` (in order) that can take `service` at `start`, or None.
    `bookings`: their bookings around that time (bookings_between)."""
    times = booking_times(service, start)
    for availability in availabilities:
        if not template_open(availability.availability, times.start, times.end):
            continue
        own = [booking for booking in bookings if booking.weekly_availability_id == availability.pk]
        if not overlaps(own, times.start, times.blocked_until):
            return availability
    return None


def service_availabilities(service: Service, lock: bool = False) -> list[WeeklyAvailability]:
    """The service's weekly availabilities, in pk order (locked with SELECT ... FOR UPDATE if `lock`)."""
    queryset = WeeklyAvailability.objects.filter(services=service, business_id=service.business_id).order_by('pk')
    return list(queryset.select_for_update() if lock else queryset)


def start_problem(service: Service, start: datetime, now: datetime | None = None) -> str | None:
    """Why `service` can't be booked at `start` (a sentence for the customer), or None if it can."""
    now = now or timezone.now()
    if not service.is_active:
        return f'{service.name} is not available for booking at the moment.'
    if not is_on_grid(start):
        return f'Bookings start on the quarter hour (every {SLOT_MINUTES} minutes).'
    if start < now + MIN_NOTICE:
        return 'That time is too soon: bookings must be at least an hour from now.'
    availabilities = service_availabilities(service)
    times = booking_times(service, start)
    bookings = list(bookings_between([a.pk for a in availabilities], times.start, times.blocked_until))
    if free_availability(service, start, availabilities, bookings) is None:
        return f'{format_slot(start)} is not available for {service.name}.'
    return None


def free_slots(service: Service, date_from: date, date_to: date, now: datetime | None = None) -> list[datetime]:
    """Every start time (on the 15-minute grid) from `date_from` to `date_to` (inclusive, local
    dates; at most SLOT_SEARCH_DAYS_MAX days) at which `service` can be booked, in order."""
    now = now or timezone.now()
    date_to = min(date_to, date_from + timedelta(days=SLOT_SEARCH_DAYS_MAX - 1))
    if not service.is_active or date_to < date_from:
        return []
    window_end = local_midnight(date_to + timedelta(days=1))
    start = max(local_midnight(date_from), next_on_grid(now + MIN_NOTICE))
    availabilities = service_availabilities(service)
    if not availabilities or start >= window_end:
        return []
    longest = booking_times(service, window_end).blocked_until
    bookings = list(bookings_between([a.pk for a in availabilities], start, longest))
    slots = []
    moment = start
    while moment < window_end:
        if free_availability(service, moment, availabilities, bookings) is not None:
            slots.append(moment)
        moment += SLOT
    return slots


def week_start(day: date) -> date:
    """The Monday of `day`'s week."""
    return day - timedelta(days=day.weekday())


def week_calendar(availability: WeeklyAvailability, day: date) -> tuple[str, list[ScheduleItem]]:
    """The week of `day` (Monday to Sunday) in `availability`'s calendar: its weekly template with
    that week's bookings drawn over it (H while pending payment, X once paid or completed), and
    those bookings."""
    start = local_midnight(week_start(day))
    end = local_midnight(week_start(day) + timedelta(days=7))
    letters = list(availability.availability)
    bookings = list(bookings_between([availability.pk], start, end).select_related('service').order_by('start_time'))
    for booking in bookings:
        letter = SLOT_TAKEN if booking.order_status in TAKEN_STATUSES else SLOT_ON_HOLD
        moment = max(local(booking.start_time), start)
        moment = moment.replace(minute=moment.minute - moment.minute % SLOT_MINUTES, second=0, microsecond=0)
        while moment < min(booking.blocked_until, end):
            index = _index(moment)
            if letters[index] != SLOT_TAKEN or letter == SLOT_TAKEN:
                letters[index] = letter
            moment += SLOT
    return ''.join(letters), bookings


def format_slot(start: datetime) -> str:
    """A start time for customers, in local time, e.g. "Tue 14 Oct, 2:30pm"."""
    moment = local(start)
    hour = moment.hour % 12 or 12
    minutes = f':{moment.minute:02d}' if moment.minute else ''
    return f'{moment:%a} {moment.day} {moment:%b}, {hour}{minutes}{"am" if moment.hour < 12 else "pm"}'
