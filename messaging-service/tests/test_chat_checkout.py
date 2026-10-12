"""A port of configuration-service's checkout_app/tests/test_schedule.py and test_services.py: the
parts the port contains (free times, start problems, start intervals, painting bookings into the
weeks, place_booking and place_order). Django-only parts (set_slots, copy_week, week_calendar,
model validation, the delete / move signals, cascades) aren't ported.
"""

import unittest
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch
from zoneinfo import ZoneInfo

from sqlalchemy import delete, event, update

from app import config
from app.chat_flow import dates
from app.chat_flow.checkout import BookingError, OrderError, place_booking, place_order, validate_schedule_data
from app.chat_flow.schedule import (
    MIN_NOTICE,
    ORDER_COMPLETED,
    PAYMENT_FAILED,
    PAYMENT_RECEIVED,
    PENDING_PAYMENT,
    SLOT_SEARCH_DAYS_MAX,
    format_slot,
    free_slots,
    is_on_grid,
    next_on_grid,
    start_problem,
    sync_booking,
    week_start,
)
from app.chat_flow.stock import Stock, ordered_quantities
from app.models import OrderItem, Product, ScheduleItem, Service, ServiceProvider, WeeklyAvailability

from .chat_helpers import DatabaseTestCase
from .schedule_helpers import TZ, at, book, day_letters, future_monday, open_week

ORDER_STATUSES = (PENDING_PAYMENT, PAYMENT_RECEIVED, ORDER_COMPLETED, PAYMENT_FAILED)  # OrderStatus.values


def singapore_time(test):
    """override_settings(SCHEDULE_TIME_ZONE='Asia/Singapore')."""
    patcher = patch.object(config, 'SCHEDULE_TIME_ZONE', 'Asia/Singapore')
    patcher.start()
    test.addCleanup(patcher.stop)


def set_status(sessions, booking, status) -> ScheduleItem:
    """booking.order_status = status; booking.save() (Django's post_save signal repaints the week)."""
    with sessions.begin() as db:
        row = db.get(ScheduleItem, booking.id)
        row.order_status = status
        sync_booking(db, row)
    return row


def delete_booking(sessions, booking) -> None:
    """booking.delete(), with Django's post_delete signal (release_booking: its H / X back to O),
    done here by painting it as payment failed (the same release) before deleting the row."""
    with sessions.begin() as db:
        row = db.get(ScheduleItem, booking.id)
        row.order_status = PAYMENT_FAILED
        sync_booking(db, row)
        db.delete(row)


# --- test_schedule.py ---------------------------------------------------------------------------

class GridTests(unittest.TestCase):
    def setUp(self):
        singapore_time(self)

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


class StudioCase(DatabaseTestCase):
    """A studio with two photographers (Mei, Raj), open Monday 09:00–12:00 in the test week."""

    def setUp(self):
        super().setUp()
        singapore_time(self)
        self.studio = self.make.business('Snap Studio')
        self.mei = self.make.provider(self.studio, 'Mei')
        self.raj = self.make.provider(self.studio, 'Raj')
        self.portrait = self.make.service(self.studio, 'Portrait', [self.mei], price='180', duration_minutes=60)
        self.family = self.make.service(self.studio, 'Family', [self.mei, self.raj], price='250', duration_minutes=60, buffer_minutes=30)
        self.monday = future_monday()
        self.open_test_week()

    def open_test_week(self):
        for provider in (self.mei, self.raj):
            open_week(self.sessions, provider, self.monday, (0, '09:00', '12:00'))

    def free_slots(self, service, date_from, date_to, **kwargs):
        with self.sessions() as db:
            return free_slots(db, service, date_from, date_to, **kwargs)

    def start_problem(self, service, start, **kwargs):
        with self.sessions() as db:
            return start_problem(db, service, start, **kwargs)

    def book(self, service, provider, start, status=PENDING_PAYMENT, **fields):
        return book(self.sessions, service, provider, start, status, **fields)


