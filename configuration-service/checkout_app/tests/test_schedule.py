from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from configuration_app.models import BusinessConfiguration
from product_app.models import Service, ServiceProvider, WeeklyAvailability
from product_app.tests import open_hours

from ..models import OrderStatus, ScheduleItem
from ..services import BookingError, place_booking
from ..schedule import (
    MIN_NOTICE,
    SLOT_SEARCH_DAYS_MAX,
    copy_week,
    format_slot,
    free_slots,
    is_on_grid,
    next_on_grid,
    set_slots,
    start_problem,
    week_calendar,
    week_start,
)

TZ = ZoneInfo('Asia/Singapore')


def future_monday(weeks: int = 2) -> date:
    """A Monday far enough ahead that every slot in tests is bookable (past MIN_NOTICE)."""
    return week_start(timezone.now().astimezone(TZ).date()) + timedelta(weeks=weeks)


def at(day: date, hhmm: str) -> datetime:
    """A local (Singapore) time on `day`."""
    return datetime.combine(day, time(int(hhmm[:2]), int(hhmm[3:])), tzinfo=TZ)


def open_week(provider, monday: date, *ranges) -> WeeklyAvailability:
    """The provider's week of `monday`, with the `(weekday, 'HH:MM', 'HH:MM')` ranges open (O)."""
    week, _ = WeeklyAvailability.objects.update_or_create(
        service_provider=provider, week=monday, defaults={'availability': open_hours(*ranges)}
    )
    return week


def letters(provider, monday: date) -> str:
    """The provider's letters for the week (U if it has none)."""
    week = WeeklyAvailability.objects.filter(service_provider=provider, week=monday).first()
    return week.availability if week else 'U' * 672


def day_letters(provider, day: date, start: str = '00:00', end: str = '24:00') -> str:
    """The provider's letters on `day` between two times, e.g. 'OOHHHH'."""
    week = letters(provider, week_start(day))
    first = day.weekday() * 96 + (int(start[:2]) * 60 + int(start[3:])) // 15
    last = day.weekday() * 96 + (int(end[:2]) * 60 + int(end[3:])) // 15
    return week[first:last]


def book(service, provider, start, status=OrderStatus.PENDING_PAYMENT, **fields):
    """A booking saved straight to the database (not through place_booking): saving it still
    writes it into the provider's week (checkout_app.signals)."""
    end = start + timedelta(minutes=service.duration_minutes)
    return ScheduleItem.objects.create(
        business=service.business,
        service=service,
        service_provider=provider,
        start_time=start,
        end_time=end,
        blocked_until=end + timedelta(minutes=service.buffer_minutes),
        order_status=status,
        schedule_data={
            'service': {
                'service_id': service.pk, 'name': service.name, 'price': str(service.price),
                'duration_minutes': service.duration_minutes, 'buffer_minutes': service.buffer_minutes,
            },
            'details': {},
        },
        **fields,
    )


@override_settings(SCHEDULE_TIME_ZONE='Asia/Singapore')
class GridTests(SimpleTestCase):
    def test_on_grid(self):
        monday = date(2030, 1, 7)
        self.assertTrue(is_on_grid(at(monday, '09:15')))
        self.assertFalse(is_on_grid(at(monday, '09:10')))
        self.assertFalse(is_on_grid(at(monday, '09:15') + timedelta(seconds=1)))
        self.assertTrue(is_on_grid(at(monday, '09:15').astimezone(ZoneInfo('UTC'))))  # same moment

    def test_next_on_grid(self):
        monday = date(2030, 1, 7)
        self.assertEqual(next_on_grid(at(monday, '09:15')), at(monday, '09:15'))
        self.assertEqual(next_on_grid(at(monday, '09:16')), at(monday, '09:30'))
        self.assertEqual(next_on_grid(at(monday, '23:50')), at(monday + timedelta(days=1), '00:00'))

    def test_format_slot(self):
        self.assertEqual(format_slot(at(date(2030, 1, 8), '14:30')), 'Tue 8 Jan, 2:30pm')
        self.assertEqual(format_slot(at(date(2030, 1, 8), '09:00')), 'Tue 8 Jan, 9am')
        self.assertEqual(format_slot(at(date(2030, 1, 8), '00:15')), 'Tue 8 Jan, 12:15am')
        self.assertEqual(format_slot(at(date(2030, 1, 8), '12:00')), 'Tue 8 Jan, 12pm')

    def test_week_start(self):
        self.assertEqual(week_start(date(2030, 1, 10)), date(2030, 1, 7))  # Thursday → Monday
        self.assertEqual(week_start(date(2030, 1, 7)), date(2030, 1, 7))


