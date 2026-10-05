from decimal import Decimal
from unittest.mock import patch

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from chat_app.models import ChatSession
from configuration_app.models import BusinessConfiguration
from product_app.models import Product

from ..models import OrderItem, OrderStatus
from ..services import OrderError, place_order


def line(product, quantity, price=None):
    return {'product_id': product.pk, 'name': product.name, 'unit_price': price or str(product.price), 'quantity': quantity}


class PlaceOrderTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.cafe = BusinessConfiguration.objects.create(business_name='Kopi Café', location='Singapore')
        cls.florist = BusinessConfiguration.objects.create(business_name='Florist', location='Singapore')
        cls.rose = Product.objects.create(business=cls.florist, name='Rose', price='5.00', quantity_available=50)

    def setUp(self):
        self.kopi = Product.objects.create(business=self.cafe, name='Kopi C', price='1.80', quantity_available=10, quantity_on_hold=1, quantity_sold=100)
        self.toast = Product.objects.create(business=self.cafe, name='Kaya Toast Set', price='5.50', quantity_available=3)

    def stock(self, product):
        product.refresh_from_db()
        return product.quantity_available, product.quantity_on_hold, product.quantity_sold

    def test_creates_pending_order_and_reserves_stock(self):
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
        # available → on hold; sold untouched until payment.
        self.assertEqual(self.stock(self.kopi), (8, 3, 100))
        self.assertEqual(self.stock(self.toast), (0, 3, 0))

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
        self.assertFalse(OrderItem.objects.exists())
        self.assertEqual(self.stock(self.kopi), (10, 1, 100))  # the first item wasn't reserved either
        self.assertEqual(self.stock(self.toast), (3, 0, 0))

    def test_unavailable_products(self):
        inactive = Product.objects.create(business=self.cafe, name='Old Special', price='9.00', quantity_available=5, is_active=False)
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
        self.assertFalse(OrderItem.objects.exists())

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
        self.assertEqual(OrderItem.objects.count(), 2)

    def test_guarded_update_stops_overselling_if_the_lock_does_not_hold(self):
        # Simulate losing a race: the locked read says there's plenty of stock, but another
        # transaction has already taken it (as can happen without row locks, e.g. on SQLite).
        stale_kopi = Product.objects.get(pk=self.kopi.pk)
        stale_toast = Product.objects.get(pk=self.toast.pk)
        stale_toast.quantity_available = 100
        Product.objects.filter(pk=self.toast.pk).update(quantity_available=1)

        with patch('checkout_app.services.Product.objects.select_for_update') as select_for_update:
            select_for_update.return_value.filter.return_value.order_by.return_value = [stale_kopi, stale_toast]
            with self.assertRaises(OrderError) as ctx:
                place_order(self.cafe, [line(self.kopi, 2), line(self.toast, 3)], {})
        self.assertEqual(ctx.exception.problems, ['Kaya Toast Set just sold out.'])
        # All or nothing: Kopi C, updated before the toast failed, was rolled back too.
        self.assertEqual(self.stock(self.kopi), (10, 1, 100))
        self.assertEqual(self.stock(self.toast), (1, 0, 0))
        self.assertFalse(OrderItem.objects.exists())

    def test_locks_product_rows_in_id_order(self):
        with patch('checkout_app.services.Product.objects.select_for_update', wraps=Product.objects.select_for_update) as select_for_update:
            with CaptureQueriesContext(connection) as queries:
                place_order(self.cafe, [line(self.toast, 1), line(self.kopi, 1)], {})
        select_for_update.assert_called_once_with()
        locking_read = next(q['sql'] for q in queries if 'FROM "product_app_product"' in q['sql'] and 'SELECT' in q['sql'])
        self.assertIn('ORDER BY "product_app_product"."id" ASC', locking_read)  # a fixed order: no deadlocks