class FreeSlotsTests(StudioCase):
    def slots(self, service, day=None, to=None, **kwargs):
        day = day or self.monday
        return [s.astimezone(TZ).strftime('%a %H:%M') for s in self.free_slots(service, day, to or day, **kwargs)]

    def test_every_quarter_hour_that_fits_the_open_blocks(self):
        self.assertEqual(
            self.slots(self.portrait),
            ['Mon 09:00', 'Mon 09:15', 'Mon 09:30', 'Mon 09:45', 'Mon 10:00', 'Mon 10:15', 'Mon 10:30', 'Mon 10:45', 'Mon 11:00'],
        )
        self.assertEqual(self.slots(self.portrait, self.monday + timedelta(days=1)), [])  # Tuesday: U

    def test_only_open_blocks(self):
        week = open_week(self.sessions, self.mei, self.monday, (0, '09:00', '10:00'), (0, '10:30', '12:00'))
        self.assertEqual(self.slots(self.portrait), ['Mon 09:00', 'Mon 10:30', 'Mon 10:45', 'Mon 11:00'])
        with self.sessions.begin() as db:  # no week at all: nothing open
            db.execute(delete(WeeklyAvailability).where(WeeklyAvailability.id == week.id))
        self.assertEqual(self.slots(self.portrait), [])

    def test_a_booking_and_its_buffer_block_the_calendar(self):
        self.book(self.family, self.mei, at(self.monday, '10:00'))  # 10:00–11:00, blocked until 11:30 (H)
        self.assertEqual(self.slots(self.portrait), ['Mon 09:00'])  # ends by 10:00; from 11:30 it can't fit

    def test_the_new_bookings_buffer_counts_too(self):
        self.book(self.portrait, self.mei, at(self.monday, '10:30'))
        self.book(self.portrait, self.raj, at(self.monday, '10:30'))
        # Family (60 min + 30 min buffer): 09:00 is blocked until 10:30, which just fits; 09:15 isn't.
        self.assertEqual(self.slots(self.family), ['Mon 09:00'])

    def test_the_buffer_may_run_past_closing(self):
        self.assertIn('Mon 11:00', self.slots(self.family))  # its buffer, 12:00–12:30, is U
        self.assertNotIn('Mon 11:15', self.slots(self.family))

    def test_any_provider_of_the_service_will_do(self):
        self.book(self.family, self.mei, at(self.monday, '09:00'))
        self.book(self.family, self.mei, at(self.monday, '10:30'))
        self.assertEqual(self.slots(self.family)[:2], ['Mon 09:00', 'Mon 09:15'])  # Raj is free
        self.assertEqual(self.slots(self.portrait), [])  # Portrait is Mei's only

    def test_an_inactive_provider_takes_no_bookings(self):
        with self.sessions.begin() as db:
            db.execute(update(ServiceProvider).where(ServiceProvider.id == self.mei.id).values(is_active=False))
        self.assertEqual(self.slots(self.portrait), [])
        self.assertEqual(len(self.slots(self.family)), 9)  # Raj

    def test_every_status_takes_up_time_except_a_failed_payment(self):
        failed = self.book(self.portrait, self.mei, at(self.monday, '09:00'), status=PAYMENT_FAILED)
        self.assertIn('Mon 09:00', self.slots(self.portrait))
        delete_booking(self.sessions, failed)
        for status in set(ORDER_STATUSES) - {PAYMENT_FAILED}:
            with self.subTest(status):
                booking = self.book(self.portrait, self.mei, at(self.monday, '09:00'), status=status)
                self.assertNotIn('Mon 09:00', self.slots(self.portrait))
                delete_booking(self.sessions, booking)
        self.assertIn('Mon 09:00', self.slots(self.portrait))  # deleting a booking frees it

    def test_other_businesses_and_providers_dont_matter(self):
        other = self.make.business('Other')
        them = self.make.provider(other, 'Them')
        open_week(self.sessions, them, self.monday, (0, '09:00', '12:00'))
        their_service = self.make.service(other, 'Portrait', price='1', duration_minutes=60)
        self.book(their_service, them, at(self.monday, '09:00'))
        self.book(self.family, self.raj, at(self.monday, '09:00'))  # Raj doesn't do Portrait
        self.assertIn('Mon 09:00', self.slots(self.portrait))

    def test_nothing_for_an_inactive_service_or_one_without_providers(self):
        self.portrait.is_active = False
        self.assertEqual(self.slots(self.portrait), [])
        solo = self.make.service(self.studio, 'Solo', price='1', duration_minutes=15)
        self.assertEqual(self.slots(solo), [])

    def test_minimum_notice(self):
        self.assertEqual(self.slots(self.portrait, now=at(self.monday, '09:20'))[0], 'Mon 10:30')
        self.assertEqual(self.slots(self.portrait, now=at(self.monday, '12:00')), [])
        self.assertEqual(MIN_NOTICE, timedelta(hours=1))

    def test_several_weeks_and_the_limit(self):
        open_week(self.sessions, self.mei, self.monday + timedelta(weeks=1), (0, '09:00', '10:00'))
        slots = self.free_slots(self.portrait, self.monday, self.monday + timedelta(days=13))
        self.assertEqual(len(slots), 10)  # 9 this Monday, 1 next Monday
        self.assertEqual(slots[-1], at(self.monday + timedelta(weeks=1), '09:00'))
        far = self.free_slots(self.portrait, self.monday, self.monday + timedelta(days=400))
        self.assertLess(far[-1].astimezone(TZ).date(), self.monday + timedelta(days=SLOT_SEARCH_DAYS_MAX))
        self.assertEqual(self.free_slots(self.portrait, self.monday, self.monday - timedelta(days=1)), [])

    def test_start_problem(self):
        self.assertIsNone(self.start_problem(self.portrait, at(self.monday, '09:00')))
        self.book(self.portrait, self.mei, at(self.monday, '09:00'))
        self.assertIn('is not available for Portrait', self.start_problem(self.portrait, at(self.monday, '09:30')))
        self.assertIn('on the quarter hour', self.start_problem(self.portrait, at(self.monday, '10:10')))
        self.assertIn('too soon', self.start_problem(self.portrait, next_on_grid(dates.now() + timedelta(minutes=30))))
        self.assertIn('is not available for Portrait', self.start_problem(self.portrait, at(self.monday, '13:00')))
        self.portrait.is_active = False
        self.assertIn('not available for booking at the moment', self.start_problem(self.portrait, at(self.monday, '10:00')))