class StudioCase(TestCase):
    """A studio with two photographers (Mei, Raj), open Monday 09:00–12:00 in the test week."""

    @classmethod
    def setUpTestData(cls):
        cls.studio = BusinessConfiguration.objects.create(business_name='Snap Studio', location='Singapore')
        cls.mei = ServiceProvider.objects.create(business=cls.studio, name='Mei')
        cls.raj = ServiceProvider.objects.create(business=cls.studio, name='Raj')
        cls.portrait = Service.objects.create(business=cls.studio, name='Portrait', price=180, duration_minutes=60)
        cls.portrait.service_providers.set([cls.mei])
        cls.family = Service.objects.create(business=cls.studio, name='Family', price=250, duration_minutes=60, buffer_minutes=30)
        cls.family.service_providers.set([cls.mei, cls.raj])
        cls.monday = future_monday()

    def setUp(self):
        for provider in (self.mei, self.raj):
            open_week(provider, self.monday, (0, '09:00', '12:00'))


@override_settings(SCHEDULE_TIME_ZONE='Asia/Singapore')
class FreeSlotsTests(StudioCase):
    def slots(self, service, day=None, to=None, **kwargs):
        day = day or self.monday
        return [s.astimezone(TZ).strftime('%a %H:%M') for s in free_slots(service, day, to or day, **kwargs)]

    def test_every_quarter_hour_that_fits_the_open_blocks(self):
        self.assertEqual(
            self.slots(self.portrait),
            ['Mon 09:00', 'Mon 09:15', 'Mon 09:30', 'Mon 09:45', 'Mon 10:00', 'Mon 10:15', 'Mon 10:30', 'Mon 10:45', 'Mon 11:00'],
        )
        self.assertEqual(self.slots(self.portrait, self.monday + timedelta(days=1)), [])  # Tuesday: U

    def test_only_open_blocks(self):
        week = open_week(self.mei, self.monday, (0, '09:00', '10:00'), (0, '10:30', '12:00'))
        self.assertEqual(self.slots(self.portrait), ['Mon 09:00', 'Mon 10:30', 'Mon 10:45', 'Mon 11:00'])
        week.delete()  # no week at all: nothing open
        self.assertEqual(self.slots(self.portrait), [])

    def test_a_booking_and_its_buffer_block_the_calendar(self):
        book(self.family, self.mei, at(self.monday, '10:00'))  # 10:00–11:00, blocked until 11:30 (H)
        self.assertEqual(self.slots(self.portrait), ['Mon 09:00'])  # ends by 10:00; from 11:30 it can't fit

    def test_the_new_bookings_buffer_counts_too(self):
        book(self.portrait, self.mei, at(self.monday, '10:30'))
        book(self.portrait, self.raj, at(self.monday, '10:30'))
        # Family (60 min + 30 min buffer): 09:00 is blocked until 10:30, which just fits; 09:15 isn't.
        self.assertEqual(self.slots(self.family), ['Mon 09:00'])

    def test_the_buffer_may_run_past_closing(self):
        self.assertIn('Mon 11:00', self.slots(self.family))  # its buffer, 12:00–12:30, is U
        self.assertNotIn('Mon 11:15', self.slots(self.family))

    def test_any_provider_of_the_service_will_do(self):
        book(self.family, self.mei, at(self.monday, '09:00'))
        book(self.family, self.mei, at(self.monday, '10:30'))
        self.assertEqual(self.slots(self.family)[:2], ['Mon 09:00', 'Mon 09:15'])  # Raj is free
        self.assertEqual(self.slots(self.portrait), [])  # Portrait is Mei's only

    def test_an_inactive_provider_takes_no_bookings(self):
        ServiceProvider.objects.filter(pk=self.mei.pk).update(is_active=False)
        self.assertEqual(self.slots(self.portrait), [])
        self.assertEqual(len(self.slots(self.family)), 9)  # Raj

    def test_every_status_takes_up_time(self):
        for status in OrderStatus.values:
            with self.subTest(status):
                booking = book(self.portrait, self.mei, at(self.monday, '09:00'), status=status)
                self.assertNotIn('Mon 09:00', self.slots(self.portrait))
                booking.delete()
        self.assertIn('Mon 09:00', self.slots(self.portrait))  # deleting a booking frees it

    def test_other_businesses_and_providers_dont_matter(self):
        other = BusinessConfiguration.objects.create(business_name='Other', location='Singapore')
        them = ServiceProvider.objects.create(business=other, name='Them')
        open_week(them, self.monday, (0, '09:00', '12:00'))
        their_service = Service.objects.create(business=other, name='Portrait', price=1, duration_minutes=60)
        book(their_service, them, at(self.monday, '09:00'))
        book(self.family, self.raj, at(self.monday, '09:00'))  # Raj doesn't do Portrait
        self.assertIn('Mon 09:00', self.slots(self.portrait))

    def test_nothing_for_an_inactive_service_or_one_without_providers(self):
        self.portrait.is_active = False
        self.assertEqual(self.slots(self.portrait), [])
        solo = Service.objects.create(business=self.studio, name='Solo', price=1, duration_minutes=15)
        self.assertEqual(self.slots(solo), [])

    def test_minimum_notice(self):
        self.assertEqual(self.slots(self.portrait, now=at(self.monday, '09:20'))[0], 'Mon 10:30')
        self.assertEqual(self.slots(self.portrait, now=at(self.monday, '12:00')), [])
        self.assertEqual(MIN_NOTICE, timedelta(hours=1))

    def test_several_weeks_and_the_limit(self):
        open_week(self.mei, self.monday + timedelta(weeks=1), (0, '09:00', '10:00'))
        slots = free_slots(self.portrait, self.monday, self.monday + timedelta(days=13))
        self.assertEqual(len(slots), 10)  # 9 this Monday, 1 next Monday
        self.assertEqual(slots[-1], at(self.monday + timedelta(weeks=1), '09:00'))
        far = free_slots(self.portrait, self.monday, self.monday + timedelta(days=400))
        self.assertLess(far[-1].astimezone(TZ).date(), self.monday + timedelta(days=SLOT_SEARCH_DAYS_MAX))
        self.assertEqual(free_slots(self.portrait, self.monday, self.monday - timedelta(days=1)), [])

    def test_start_problem(self):
        self.assertIsNone(start_problem(self.portrait, at(self.monday, '09:00')))
        book(self.portrait, self.mei, at(self.monday, '09:00'))
        self.assertIn('is not available for Portrait', start_problem(self.portrait, at(self.monday, '09:30')))
        self.assertIn('on the quarter hour', start_problem(self.portrait, at(self.monday, '10:10')))
        self.assertIn('too soon', start_problem(self.portrait, next_on_grid(timezone.now() + timedelta(minutes=30))))
        self.assertIn('is not available for Portrait', start_problem(self.portrait, at(self.monday, '13:00')))
        self.portrait.is_active = False
        self.assertIn('not available for booking at the moment', start_problem(self.portrait, at(self.monday, '10:00')))


