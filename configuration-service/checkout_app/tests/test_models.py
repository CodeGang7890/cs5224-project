from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import SimpleTestCase, TestCase

from configuration_app.models import BusinessConfiguration

from ..models import OrderItem, OrderStatus
from ..validators import validate_order_data

VALID_ORDER_DATA = {
    'items': [
        {'product_id': 1, 'name': 'Kopi C', 'unit_price': '1.80', 'quantity': 2},
        {'product_id': 2, 'name': 'Kaya Toast Set', 'unit_price': '5.50', 'quantity': 1},
    ],
    'details': {'name': 'Alice', 'email': 'alice@example.com', 'postal_code': 238801},
}


class ValidateOrderDataTests(SimpleTestCase):
    def assertInvalid(self, value, message_part):
        with self.assertRaises(ValidationError) as ctx:
            validate_order_data(value)
        self.assertTrue(
            any(message_part in message for message in ctx.exception.messages),
            f'{message_part!r} not in {ctx.exception.messages}',
        )

    def test_valid(self):
        validate_order_data(VALID_ORDER_DATA)
        validate_order_data({**VALID_ORDER_DATA, 'details': {}})  # a flow without details collection
        item = VALID_ORDER_DATA['items'][0]
        for price in ('0', '0.00', '5', '5.5', '99999999.99'):
            with self.subTest(price=price):
                validate_order_data({'items': [{**item, 'unit_price': price}], 'details': {}})

    def test_invalid(self):
        item = VALID_ORDER_DATA['items'][0]
        cases = {
            'not an object': ([], 'must be an object'),
            'missing items': ({'details': {}}, 'Missing field(s) items'),
            'missing details': ({'items': [item]}, 'Missing field(s) details'),
            'unknown field': ({**VALID_ORDER_DATA, 'total': '3.60'}, 'Unknown field(s) total'),
            'items not a list': ({'items': {}, 'details': {}}, 'items must be a list'),
            'no items': ({'items': [], 'details': {}}, 'items must have at least one item'),
            'item missing field': ({'items': [{'product_id': 1}], 'details': {}}, 'must be an object with exactly'),
            'item extra field': ({'items': [{**item, 'note': 'x'}], 'details': {}}, 'must be an object with exactly'),
            'product_id not int': ({'items': [{**item, 'product_id': '1'}], 'details': {}}, 'product_id must be an integer'),
            'duplicate product': ({'items': [item, {**item, 'quantity': 1}], 'details': {}}, 'listed more than once'),
            'blank name': ({'items': [{**item, 'name': ''}], 'details': {}}, 'name must be a non-blank string'),
            'numeric price': ({'items': [{**item, 'unit_price': 1.8}], 'details': {}}, 'unit_price must be a decimal string'),
            'negative price': ({'items': [{**item, 'unit_price': '-1.00'}], 'details': {}}, 'unit_price must be'),
            'three decimals': ({'items': [{**item, 'unit_price': '1.805'}], 'details': {}}, 'unit_price must be'),
            'price too big': ({'items': [{**item, 'unit_price': '100000000.00'}], 'details': {}}, 'unit_price must be'),
            'price not a number': ({'items': [{**item, 'unit_price': 'abc'}], 'details': {}}, 'unit_price must be'),
            'infinite price': ({'items': [{**item, 'unit_price': 'Infinity'}], 'details': {}}, 'unit_price must be'),
            'zero quantity': ({'items': [{**item, 'quantity': 0}], 'details': {}}, 'quantity must be an integer from 1'),
            'bool quantity': ({'items': [{**item, 'quantity': True}], 'details': {}}, 'quantity must be an integer from 1'),
            'huge quantity': ({'items': [{**item, 'quantity': 1_000_001}], 'details': {}}, 'quantity must be an integer from 1'),
            'details not object': ({'items': [item], 'details': 'Alice'}, 'details must be an object'),
            'bad detail key': ({'items': [item], 'details': {'Postal Code': 1}}, "details: invalid key 'Postal Code'"),
            'blank detail': ({'items': [item], 'details': {'name': ' '}}, 'details: name must be a non-blank string or a number'),
            'bool detail': ({'items': [item], 'details': {'agreed': False}}, 'details: agreed must be'),
        }
        for label, (value, message_part) in cases.items():
            with self.subTest(label):
                self.assertInvalid(value, message_part)

    def test_every_error_is_listed(self):
        with self.assertRaises(ValidationError) as ctx:
            validate_order_data({'items': [{'product_id': 'x', 'name': '', 'unit_price': 1, 'quantity': 0}], 'details': []})
        self.assertEqual(len(ctx.exception.messages), 5, ctx.exception.messages)


class OrderItemModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.business = BusinessConfiguration.objects.create(business_name='Kopi Café', location='Singapore')

    def test_defaults_and_total(self):
        order = OrderItem(business=self.business, order_data=VALID_ORDER_DATA)
        order.full_clean()
        order.save()
        self.assertEqual(order.order_status, OrderStatus.PENDING_PAYMENT)
        self.assertEqual(order.order_status, 'pending_payment')
        self.assertFalse(order.is_sandbox)
        self.assertIsNone(order.chat_session)
        self.assertEqual(order.total, Decimal('9.10'))  # 2 × 1.80 + 5.50

    def test_statuses(self):
        self.assertEqual(OrderStatus.values, ['pending_payment', 'payment_received', 'order_completed'])
        for status in OrderStatus.values:
            OrderItem(business=self.business, order_data=VALID_ORDER_DATA, order_status=status).full_clean()

    def test_invalid_status_rejected(self):
        with self.assertRaises(ValidationError) as ctx:
            OrderItem(business=self.business, order_data=VALID_ORDER_DATA, order_status='shipped').full_clean()
        self.assertIn('order_status', ctx.exception.message_dict)
        with self.assertRaises(IntegrityError), transaction.atomic():
            OrderItem.objects.create(business=self.business, order_data=VALID_ORDER_DATA, order_status='shipped')

    def test_invalid_order_data_rejected_by_full_clean(self):
        with self.assertRaises(ValidationError) as ctx:
            OrderItem(business=self.business, order_data={'items': []}).full_clean()
        self.assertIn('order_data', ctx.exception.message_dict)

    def test_deleted_with_business(self):
        OrderItem.objects.create(business=self.business, order_data=VALID_ORDER_DATA)
        self.business.delete()
        self.assertFalse(OrderItem.objects.exists())


class SampleOrderItemFixtureTests(TestCase):
    fixtures = ['sample_business_configurations', 'sample_order_items']

    def test_fixture_is_valid(self):
        orders = OrderItem.objects.all()
        self.assertEqual(orders.count(), 5)
        self.assertEqual(set(orders.values_list('order_status', flat=True)), set(OrderStatus.values))
        for order in orders:
            with self.subTest(order=order.pk):
                order.full_clean()  # loaddata skips validation