class BookingLettersTests(StudioCase):
    """A booking writes itself into its provider's week: O → H (pending payment) → X (paid / done).
    (Freeing on delete / move is Django's signals: not ported.)"""

    def mon(self, provider=None, start='08:45', end='12:30'):
        return day_letters(self.sessions, provider or self.mei, self.monday, start, end)

    def test_a_pending_booking_puts_its_blocks_on_hold(self):
        self.assertEqual(self.mon(), 'U' + 'O' * 12 + 'UU')
        self.book(self.family, self.mei, at(self.monday, '09:00'))  # 09:00–10:00, buffer to 10:30
        self.assertEqual(self.mon(), 'U' + 'HHHH' + 'HH' + 'O' * 6 + 'UU')
        self.assertEqual(self.mon(self.raj), 'U' + 'O' * 12 + 'UU')  # Raj's week is untouched

    def test_the_buffer_over_closed_blocks_stays_closed(self):
        self.book(self.family, self.mei, at(self.monday, '11:00'))  # 11:00–12:00, buffer 12:00–12:30 is U
        self.assertEqual(self.mon(), 'U' + 'O' * 8 + 'HHHH' + 'UU')

    def test_paid_and_completed_are_booked(self):
        booking = self.book(self.family, self.mei, at(self.monday, '09:00'))
        for status, letter in (
            (PAYMENT_RECEIVED, 'X'), (ORDER_COMPLETED, 'X'), (PENDING_PAYMENT, 'H'),
        ):
            with self.subTest(status):
                set_status(self.sessions, booking, status)
                self.assertEqual(self.mon(), 'U' + letter * 6 + 'O' * 6 + 'UU')
        paid = self.book(self.portrait, self.mei, at(self.monday, '10:30'), status=PAYMENT_RECEIVED)
        self.assertEqual(self.mon(start='10:30', end='11:30'), 'XXXX')  # booked straight away as paid
        self.assertEqual(paid.order_status, PAYMENT_RECEIVED)

    def test_a_booking_across_two_weeks(self):
        sunday = self.monday - timedelta(days=1)
        open_week(self.sessions, self.mei, week_start(sunday), (6, '23:00', '24:00'))
        open_week(self.sessions, self.mei, self.monday, (0, '00:00', '01:00'))
        self.book(self.family, self.mei, at(sunday, '23:30'))  # 23:30–00:30, buffer to 01:00
        self.assertEqual(day_letters(self.sessions, self.mei, sunday, '23:00', '24:00'), 'OOHH')
        self.assertEqual(day_letters(self.sessions, self.mei, self.monday, '00:00', '01:15'), 'HHHHU')

    def test_a_week_without_a_row_gets_one(self):
        # E.g. a booking made in Django Admin at a time that was never opened: it still shows.
        tuesday = self.monday + timedelta(days=8)
        self.assertFalse(self.all(
            WeeklyAvailability, WeeklyAvailability.service_provider_id == self.mei.id, WeeklyAvailability.week == week_start(tuesday),
        ))
        self.book(self.portrait, self.mei, at(tuesday, '09:00'))
        self.assertEqual(day_letters(self.sessions, self.mei, tuesday, '08:45', '10:15'), 'UHHHHU')