@override_settings(SCHEDULE_TIME_ZONE='Asia/Singapore')
class BookingLettersTests(StudioCase):
    """A booking writes itself into its provider's week: O → H (pending payment) → X (paid / done),
    and back to O when it's deleted or moved."""

    def mon(self, provider=None, start='08:45', end='12:30'):
        return day_letters(provider or self.mei, self.monday, start, end)

    def test_a_pending_booking_puts_its_blocks_on_hold(self):
        self.assertEqual(self.mon(), 'U' + 'O' * 12 + 'UU')
        book(self.family, self.mei, at(self.monday, '09:00'))  # 09:00–10:00, buffer to 10:30
        self.assertEqual(self.mon(), 'U' + 'HHHH' + 'HH' + 'O' * 6 + 'UU')
        self.assertEqual(self.mon(self.raj), 'U' + 'O' * 12 + 'UU')  # Raj's week is untouched

    def test_the_buffer_over_closed_blocks_stays_closed(self):
        book(self.family, self.mei, at(self.monday, '11:00'))  # 11:00–12:00, buffer 12:00–12:30 is U
        self.assertEqual(self.mon(), 'U' + 'O' * 8 + 'HHHH' + 'UU')

    def test_paid_and_completed_are_booked(self):
        booking = book(self.family, self.mei, at(self.monday, '09:00'))
        for status, letter in (
            (OrderStatus.PAYMENT_RECEIVED, 'X'), (OrderStatus.ORDER_COMPLETED, 'X'), (OrderStatus.PENDING_PAYMENT, 'H'),
        ):
            with self.subTest(status):
                booking.order_status = status
                booking.save()
                self.assertEqual(self.mon(), 'U' + letter * 6 + 'O' * 6 + 'UU')
        paid = book(self.portrait, self.mei, at(self.monday, '10:30'), status=OrderStatus.PAYMENT_RECEIVED)
        self.assertEqual(self.mon(start='10:30', end='11:30'), 'XXXX')  # booked straight away as paid
        self.assertEqual(paid.order_status, OrderStatus.PAYMENT_RECEIVED)

    def test_deleting_frees_the_blocks(self):
        booking = book(self.family, self.mei, at(self.monday, '11:00'))
        booking.delete()
        self.assertEqual(self.mon(), 'U' + 'O' * 12 + 'UU')  # the closed buffer stayed U
        book(self.family, self.mei, at(self.monday, '09:00'), status=OrderStatus.ORDER_COMPLETED)
        ScheduleItem.objects.all().delete()  # a queryset delete too
        self.assertEqual(self.mon(), 'U' + 'O' * 12 + 'UU')

    def test_moving_a_booking_frees_its_old_time(self):
        booking = book(self.portrait, self.mei, at(self.monday, '09:00'))
        booking.start_time, booking.end_time, booking.blocked_until = (
            at(self.monday, '10:00'), at(self.monday, '11:00'), at(self.monday, '11:00'),
        )
        booking.save()
        self.assertEqual(self.mon(start='09:00', end='12:00'), 'OOOO' + 'HHHH' + 'OOOO')
        booking.service_provider = self.raj  # to the other photographer
        booking.save()
        self.assertEqual(self.mon(self.mei, start='09:00', end='12:00'), 'O' * 12)
        self.assertEqual(self.mon(self.raj, start='09:00', end='12:00'), 'OOOO' + 'HHHH' + 'OOOO')

    def test_a_booking_across_two_weeks(self):
        sunday = self.monday - timedelta(days=1)
        open_week(self.mei, week_start(sunday), (6, '23:00', '24:00'))
        open_week(self.mei, self.monday, (0, '00:00', '01:00'))
        book(self.family, self.mei, at(sunday, '23:30'))  # 23:30–00:30, buffer to 01:00
        self.assertEqual(day_letters(self.mei, sunday, '23:00', '24:00'), 'OOHH')
        self.assertEqual(day_letters(self.mei, self.monday, '00:00', '01:15'), 'HHHHU')

    def test_a_week_without_a_row_gets_one(self):
        # E.g. a booking made in Django Admin at a time that was never opened: it still shows.
        tuesday = self.monday + timedelta(days=8)
        self.assertFalse(WeeklyAvailability.objects.filter(service_provider=self.mei, week=week_start(tuesday)).exists())
        book(self.portrait, self.mei, at(tuesday, '09:00'))
        self.assertEqual(day_letters(self.mei, tuesday, '08:45', '10:15'), 'UHHHHU')

    def test_deleting_the_business_with_bookings(self):
        book(self.family, self.mei, at(self.monday, '09:00'))
        self.studio.delete()
        self.assertFalse(WeeklyAvailability.objects.exists())
        self.assertFalse(ScheduleItem.objects.exists())

    def test_deleting_a_provider_keeps_its_bookings(self):
        booking = book(self.family, self.mei, at(self.monday, '09:00'))
        self.mei.delete()
        booking.refresh_from_db()
        self.assertIsNone(booking.service_provider)
        booking.save()  # with no provider, nothing to write
        booking.delete()


