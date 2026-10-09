from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from chat_app.models import ChatSession
from configuration_app.models import BusinessConfiguration
from product_app.models import Product, Service, ServiceProvider

from ..models import OrderItem, OrderStatus, ScheduleItem
from ..schedule import next_on_grid
from ..services import BookingError, OrderError, place_booking, place_order
from ..stock import Stock
from .test_schedule import at, day_letters, future_monday, open_week


def line(product, quantity, price=None):
    return {'product_id': product.pk, 'name': product.name, 'unit_price': price or str(product.price), 'quantity': quantity}


class PlaceOrderTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.cafe = BusinessConfiguration.objects.create(business_name='Kopi Café', location='Singapore')
        cls.florist = BusinessConfiguration.objects.create(business_name='Florist', location='Singapore')
        cls.rose = Product.objects.create(business=cls.florist, name='Rose', price='5.00', total_quantity=50)

    def setUp(self):
        # Kopi C: 111 in total, 1 on hold (a pending order) and 100 sold (a completed one): 10 available.
        self.kopi = Product.objects.create(business=self.cafe, name='Kopi C', price='1.80', total_quantity=111)
        self.toast = Product.objects.create(business=self.cafe, name='Kaya Toast Set', price='5.50', total_quantity=3)
        OrderItem.objects.create(business=self.cafe, order_data={'items': [line(self.kopi, 1)], 'details': {}})
        OrderItem.objects.create(
            business=self.cafe, order_status=OrderStatus.ORDER_COMPLETED, order_data={'items': [line(self.kopi, 100)], 'details': {}}
        )
        self.existing = set(OrderItem.objects.values_list('pk', flat=True))

    def stock(self, product):
        """(available, on hold, sold): all derived from the orders."""
        product.refresh_from_db()
        return product.quantity_available, product.quantity_on_hold, product.quantity_sold

    def new_orders(self):
        return OrderItem.objects.exclude(pk__in=self.existing)

    def test_creates_pending_order_which_puts_its_quantities_on_hold(self):
        session = ChatSession.objects.create(business=self.cafe, is_sandbox=True)
        details = {'name': 'Alice', 'postal_code': 238801}
        order = place_order(self.cafe, [line(self.kopi, 2), line(self.toast, 3)], details, chat_session=session, is_sandbox=True)

        order.refresh_from_db()
        self.assertEqual(order.business, self.cafe)
        self.assertEqual(order.chat_session, session)
        self.assertTrue(order.is_sandbox)
        self.assertEqual(order.order_status, OrderStatus.PENDING_PAYMENT)
        self.assertEqual(order.order_data, {'items': [line(self.kopi, 2), line(self.toast, 3)], 'details': details})
        self.assertEqual(order.total, Decimal('20.10'))
        # available → on hold; sold untouched until the order is completed. Totals don't change.
        self.assertEqual(self.stock(self.kopi), (8, 3, 100))
        self.assertEqual(self.stock(self.toast), (0, 3, 0))
        self.assertEqual((self.kopi.total_quantity, self.toast.total_quantity), (111, 3))

    def test_keeps_the_confirmed_price(self):
        order = place_order(self.cafe, [line(self.kopi, 1, price='1.50')], {})
        self.assertEqual(order.order_data['items'][0]['unit_price'], '1.50')  # what the customer was shown

    def test_same_product_twice_is_merged(self):
        order = place_order(self.cafe, [line(self.kopi, 2), line(self.kopi, 3)], {})
        self.assertEqual(order.order_data['items'], [line(self.kopi, 5)])
        self.assertEqual(self.stock(self.kopi)[0], 5)

    def test_not_enough_stock_changes_nothing(self):
        with self.assertRaises(OrderError) as ctx:
            place_order(self.cafe, [line(self.kopi, 2), line(self.toast, 4)], {})
        self.assertEqual(ctx.exception.problems, ['Only 3 Kaya Toast Set are left.'])
        self.assertFalse(self.new_orders().exists())
        self.assertEqual(self.stock(self.kopi), (10, 1, 100))  # the first item wasn't put on hold either
        self.assertEqual(self.stock(self.toast), (3, 0, 0))

    def test_unavailable_products(self):
        inactive = Product.objects.create(business=self.cafe, name='Old Special', price='9.00', total_quantity=5, is_active=False)
        deleted = {'product_id': 99999, 'name': 'Gone', 'unit_price': '1.00', 'quantity': 1}
        cases = {
            'inactive': (line(inactive, 1), 'Old Special is no longer available.'),
            "another business's product": (line(self.rose, 1), 'Rose is no longer available.'),
            'deleted': (deleted, 'Gone is no longer available.'),
        }
        for label, (item, problem) in cases.items():
            with self.subTest(label), self.assertRaises(OrderError) as ctx:
                place_order(self.cafe, [item], {})
            self.assertEqual(ctx.exception.problems, [problem])
        self.assertEqual(self.stock(self.rose)[0], 50)
        self.assertFalse(self.new_orders().exists())

    def test_every_problem_is_reported(self):
        self.toast.is_active = False
        self.toast.save()
        with self.assertRaises(OrderError) as ctx:
            place_order(self.cafe, [line(self.kopi, 11), line(self.toast, 1)], {})
        self.assertEqual(ctx.exception.problems, ['Only 10 Kopi C are left.', 'Kaya Toast Set is no longer available.'])

    def test_no_items(self):
        with self.assertRaises(OrderError):
            place_order(self.cafe, [], {})

    def test_orders_in_turn_cannot_oversell(self):
        place_order(self.cafe, [line(self.toast, 2)], {})
        with self.assertRaises(OrderError) as ctx:
            place_order(self.cafe, [line(self.toast, 2)], {})
        self.assertEqual(ctx.exception.problems, ['Only 1 Kaya Toast Set is left.'])
        place_order(self.cafe, [line(self.toast, 1)], {})
        self.assertEqual(self.stock(self.toast), (0, 3, 0))
        self.assertEqual(self.new_orders().count(), 2)

    def test_paid_and_completed_orders_count_too(self):
        OrderItem.objects.create(
            business=self.cafe, order_status=OrderStatus.PAYMENT_RECEIVED, order_data={'items': [line(self.toast, 1)], 'details': {}}
        )
        OrderItem.objects.create(
            business=self.cafe, order_status=OrderStatus.ORDER_COMPLETED, order_data={'items': [line(self.toast, 1)], 'details': {}}
        )
        with self.assertRaises(OrderError) as ctx:
            place_order(self.cafe, [line(self.toast, 2)], {})
        self.assertEqual(ctx.exception.problems, ['Only 1 Kaya Toast Set is left.'])
        place_order(self.cafe, [line(self.toast, 1)], {})
        self.assertEqual(self.stock(self.toast), (0, 2, 1))

    def test_more_stock_can_be_ordered_after_the_total_goes_up(self):
        place_order(self.cafe, [line(self.toast, 3)], {})
        Product.objects.filter(pk=self.toast.pk).update(total_quantity=5)
        place_order(self.cafe, [line(self.toast, 2)], {})
        self.assertEqual(self.stock(self.toast), (0, 5, 0))

    def test_recheck_stops_overselling_if_the_lock_does_not_hold(self):
        # Simulate losing a race: the first (locked) read misses an order another transaction has
        # just placed (as can happen without row locks, e.g. on SQLite), so the check passes.
        OrderItem.objects.create(business=self.cafe, order_data={'items': [line(self.toast, 2)], 'details': {}})
        real_load_stock = Product.load_stock
        reads = []

        def stale_first_read(products):
            products = real_load_stock(products)
            if not reads:
                for product in products:
                    product._stock = Stock()  # nothing on hold or sold, as far as this read knows
            reads.append(products)
            return products

        with patch.object(Product, 'load_stock', side_effect=stale_first_read), self.assertRaises(OrderError) as ctx:
            place_order(self.cafe, [line(self.kopi, 2), line(self.toast, 3)], {})
        self.assertEqual(ctx.exception.problems, ['Kaya Toast Set just sold out.'])
        self.assertEqual(len(reads), 2)  # checked before and after saving the order
        # All or nothing: the order (Kopi C too) was rolled back.
        self.assertEqual(self.new_orders().count(), 1)  # only the other transaction's order
        self.assertEqual(self.stock(self.kopi), (10, 1, 100))
        self.assertEqual(self.stock(self.toast), (1, 2, 0))

    def test_locks_product_rows_in_id_order(self):
        with patch('checkout_app.services.Product.objects.select_for_update', wraps=Product.objects.select_for_update) as select_for_update:
            with CaptureQueriesContext(connection) as queries:
                place_order(self.cafe, [line(self.toast, 1), line(self.kopi, 1)], {})
        select_for_update.assert_called_once_with()
        locking_read = next(q['sql'] for q in queries if 'FROM "product_app_product"' in q['sql'] and 'SELECT' in q['sql'])
        self.assertIn('ORDER BY "product_app_product"."id" ASC', locking_read)  # a fixed order: no deadlocks