class FailedPaymentLettersTests(StudioCase):
    """A booking whose payment failed frees its time; if it's set back to pending, it's on hold again."""

    def test_failed_frees_its_blocks(self):
        booking = self.book(self.family, self.mei, at(self.monday, '10:00'))  # 10:00–11:00, buffer to 11:30: H
        self.assertEqual(day_letters(self.sessions, self.mei, self.monday, '10:00', '11:30'), 'H' * 6)
        set_status(self.sessions, booking, PAYMENT_FAILED)
        self.assertEqual(day_letters(self.sessions, self.mei, self.monday, '10:00', '11:30'), 'O' * 6)
        self.assertIsNone(self.start_problem(self.family, at(self.monday, '10:00')))  # bookable again
        set_status(self.sessions, booking, PENDING_PAYMENT)  # e.g. the payment service retries
        self.assertEqual(day_letters(self.sessions, self.mei, self.monday, '10:00', '11:30'), 'H' * 6)


class StartIntervalTests(StudioCase):
    """Service.start_interval_minutes: bookings only start every N minutes from local midnight.
    The user's example: a 1-hour service, available 09:00 to 11:00."""

    def open_test_week(self):
        for provider in (self.mei, self.raj):
            open_week(self.sessions, provider, self.monday, (0, '09:00', '11:00'))

    def slots(self, interval):
        self.portrait.start_interval_minutes = interval
        return [s.astimezone(TZ).strftime('%H:%M') for s in self.free_slots(self.portrait, self.monday, self.monday)]

    def test_every_15_minutes_by_default(self):
        # Django: Service(...).start_interval_minutes == 15 (the model field's default).
        self.assertEqual(Service.__table__.c.start_interval_minutes.default.arg, 15)
        self.assertEqual(self.slots(15), ['09:00', '09:15', '09:30', '09:45', '10:00'])
        self.assertIsNone(self.start_problem(self.portrait, at(self.monday, '09:15')))  # 9:15 to 10:15

    def test_every_30_minutes(self):
        self.assertEqual(self.slots(30), ['09:00', '09:30', '10:00'])

    def test_every_hour(self):
        self.assertEqual(self.slots(60), ['09:00', '10:00'])

    def test_a_custom_interval_counts_from_midnight(self):
        self.assertEqual(self.slots(45), ['09:00', '09:45'])  # 9:00 is 12 × 45 min after midnight; 10:30 ends too late
        open_week(self.sessions, self.mei, self.monday, (0, '08:00', '12:00'))
        self.assertEqual(self.slots(120), ['08:00', '10:00'])

    def test_a_start_off_the_interval_is_explained(self):
        self.portrait.start_interval_minutes = 30
        self.assertEqual(
            self.start_problem(self.portrait, at(self.monday, '09:15')),
            'Portrait can only start every 30 minutes (for example 9am or 9:30am).',
        )
        self.assertIsNone(self.start_problem(self.portrait, at(self.monday, '09:30')))
        self.portrait.start_interval_minutes = 60
        self.assertEqual(
            self.start_problem(self.portrait, at(self.monday, '09:45')),
            'Portrait can only start every hour (for example 9am or 10am).',
        )
        self.portrait.start_interval_minutes = 120
        self.assertIn('every 2 hours (for example 8am or 10am)', self.start_problem(self.portrait, at(self.monday, '09:00')))

    def test_placing_a_booking_off_the_interval_is_refused(self):
        with self.sessions.begin() as db:
            db.get(Service, self.portrait.id).start_interval_minutes = 60
        with self.assertRaises(BookingError) as ctx, self.sessions.begin() as db:
            place_booking(db, self.studio, self.portrait.pk, at(self.monday, '09:30'), {'name': 'Alice'})
        self.assertEqual(ctx.exception.problems, ['Portrait can only start every hour (for example 9am or 10am).'])
        self.assertFalse(self.all(ScheduleItem))
        with self.sessions.begin() as db:
            booking = place_booking(db, self.studio, self.portrait.pk, at(self.monday, '10:00'), {'name': 'Alice'})
        self.assertEqual(booking.start_time, at(self.monday, '10:00'))