@override_settings(SCHEDULE_TIME_ZONE='Asia/Singapore')
class WeekCalendarTests(StudioCase):
    def test_the_week_and_its_bookings(self):
        first = book(self.family, self.mei, at(self.monday, '09:00'))
        second = book(self.family, self.mei, at(self.monday, '11:00'), status=OrderStatus.PAYMENT_RECEIVED)
        book(self.family, self.raj, at(self.monday, '10:30'))  # Raj's: not listed
        book(self.family, self.mei, at(self.monday + timedelta(days=7), '09:00'))  # next week: not listed
        row, bookings = week_calendar(self.mei, self.monday + timedelta(days=3))  # any day of the week
        self.assertEqual(row.week, self.monday)
        self.assertEqual(bookings, [first, second])
        self.assertEqual(row.availability[36:50], 'HHHHHH' + 'OO' + 'XXXX' + 'UU')

    def test_a_week_without_a_row(self):
        row, bookings = week_calendar(self.mei, self.monday + timedelta(weeks=5))
        self.assertIsNone(row)
        self.assertEqual(bookings, [])


@override_settings(SCHEDULE_TIME_ZONE='Asia/Singapore')
class SetSlotsTests(StudioCase):
    def test_next_two_weeks_monday_to_friday_9_to_5(self):
        start = self.monday + timedelta(weeks=1)
        change = set_slots(self.mei, start, start + timedelta(days=13), range(5), time(9), time(17))
        self.assertEqual((change.changed, change.skipped), (2 * 5 * 32, 0))
        self.assertEqual([w.week for w in change.weeks], [start, start + timedelta(weeks=1)])
        for week in change.weeks:
            week.refresh_from_db()
            self.assertEqual(week.availability, open_hours(*[(day, '09:00', '17:00') for day in range(5)]))
        # Again: nothing to change.
        self.assertEqual(set_slots(self.mei, start, start + timedelta(days=13), range(5), time(9), time(17)).changed, 0)

    def test_adds_to_an_existing_week_and_until_midnight(self):
        change = set_slots(self.mei, self.monday + timedelta(days=5), self.monday + timedelta(days=6), [5, 6], time(20), None)
        self.assertEqual(change.changed, 2 * 16)
        week = letters(self.mei, self.monday)
        self.assertEqual(week, open_hours((0, '09:00', '12:00'), (5, '20:00', '24:00'), (6, '20:00', '24:00')))

    def test_a_range_starting_mid_week_only_changes_those_days(self):
        wednesday = self.monday + timedelta(days=2)
        set_slots(self.mei, wednesday, wednesday + timedelta(days=6), [0, 2], time(9), time(10))
        self.assertEqual(day_letters(self.mei, wednesday, '09:00', '10:00'), 'OOOO')
        self.assertEqual(day_letters(self.mei, self.monday, '09:00', '10:00'), 'OOOO')  # already open
        self.assertEqual(day_letters(self.mei, self.monday + timedelta(weeks=1), '09:00', '10:00'), 'OOOO')  # next Monday
        self.assertEqual(day_letters(self.mei, wednesday + timedelta(weeks=1), '09:00', '10:00'), 'UUUU')  # past date_to

    def test_closing_leaves_bookings_alone(self):
        book(self.family, self.mei, at(self.monday, '10:00'))  # 10:00–11:30 H
        change = set_slots(self.mei, self.monday, self.monday, [0], time(9), time(12), available=False)
        self.assertEqual((change.changed, change.skipped), (6, 6))
        self.assertEqual(day_letters(self.mei, self.monday, '09:00', '12:00'), 'UUUU' + 'HHHHHH' + 'UU')

    def test_opening_leaves_bookings_alone(self):
        book(self.family, self.mei, at(self.monday, '10:00'))
        change = set_slots(self.mei, self.monday, self.monday, [0], time(8), time(13))
        self.assertEqual((change.changed, change.skipped), (8, 6))
        self.assertEqual(day_letters(self.mei, self.monday, '08:00', '13:00'), 'O' * 8 + 'H' * 6 + 'O' * 6)

    def test_then_bookable(self):
        nxt = self.monday + timedelta(weeks=1)
        self.assertEqual(free_slots(self.portrait, nxt, nxt), [])
        set_slots(self.mei, nxt, nxt, [0], time(14), time(16))
        self.assertEqual([s.astimezone(TZ).strftime('%H:%M') for s in free_slots(self.portrait, nxt, nxt)],
                         ['14:00', '14:15', '14:30', '14:45', '15:00'])