@override_settings(SCHEDULE_TIME_ZONE='Asia/Singapore')
class PlaceBookingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.studio = BusinessConfiguration.objects.create(business_name='Snap Studio', location='Singapore')
        cls.other = BusinessConfiguration.objects.create(business_name='Other', location='Singapore')
        cls.mei = ServiceProvider.objects.create(business=cls.studio, name='Mei')
        cls.raj = ServiceProvider.objects.create(business=cls.studio, name='Raj')
        cls.family = Service.objects.create(
            business=cls.studio, name='Family', price='250.00', duration_minutes=60, buffer_minutes=30
        )
        cls.family.service_providers.set([cls.raj, cls.mei])
        cls.theirs = Service.objects.create(business=cls.other, name='Theirs', price=1, duration_minutes=60)
        cls.monday = future_monday()
        cls.session = ChatSession.objects.create(business=cls.studio, is_sandbox=True)

    def setUp(self):
        for provider in (self.mei, self.raj):
            open_week(provider, self.monday, (0, '09:00', '12:00'))

    def place(self, start, **kwargs):
        return place_booking(self.studio, self.family.pk, start, {'name': 'Alice'}, **kwargs)

    def test_books_the_first_free_provider_and_puts_the_time_on_hold(self):
        booking = self.place(at(self.monday, '09:00'), chat_session=self.session, is_sandbox=True)
        booking.full_clean()
        self.assertEqual(booking.order_status, OrderStatus.PENDING_PAYMENT)
        self.assertEqual(booking.service_provider, self.mei)  # lowest pk of the two
        self.assertEqual(booking.service, self.family)
        self.assertEqual((booking.chat_session, booking.is_sandbox), (self.session, True))
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
        self.assertEqual(day_letters(self.mei, self.monday, '09:00', '12:00'), 'H' * 6 + 'O' * 6)
        self.assertEqual(day_letters(self.raj, self.monday, '09:00', '12:00'), 'O' * 12)

    def test_the_same_time_again_goes_to_the_next_provider(self):
        first = self.place(at(self.monday, '09:00'))
        second = self.place(at(self.monday, '09:00'))
        self.assertEqual({first.service_provider, second.service_provider}, {self.mei, self.raj})
        with self.assertRaises(BookingError) as ctx:
            self.place(at(self.monday, '09:00'))
        self.assertIn('is not available for Family', ctx.exception.problems[0])
        with self.assertRaises(BookingError):
            self.place(at(self.monday, '10:15'))  # inside both buffers
        self.place(at(self.monday, '10:30'))
        self.assertEqual(ScheduleItem.objects.count(), 3)

    def test_an_inactive_provider_is_skipped(self):
        ServiceProvider.objects.filter(pk=self.mei.pk).update(is_active=False)
        self.assertEqual(self.place(at(self.monday, '09:00')).service_provider, self.raj)

    def test_the_price_shown_to_the_customer_is_kept(self):
        self.assertEqual(self.place(at(self.monday, '09:00'), price='200.00').schedule_data['service']['price'], '200.00')

    def test_nothing_is_booked_when_it_cant_be(self):
        cases = {
            'closed': (at(self.monday, '13:00'), 'is not available for Family'),
            'off the grid': (at(self.monday, '09:05'), 'quarter hour'),
            'too soon': (next_on_grid(timezone.now() + timedelta(minutes=15)), 'too soon'),
            'in the past': (at(self.monday - timedelta(days=28), '09:00'), 'too soon'),
        }
        for label, (start, problem) in cases.items():
            with self.subTest(label), self.assertRaises(BookingError) as ctx:
                self.place(start)
            self.assertIn(problem, str(ctx.exception))
        self.assertFalse(ScheduleItem.objects.exists())
        self.assertEqual(day_letters(self.mei, self.monday, '09:00', '12:00'), 'O' * 12)

    def test_inactive_unknown_or_other_business_service(self):
        Service.objects.filter(pk=self.family.pk).update(is_active=False)
        with self.assertRaises(BookingError) as ctx:
            self.place(at(self.monday, '09:00'))
        self.assertIn('not available for booking', ctx.exception.problems[0])
        for service_id in (self.theirs.pk, 99999):
            with self.subTest(service_id=service_id), self.assertRaises(BookingError) as ctx:
                place_booking(self.studio, service_id, at(self.monday, '09:00'), {})
            self.assertEqual(ctx.exception.problems, ['That service is no longer available.'])
        self.assertFalse(ScheduleItem.objects.exists())

    def test_a_clash_found_after_saving_rolls_back_the_booking_and_its_letters(self):
        # As if the lock didn't hold (e.g. SQLite): another booking took the time in between.
        taken = self.place(at(self.monday, '09:00'))
        before = day_letters(self.mei, self.monday)
        with patch('checkout_app.schedule.start_problem', return_value=None), \
                patch('checkout_app.schedule.free_provider', return_value=self.mei), \
                self.assertRaises(BookingError) as ctx:
            self.place(at(self.monday, '09:00'))
        self.assertIn('was just booked by someone else', ctx.exception.problems[0])
        self.assertEqual(list(ScheduleItem.objects.all()), [taken])
        self.assertEqual(day_letters(self.mei, self.monday), before)

    def test_locks_the_providers(self):
        with CaptureQueriesContext(connection) as queries:
            self.place(at(self.monday, '09:00'))
        locks = [q['sql'] for q in queries if 'product_app_serviceprovider' in q['sql'] and 'FOR UPDATE' in q['sql']]
        if connection.features.has_select_for_update:
            self.assertTrue(locks)