# --- test_services.py ---------------------------------------------------------------------------

def line(product, quantity, price=None):
    return {'product_id': product.pk, 'name': product.name, 'unit_price': price or str(product.price), 'quantity': quantity}


class PlaceOrderTests(DatabaseTestCase):
    def setUp(self):
        super().setUp()
        self.cafe = self.make.business('Kopi Café')
        self.florist = self.make.business('Florist')
        self.rose = self.make.product(self.florist, 'Rose', '5.00', total_quantity=50)
        # Kopi C: 111 in total, 1 on hold (a pending order) and 100 sold (a completed one): 10 available.
        self.kopi = self.make.product(self.cafe, 'Kopi C', '1.80', total_quantity=111)
        self.toast = self.make.product(self.cafe, 'Kaya Toast Set', '5.50', total_quantity=3)
        self.make.order(self.cafe, {'items': [line(self.kopi, 1)], 'details': {}})
        self.make.order(self.cafe, {'items': [line(self.kopi, 100)], 'details': {}}, order_status=ORDER_COMPLETED)
        self.existing = {order.id for order in self.all(OrderItem)}

    def place_order(self, *args, **kwargs):
        with self.sessions.begin() as db:
            return place_order(db, self.cafe, *args, **kwargs)

    def stock(self, product):
        """(available, on hold, sold): all derived from the orders."""
        with self.sessions() as db:
            product = db.get(Product, product.id)
            stock = ordered_quantities(db, [product.business_id], [product.id]).get(product.id, Stock())
        return product.total_quantity - stock.committed, stock.on_hold, stock.sold

    def new_orders(self):
        return [order for order in self.all(OrderItem) if order.id not in self.existing]

    def test_creates_pending_order_which_puts_its_quantities_on_hold(self):
        session = self.make.session(self.cafe, is_sandbox=True)
        details = {'name': 'Alice', 'postal_code': 238801}
        order = self.place_order([line(self.kopi, 2), line(self.toast, 3)], details, chat_session=session, is_sandbox=True)

        order = self.get(OrderItem, order.id)
        self.assertEqual(order.business_id, self.cafe.id)
        self.assertEqual(order.chat_session_id, session.id)
        self.assertTrue(order.is_sandbox)
        self.assertEqual(order.order_status, PENDING_PAYMENT)
        self.assertEqual(order.order_data, {'items': [line(self.kopi, 2), line(self.toast, 3)], 'details': details})
        self.assertEqual(order.total, Decimal('20.10'))
        # available → on hold; sold untouched until the order is completed. Totals don't change.
        self.assertEqual(self.stock(self.kopi), (8, 3, 100))
        self.assertEqual(self.stock(self.toast), (0, 3, 0))
        self.assertEqual((self.get(Product, self.kopi.id).total_quantity, self.get(Product, self.toast.id).total_quantity), (111, 3))

    def test_keeps_the_confirmed_price(self):
        order = self.place_order([line(self.kopi, 1, price='1.50')], {})
        self.assertEqual(order.order_data['items'][0]['unit_price'], '1.50')  # what the customer was shown

    def test_same_product_twice_is_merged(self):
        order = self.place_order([line(self.kopi, 2), line(self.kopi, 3)], {})
        self.assertEqual(order.order_data['items'], [line(self.kopi, 5)])
        self.assertEqual(self.stock(self.kopi)[0], 5)

    def test_not_enough_stock_changes_nothing(self):
        with self.assertRaises(OrderError) as ctx:
            self.place_order([line(self.kopi, 2), line(self.toast, 4)], {})
        self.assertEqual(ctx.exception.problems, ['Only 3 Kaya Toast Set are left.'])
        self.assertFalse(self.new_orders())
        self.assertEqual(self.stock(self.kopi), (10, 1, 100))  # the first item wasn't put on hold either
        self.assertEqual(self.stock(self.toast), (3, 0, 0))

    def test_unavailable_products(self):
        inactive = self.make.product(self.cafe, 'Old Special', '9.00', total_quantity=5, is_active=False)
        deleted = {'product_id': 99999, 'name': 'Gone', 'unit_price': '1.00', 'quantity': 1}
        cases = {
            'inactive': (line(inactive, 1), 'Old Special is no longer available.'),
            "another business's product": (line(self.rose, 1), 'Rose is no longer available.'),
            'deleted': (deleted, 'Gone is no longer available.'),
        }
        for label, (item, problem) in cases.items():
            with self.subTest(label), self.assertRaises(OrderError) as ctx:
                self.place_order([item], {})
            self.assertEqual(ctx.exception.problems, [problem])
        self.assertEqual(self.stock(self.rose)[0], 50)
        self.assertFalse(self.new_orders())

    def test_every_problem_is_reported(self):
        with self.sessions.begin() as db:
            db.get(Product, self.toast.id).is_active = False
        with self.assertRaises(OrderError) as ctx:
            self.place_order([line(self.kopi, 11), line(self.toast, 1)], {})
        self.assertEqual(ctx.exception.problems, ['Only 10 Kopi C are left.', 'Kaya Toast Set is no longer available.'])

    def test_no_items(self):
        with self.assertRaises(OrderError):
            self.place_order([], {})

    def test_orders_in_turn_cannot_oversell(self):
        self.place_order([line(self.toast, 2)], {})
        with self.assertRaises(OrderError) as ctx:
            self.place_order([line(self.toast, 2)], {})
        self.assertEqual(ctx.exception.problems, ['Only 1 Kaya Toast Set is left.'])
        self.place_order([line(self.toast, 1)], {})
        self.assertEqual(self.stock(self.toast), (0, 3, 0))
        self.assertEqual(len(self.new_orders()), 2)

    def test_paid_and_completed_orders_count_too(self):
        self.make.order(self.cafe, {'items': [line(self.toast, 1)], 'details': {}}, order_status=PAYMENT_RECEIVED)
        self.make.order(self.cafe, {'items': [line(self.toast, 1)], 'details': {}}, order_status=ORDER_COMPLETED)
        with self.assertRaises(OrderError) as ctx:
            self.place_order([line(self.toast, 2)], {})
        self.assertEqual(ctx.exception.problems, ['Only 1 Kaya Toast Set is left.'])
        self.place_order([line(self.toast, 1)], {})
        self.assertEqual(self.stock(self.toast), (0, 2, 1))

    def test_more_stock_can_be_ordered_after_the_total_goes_up(self):
        self.place_order([line(self.toast, 3)], {})
        with self.sessions.begin() as db:
            db.execute(update(Product).where(Product.id == self.toast.id).values(total_quantity=5))
        self.place_order([line(self.toast, 2)], {})
        self.assertEqual(self.stock(self.toast), (0, 5, 0))

    def test_recheck_stops_overselling_if_the_lock_does_not_hold(self):
        # Simulate losing a race: the first (locked) read misses an order another transaction has
        # just placed (as can happen without row locks, e.g. on SQLite), so the check passes.
        self.make.order(self.cafe, {'items': [line(self.toast, 2)], 'details': {}})
        from app.chat_flow import checkout
        real_quantities_available = checkout.quantities_available
        reads = []

        def stale_first_read(db, products):
            products = list(products)
            available = real_quantities_available(db, products)
            if not reads:
                available = {p.id: p.total_quantity for p in products}  # nothing on hold or sold, as far as this read knows
            reads.append(available)
            return available

        with patch.object(checkout, 'quantities_available', side_effect=stale_first_read), self.assertRaises(OrderError) as ctx:
            self.place_order([line(self.kopi, 2), line(self.toast, 3)], {})
        self.assertEqual(ctx.exception.problems, ['Kaya Toast Set just sold out.'])
        self.assertEqual(len(reads), 2)  # checked before and after saving the order
        # All or nothing: the order (Kopi C too) was rolled back.
        self.assertEqual(len(self.new_orders()), 1)  # only the other transaction's order
        self.assertEqual(self.stock(self.kopi), (10, 1, 100))
        self.assertEqual(self.stock(self.toast), (1, 2, 0))

    def test_locks_product_rows_in_id_order(self):
        # Django: select_for_update() and the SQL's ORDER BY. Here: the SQL of the product read
        # (SQLite renders no FOR UPDATE; PostgreSQL does).
        engine = self.sessions.kw['bind']
        queries = []

        def capture(conn, cursor, statement, parameters, context, executemany):
            queries.append(statement)

        event.listen(engine, 'before_cursor_execute', capture)
        self.addCleanup(event.remove, engine, 'before_cursor_execute', capture)
        self.place_order([line(self.toast, 1), line(self.kopi, 1)], {})
        locking_read = next(q for q in queries if 'FROM product_app_product' in q and 'SELECT' in q)
        self.assertIn('ORDER BY product_app_product.id', locking_read)  # a fixed order: no deadlocks