@override_settings(SCHEDULE_TIME_ZONE='Asia/Singapore')
class CopyWeekTests(StudioCase):
    def test_copies_to_the_next_weeks(self):
        book(self.family, self.mei, at(self.monday, '09:00'))  # booked in the source: copied as open
        targets = [self.monday + timedelta(weeks=n) for n in (1, 2, 3)]
        change = copy_week(self.mei, self.monday, targets)
        self.assertEqual([w.week for w in change.weeks], targets)
        self.assertEqual(change.changed, 3 * 12)
        for monday in targets:
            self.assertEqual(letters(self.mei, monday), open_hours((0, '09:00', '12:00')))

    def test_bookings_in_the_target_stay(self):
        nxt = self.monday + timedelta(weeks=1)
        open_week(self.mei, nxt, (0, '13:00', '15:00'))
        book(self.portrait, self.mei, at(nxt, '13:00'))  # H 13:00–14:00
        change = copy_week(self.mei, self.monday, [nxt])
        self.assertEqual(change.skipped, 4)  # the source is closed there, but it's booked
        self.assertEqual(day_letters(self.mei, nxt, '09:00', '15:00'), 'O' * 12 + 'UUUU' + 'HHHH' + 'UUUU')

    def test_an_empty_source_week_closes_the_targets(self):
        empty = self.monday + timedelta(weeks=4)
        change = copy_week(self.mei, empty, [self.monday])
        self.assertEqual(change.changed, 12)
        self.assertEqual(letters(self.mei, self.monday), 'U' * 672)

    def test_the_source_itself_is_skipped(self):
        self.assertEqual(copy_week(self.mei, self.monday, [self.monday]).weeks, [])


