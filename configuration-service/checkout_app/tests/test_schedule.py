from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from configuration_app.models import BusinessConfiguration
from product_app.models import Service, WeeklyAvailability
from product_app.tests import open_hours

from ..models import OrderStatus, ScheduleItem
from ..schedule import (
    MIN_NOTICE,
    SLOT_SEARCH_DAYS_MAX,
    format_slot,
    free_slots,
    is_on_grid,
    next_on_grid,
    start_problem,
    template_open,
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


def book(service, availability, start, status=OrderStatus.PENDING_PAYMENT, **fields):
    """A booking saved straight to the database (not through place_booking)."""
    end = start + timedelta(minutes=service.duration_minutes)
    return ScheduleItem.objects.create(
        business=service.business,
        service=service,
        weekly_availability=availability,
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

    def test_template_open(self):
        week = open_hours((0, '09:00', '12:00'), (6, '22:00', '24:00'))
        monday = date(2030, 1, 7)
        self.assertTrue(template_open(week, at(monday, '09:00'), at(monday, '12:00')))
        self.assertTrue(template_open(week, at(monday, '11:45'), at(monday, '12:00')))
        self.assertFalse(template_open(week, at(monday, '11:45'), at(monday, '12:15')))  # runs past closing
        self.assertFalse(template_open(week, at(monday, '08:45'), at(monday, '09:30')))
        # Sunday night into Monday morning wraps round the week.
        sunday = monday + timedelta(days=6)
        self.assertTrue(template_open(week, at(sunday, '23:00'), at(sunday, '23:45')))
        self.assertFalse(template_open(week, at(sunday, '23:30'), at(sunday, '23:30') + timedelta(hours=1)))
        self.assertTrue(template_open(open_hours((6, '23:00', '24:00'), (0, '00:00', '01:00')),
                                      at(sunday, '23:30'), at(sunday, '23:30') + timedelta(hours=1)))

    def test_on_hold_and_taken_blocks_are_not_bookable(self):
        monday = date(2030, 1, 7)
        for letter in ('X', 'H'):
            week = open_hours((0, '10:00', '11:00'), letter=letter, base=open_hours((0, '09:00', '12:00')))
            with self.subTest(letter):
                self.assertFalse(template_open(week, at(monday, '09:30'), at(monday, '10:30')))
                self.assertTrue(template_open(week, at(monday, '09:00'), at(monday, '10:00')))

    def test_blocks_are_local_time(self):
        week = open_hours((0, '09:00', '10:00'))
        monday = date(2030, 1, 7)
        utc_start = datetime(2030, 1, 7, 1, 0, tzinfo=ZoneInfo('UTC'))  # 09:00 in Singapore
        self.assertTrue(template_open(week, utc_start, utc_start + timedelta(hours=1)))
        with override_settings(SCHEDULE_TIME_ZONE='UTC'):
            self.assertFalse(template_open(week, utc_start, utc_start + timedelta(hours=1)))
            self.assertTrue(template_open(week, datetime(2030, 1, 7, 9, tzinfo=ZoneInfo('UTC')), datetime(2030, 1, 7, 10, tzinfo=ZoneInfo('UTC'))))
        self.assertEqual(at(monday, '09:00'), utc_start)

    def test_format_slot(self):
        self.assertEqual(format_slot(at(date(2030, 1, 8), '14:30')), 'Tue 8 Jan, 2:30pm')
        self.assertEqual(format_slot(at(date(2030, 1, 8), '09:00')), 'Tue 8 Jan, 9am')
        self.assertEqual(format_slot(at(date(2030, 1, 8), '00:15')), 'Tue 8 Jan, 12:15am')
        self.assertEqual(format_slot(at(date(2030, 1, 8), '12:00')), 'Tue 8 Jan, 12pm')

    def test_week_start(self):
        self.assertEqual(week_start(date(2030, 1, 10)), date(2030, 1, 7))  # Thursday → Monday
        self.assertEqual(week_start(date(2030, 1, 7)), date(2030, 1, 7))


@override_settings(SCHEDULE_TIME_ZONE='Asia/Singapore')
class FreeSlotsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.studio = BusinessConfiguration.objects.create(business_name='Snap Studio', location='Singapore')
        # Monday 09:00–12:00 for both photographers.
        cls.mei = WeeklyAvailability.objects.create(business=cls.studio, name='Mei', availability=open_hours((0, '09:00', '12:00')))
        cls.raj = WeeklyAvailability.objects.create(business=cls.studio, name='Raj', availability=open_hours((0, '09:00', '12:00')))
        cls.portrait = Service.objects.create(business=cls.studio, name='Portrait', price=180, duration_minutes=60)
        cls.portrait.weekly_availability.set([cls.mei])
        cls.family = Service.objects.create(business=cls.studio, name='Family', price=250, duration_minutes=60, buffer_minutes=30)
        cls.family.weekly_availability.set([cls.mei, cls.raj])
        cls.monday = future_monday()

    def slots(self, service, day=None, to=None, **kwargs):
        day = day or self.monday
        return [s.astimezone(TZ).strftime('%a %H:%M') for s in free_slots(service, day, to or day, **kwargs)]

    def test_every_quarter_hour_that_fits(self):
        self.assertEqual(
            self.slots(self.portrait),
            ['Mon 09:00', 'Mon 09:15', 'Mon 09:30', 'Mon 09:45', 'Mon 10:00', 'Mon 10:15', 'Mon 10:30', 'Mon 10:45', 'Mon 11:00'],
        )
        self.assertEqual(self.slots(self.portrait, self.monday + timedelta(days=1)), [])  # closed on Tuesday

    def test_a_booking_and_its_buffer_block_the_calendar(self):
        book(self.family, self.mei, at(self.monday, '10:00'))  # 10:00–11:00, blocked until 11:30
        # Portrait (Mei only, no buffer): must end by 10:00, or start from 11:30 (too late to fit).
        self.assertEqual(self.slots(self.portrait), ['Mon 09:00'])

    def test_the_new_bookings_buffer_counts_too(self):
        book(self.portrait, self.mei, at(self.monday, '10:30'))  # 10:30–11:30, no buffer
        book(self.portrait, self.raj, at(self.monday, '10:30'))
        # Family (60 min + 30 min buffer): 09:00 would be blocked until 10:30, which just fits;
        # 09:15 would be blocked until 10:45, over the 10:30 booking.
        self.assertEqual(self.slots(self.family), ['Mon 09:00'])

    def test_the_buffer_may_run_past_closing(self):
        # 11:00–12:00 fits the open hours; the 30-minute buffer after it is outside them.
        self.assertIn('Mon 11:00', self.slots(self.family))
        self.assertNotIn('Mon 11:15', self.slots(self.family))

    def test_any_availability_of_the_service_will_do(self):
        book(self.family, self.mei, at(self.monday, '09:00'))
        book(self.family, self.mei, at(self.monday, '10:30'))
        # Mei is full, but Raj (who also does Family) is free.
        self.assertEqual(self.slots(self.family)[:2], ['Mon 09:00', 'Mon 09:15'])
        # Portrait is Mei's only: nothing left.
        self.assertEqual(self.slots(self.portrait), [])

    def test_every_status_takes_up_time(self):
        for status in OrderStatus.values:
            with self.subTest(status):
                booking = book(self.portrait, self.mei, at(self.monday, '09:00'), status=status)
                self.assertNotIn('Mon 09:00', self.slots(self.portrait))
                booking.delete()
        self.assertIn('Mon 09:00', self.slots(self.portrait))  # deleting a booking frees it

    def test_other_businesses_and_calendars_dont_matter(self):
        other = BusinessConfiguration.objects.create(business_name='Other', location='Singapore')
        theirs = WeeklyAvailability.objects.create(business=other, name='Them', availability=open_hours((0, '09:00', '12:00')))
        their_service = Service.objects.create(business=other, name='Portrait', price=1, duration_minutes=60)
        book(their_service, theirs, at(self.monday, '09:00'))
        book(self.family, self.raj, at(self.monday, '09:00'))  # Raj doesn't do Portrait
        self.assertIn('Mon 09:00', self.slots(self.portrait))

    def test_nothing_for_an_inactive_service_or_one_without_availabilities(self):
        self.portrait.is_active = False
        self.assertEqual(self.slots(self.portrait), [])
        solo = Service.objects.create(business=self.studio, name='Solo', price=1, duration_minutes=15)
        self.assertEqual(self.slots(solo), [])

    def test_minimum_notice(self):
        now = at(self.monday, '09:20')
        self.assertEqual(self.slots(self.portrait, now=now)[0], 'Mon 10:30')  # 09:20 + 1 hour, rounded up
        self.assertEqual(self.slots(self.portrait, now=at(self.monday, '12:00')), [])
        self.assertEqual(MIN_NOTICE, timedelta(hours=1))

    def test_several_days_and_the_limit(self):
        slots = free_slots(self.portrait, self.monday, self.monday + timedelta(days=13))
        self.assertEqual(len(slots), 18)  # two Mondays
        self.assertEqual(slots[9].astimezone(TZ).date(), self.monday + timedelta(days=7))
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
class WeekCalendarTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.studio = BusinessConfiguration.objects.create(business_name='Snap Studio', location='Singapore')
        cls.mei = WeeklyAvailability.objects.create(business=cls.studio, name='Mei', availability=open_hours((0, '09:00', '12:00')))
        cls.raj = WeeklyAvailability.objects.create(business=cls.studio, name='Raj', availability=open_hours((0, '09:00', '12:00')))
        cls.family = Service.objects.create(business=cls.studio, name='Family', price=250, duration_minutes=60, buffer_minutes=30)
        cls.monday = future_monday()

    def test_bookings_drawn_over_the_template(self):
        pending = book(self.family, self.mei, at(self.monday, '09:00'))  # 09:00–10:30 with its buffer
        paid = book(self.family, self.mei, at(self.monday, '11:00'), status=OrderStatus.PAYMENT_RECEIVED)  # 11:00–12:30
        book(self.family, self.raj, at(self.monday, '10:30'))  # Raj's: not drawn
        book(self.family, self.mei, at(self.monday + timedelta(days=7), '09:00'))  # next week: not drawn
        letters, bookings = week_calendar(self.mei, self.monday + timedelta(days=3))  # any day of the week
        monday = letters[:96]
        self.assertEqual(monday[36:42], 'HHHHHH')  # 09:00–10:30 on hold
        self.assertEqual(monday[42:44], 'OO')  # 10:30–11:00 still free
        self.assertEqual(monday[44:48], 'XXXX')  # 11:00–12:00 taken
        self.assertEqual(monday[48:50], 'XX')  # the buffer after closing: the template's X stays
        self.assertEqual(letters[96:], self.mei.availability[96:])
        self.assertEqual(bookings, [pending, paid])
        # The stored template itself never changes.
        self.mei.refresh_from_db()
        self.assertEqual(self.mei.availability, open_hours((0, '09:00', '12:00')))

    def test_a_booking_over_the_week_boundary(self):
        sunday = self.monday - timedelta(days=1)
        week = open_hours((6, '23:00', '24:00'), (0, '00:00', '01:00'))
        self.mei.availability = week
        self.mei.save()
        book(self.family, self.mei, at(sunday, '23:30'))  # Sunday 23:30 → Monday 01:00 (with buffer)
        this_week, _ = week_calendar(self.mei, self.monday)
        self.assertEqual(this_week[:4], 'HHHH')  # Monday 00:00–01:00
        last_week, _ = week_calendar(self.mei, sunday)
        self.assertEqual(last_week[-2:], 'HH')  # Sunday 23:30–24:00