class PlaceBookingTests(DatabaseTestCase):
    def setUp(self):
        super().setUp()
        singapore_time(self)
        self.studio = self.make.business('Snap Studio')
        self.other = self.make.business('Other')
        self.mei = self.make.provider(self.studio, 'Mei')
        self.raj = self.make.provider(self.studio, 'Raj')
        self.family = self.make.service(self.studio, 'Family', [self.raj, self.mei], price='250.00', duration_minutes=60, buffer_minutes=30)
        self.theirs = self.make.service(self.other, 'Theirs', price='1', duration_minutes=60)
        self.monday = future_monday()
        self.session = self.make.session(self.studio, is_sandbox=True)
        for provider in (self.mei, self.raj):
            open_week(self.sessions, provider, self.monday, (0, '09:00', '12:00'))

    def place(self, start, service_id=None, details=None, **kwargs):
        with self.sessions.begin() as db:
            return place_booking(
                db, self.studio, service_id or self.family.pk, start, {'name': 'Alice'} if details is None else details, **kwargs,
            )

    def test_books_the_first_free_provider_and_puts_the_time_on_hold(self):
        booking = self.place(at(self.monday, '09:00'), chat_session=self.session, is_sandbox=True)
        validate_schedule_data(booking.schedule_data)  # Django: booking.full_clean()
        self.assertEqual(booking.order_status, PENDING_PAYMENT)
        self.assertEqual(booking.service_provider_id, self.mei.id)  # lowest pk of the two
        self.assertEqual(booking.service_id, self.family.id)
        self.assertEqual((booking.chat_session_id, booking.is_sandbox), (self.session.id, True))
        self.assertEqual(
            (booking.start_time, booking.end_time, booking.blocked_until),
            (at(self.monday, '09:00'), at(self.monday, '10:00'), at(self.monday, '10:30')),
        )
        self.assertEqual(booking.schedule_data, {
            'service': {'service_id': self.family.pk, 'name': 'Family', 'price': '250.00', 'duration_minutes': 60, 'buffer_minutes': 30},
            'details': {'name': 'Alice'},
        })
        self.assertEqual(booking.total, Decimal('250.00'))
        # Its blocks went from O to H (the hour and its buffer); Raj's didn't.
        self.assertEqual(day_letters(self.sessions, self.mei, self.monday, '09:00', '12:00'), 'H' * 6 + 'O' * 6)
        self.assertEqual(day_letters(self.sessions, self.raj, self.monday, '09:00', '12:00'), 'O' * 12)

    def test_the_same_time_again_goes_to_the_next_provider(self):
        first = self.place(at(self.monday, '09:00'))
        second = self.place(at(self.monday, '09:00'))
        self.assertEqual({first.service_provider_id, second.service_provider_id}, {self.mei.id, self.raj.id})
        with self.assertRaises(BookingError) as ctx:
            self.place(at(self.monday, '09:00'))
        self.assertIn('is not available for Family', ctx.exception.problems[0])
        with self.assertRaises(BookingError):
            self.place(at(self.monday, '10:15'))  # inside both buffers
        self.place(at(self.monday, '10:30'))
        self.assertEqual(len(self.all(ScheduleItem)), 3)

    def test_an_inactive_provider_is_skipped(self):
        with self.sessions.begin() as db:
            db.execute(update(ServiceProvider).where(ServiceProvider.id == self.mei.id).values(is_active=False))
        self.assertEqual(self.place(at(self.monday, '09:00')).service_provider_id, self.raj.id)

    def test_the_price_shown_to_the_customer_is_kept(self):
        self.assertEqual(self.place(at(self.monday, '09:00'), price='200.00').schedule_data['service']['price'], '200.00')

    def test_nothing_is_booked_when_it_cant_be(self):
        cases = {
            'closed': (at(self.monday, '13:00'), 'is not available for Family'),
            'off the grid': (at(self.monday, '09:05'), 'quarter hour'),
            'too soon': (next_on_grid(dates.now() + timedelta(minutes=15)), 'too soon'),
            'in the past': (at(self.monday - timedelta(days=28), '09:00'), 'too soon'),
        }
        for label, (start, problem) in cases.items():
            with self.subTest(label), self.assertRaises(BookingError) as ctx:
                self.place(start)
            self.assertIn(problem, str(ctx.exception))
        self.assertFalse(self.all(ScheduleItem))
        self.assertEqual(day_letters(self.sessions, self.mei, self.monday, '09:00', '12:00'), 'O' * 12)

    def test_inactive_unknown_or_other_business_service(self):
        with self.sessions.begin() as db:
            db.execute(update(Service).where(Service.id == self.family.id).values(is_active=False))
        with self.assertRaises(BookingError) as ctx:
            self.place(at(self.monday, '09:00'))
        self.assertIn('not available for booking', ctx.exception.problems[0])
        for service_id in (self.theirs.pk, 99999):
            with self.subTest(service_id=service_id), self.assertRaises(BookingError) as ctx:
                self.place(at(self.monday, '09:00'), service_id=service_id, details={})
            self.assertEqual(ctx.exception.problems, ['That service is no longer available.'])
        self.assertFalse(self.all(ScheduleItem))

    def test_a_clash_found_after_saving_rolls_back_the_booking_and_its_letters(self):
        # As if the lock didn't hold (e.g. SQLite): another booking took the time in between.
        taken = self.place(at(self.monday, '09:00'))
        before = day_letters(self.sessions, self.mei, self.monday)
        with patch('app.chat_flow.schedule.start_problem', return_value=None), \
                patch('app.chat_flow.schedule.free_provider', return_value=self.mei), \
                self.assertRaises(BookingError) as ctx:
            self.place(at(self.monday, '09:00'))
        self.assertIn('was just booked by someone else', ctx.exception.problems[0])
        self.assertEqual([b.id for b in self.all(ScheduleItem)], [taken.id])
        self.assertEqual(day_letters(self.sessions, self.mei, self.monday), before)

    def test_locks_the_providers(self):
        engine = self.sessions.kw['bind']
        queries = []

        def capture(conn, cursor, statement, parameters, context, executemany):
            queries.append(statement)

        event.listen(engine, 'before_cursor_execute', capture)
        self.addCleanup(event.remove, engine, 'before_cursor_execute', capture)
        self.place(at(self.monday, '09:00'))
        locks = [q for q in queries if 'product_app_serviceprovider' in q and 'FOR UPDATE' in q]
        if engine.dialect.name == 'postgresql':  # Django: connection.features.has_select_for_update
            self.assertTrue(locks)