@override_settings(SCHEDULE_TIME_ZONE='Asia/Singapore')
class StartIntervalTests(StudioCase):
    """Service.start_interval_minutes: bookings only start every N minutes from local midnight.
    The user's example: a 1-hour service, available 09:00 to 11:00."""

    def setUp(self):
        for provider in (self.mei, self.raj):
            open_week(provider, self.monday, (0, '09:00', '11:00'))

    def slots(self, interval):
        self.portrait.start_interval_minutes = interval
        return [s.astimezone(TZ).strftime('%H:%M') for s in free_slots(self.portrait, self.monday, self.monday)]

    def test_every_15_minutes_by_default(self):
        self.assertEqual(Service(business=self.studio, name='X', price=1, duration_minutes=60).start_interval_minutes, 15)
        self.assertEqual(self.slots(15), ['09:00', '09:15', '09:30', '09:45', '10:00'])
        self.assertIsNone(start_problem(self.portrait, at(self.monday, '09:15')))  # 9:15 to 10:15

    def test_every_30_minutes(self):
        self.assertEqual(self.slots(30), ['09:00', '09:30', '10:00'])

    def test_every_hour(self):
        self.assertEqual(self.slots(60), ['09:00', '10:00'])

    def test_a_custom_interval_counts_from_midnight(self):
        self.assertEqual(self.slots(45), ['09:00', '09:45'])  # 9:00 is 12 × 45 min after midnight; 10:30 ends too late
        open_week(self.mei, self.monday, (0, '08:00', '12:00'))
        self.assertEqual(self.slots(120), ['08:00', '10:00'])

    def test_a_start_off_the_interval_is_explained(self):
        self.portrait.start_interval_minutes = 30
        self.assertEqual(
            start_problem(self.portrait, at(self.monday, '09:15')),
            'Portrait can only start every 30 minutes (for example 9am or 9:30am).',
        )
        self.assertIsNone(start_problem(self.portrait, at(self.monday, '09:30')))
        self.portrait.start_interval_minutes = 60
        self.assertEqual(
            start_problem(self.portrait, at(self.monday, '09:45')),
            'Portrait can only start every hour (for example 9am or 10am).',
        )
        self.portrait.start_interval_minutes = 120
        self.assertIn('every 2 hours (for example 8am or 10am)', start_problem(self.portrait, at(self.monday, '09:00')))

    def test_placing_a_booking_off_the_interval_is_refused(self):
        self.portrait.start_interval_minutes = 60
        self.portrait.save()
        with self.assertRaises(BookingError) as ctx:
            place_booking(self.studio, self.portrait.pk, at(self.monday, '09:30'), {'name': 'Alice'})
        self.assertEqual(ctx.exception.problems, ['Portrait can only start every hour (for example 9am or 10am).'])
        self.assertFalse(ScheduleItem.objects.exists())
        booking = place_booking(self.studio, self.portrait.pk, at(self.monday, '10:00'), {'name': 'Alice'})
        self.assertEqual(booking.start_time, at(self.monday, '10:00'))

    def test_validation(self):
        def service(minutes):
            return Service(business=self.studio, name='S', price=1, duration_minutes=60, start_interval_minutes=minutes)

        for minutes in (15, 30, 45, 60, 90, 1440):
            with self.subTest(minutes=minutes):
                service(minutes).full_clean()
        for minutes in (0, 10, 20, 1455):
            with self.subTest(minutes=minutes), self.assertRaises(ValidationError) as ctx:
                service(minutes).full_clean()
            self.assertIn('start_interval_minutes', ctx.exception.message_dict)
        with self.assertRaises(IntegrityError), transaction.atomic():
            service(0).save()
