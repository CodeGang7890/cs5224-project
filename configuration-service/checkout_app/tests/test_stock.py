from django.core.exceptions import ValidationError
from django.test import TestCase

from configuration_app.models import BusinessConfiguration
from product_app.models import Product

from ..models import OrderItem, OrderStatus
from ..stock import HOLD_STATUSES, SOLD_STATUSES, Stock, ordered_quantities


def make_order(business, status, *lines):
    """An order of (product, quantity) lines with the given status."""
    return OrderItem.objects.create(business=business, order_status=status, order_data={
        'items': [
            {'product_id': product.pk, 'name': product.name, 'unit_price': str(product.price), 'quantity': quantity}
            for product, quantity in lines
        ],
        'details': {},
    })


class OrderedQuantitiesTests(TestCase):
    """checkout_app.stock: on hold / sold quantities summed from the orders."""

    @classmethod
    def setUpTestData(cls):
        cls.cafe = BusinessConfiguration.objects.create(business_name='Kopi Café', location='Singapore')
        cls.florist = BusinessConfiguration.objects.create(business_name='Florist', location='Singapore')
        cls.kopi = Product.objects.create(business=cls.cafe, name='Kopi C', price='1.80', total_quantity=100)
        cls.toast = Product.objects.create(business=cls.cafe, name='Kaya Toast Set', price='5.50', total_quantity=20)
        cls.cake = Product.objects.create(business=cls.cafe, name='Pandan Cake', price='28.00', total_quantity=5)
        cls.rose = Product.objects.create(business=cls.florist, name='Rose', price='5.00', total_quantity=50)

    def test_statuses(self):
        self.assertEqual(set(HOLD_STATUSES), {OrderStatus.PENDING_PAYMENT, OrderStatus.PAYMENT_RECEIVED})
        self.assertEqual(set(SOLD_STATUSES), {OrderStatus.ORDER_COMPLETED})
        # Every status counts, except a failed payment: that order holds nothing.
        self.assertEqual(set(HOLD_STATUSES) | set(SOLD_STATUSES), set(OrderStatus.values) - {OrderStatus.PAYMENT_FAILED})

    def test_a_failed_payment_holds_nothing(self):
        make_order(self.cafe, OrderStatus.PAYMENT_FAILED, (self.kopi, 5))
        self.assertEqual(ordered_quantities([self.cafe.pk]), {})

    def test_sums_on_hold_and_sold_by_status(self):
        make_order(self.cafe, OrderStatus.PENDING_PAYMENT, (self.kopi, 2), (self.toast, 1))
        make_order(self.cafe, OrderStatus.PAYMENT_RECEIVED, (self.kopi, 3))
        make_order(self.cafe, OrderStatus.ORDER_COMPLETED, (self.kopi, 10), (self.toast, 4))
        make_order(self.cafe, OrderStatus.ORDER_COMPLETED, (self.toast, 1))
        self.assertEqual(ordered_quantities([self.cafe.pk]), {
            self.kopi.pk: Stock(on_hold=5, sold=10),
            self.toast.pk: Stock(on_hold=1, sold=5),
        })

    def test_products_without_orders_are_left_out(self):
        make_order(self.cafe, OrderStatus.PENDING_PAYMENT, (self.kopi, 1))
        stocks = ordered_quantities([self.cafe.pk])
        self.assertNotIn(self.cake.pk, stocks)
        self.assertEqual(stocks.get(self.cake.pk, Stock()), Stock(on_hold=0, sold=0))

    def test_only_the_given_businesses_and_products(self):
        make_order(self.cafe, OrderStatus.PENDING_PAYMENT, (self.kopi, 1), (self.toast, 2))
        make_order(self.florist, OrderStatus.ORDER_COMPLETED, (self.rose, 7))
        self.assertEqual(ordered_quantities([self.florist.pk]), {self.rose.pk: Stock(sold=7)})
        self.assertEqual(ordered_quantities([self.cafe.pk], [self.toast.pk]), {self.toast.pk: Stock(on_hold=2)})
        self.assertEqual(ordered_quantities([self.cafe.pk, self.florist.pk]).keys(), {self.kopi.pk, self.toast.pk, self.rose.pk})
        self.assertEqual(ordered_quantities([]), {})

    def test_one_query(self):
        for _ in range(5):
            make_order(self.cafe, OrderStatus.PENDING_PAYMENT, (self.kopi, 1), (self.toast, 1))
        with self.assertNumQueries(1):
            ordered_quantities([self.cafe.pk])

    def test_committed(self):
        self.assertEqual(Stock(on_hold=2, sold=3).committed, 5)


class ProductDerivedQuantityTests(TestCase):
    """Product.quantity_on_hold / quantity_sold / quantity_available, derived from the orders."""

    @classmethod
    def setUpTestData(cls):
        cls.cafe = BusinessConfiguration.objects.create(business_name='Kopi Café', location='Singapore')
        cls.florist = BusinessConfiguration.objects.create(business_name='Florist', location='Singapore')

    def setUp(self):
        self.kopi = Product.objects.create(business=self.cafe, name='Kopi C', price='1.80', total_quantity=100)
        self.toast = Product.objects.create(business=self.cafe, name='Kaya Toast Set', price='5.50', total_quantity=20)

    def quantities(self, product):
        product.refresh_from_db()
        return product.total_quantity, product.quantity_available, product.quantity_on_hold, product.quantity_sold

    def test_no_orders_everything_is_available(self):
        self.assertEqual(self.quantities(self.kopi), (100, 100, 0, 0))
        unsaved = Product(business=self.cafe, name='New', price='1.00', total_quantity=7)
        self.assertEqual((unsaved.quantity_available, unsaved.quantity_on_hold, unsaved.quantity_sold), (7, 0, 0))

    def test_available_is_total_minus_on_hold_and_sold(self):
        make_order(self.cafe, OrderStatus.PENDING_PAYMENT, (self.kopi, 2))
        make_order(self.cafe, OrderStatus.PAYMENT_RECEIVED, (self.kopi, 3))
        make_order(self.cafe, OrderStatus.ORDER_COMPLETED, (self.kopi, 10))
        self.assertEqual(self.quantities(self.kopi), (100, 85, 5, 10))
        self.assertEqual(self.quantities(self.toast), (20, 20, 0, 0))

    def test_completing_an_order_moves_it_from_on_hold_to_sold(self):
        order = make_order(self.cafe, OrderStatus.PENDING_PAYMENT, (self.kopi, 4))
        self.assertEqual(self.quantities(self.kopi), (100, 96, 4, 0))
        order.order_status = OrderStatus.PAYMENT_RECEIVED
        order.save()
        self.assertEqual(self.quantities(self.kopi), (100, 96, 4, 0))
        order.order_status = OrderStatus.ORDER_COMPLETED
        order.save()
        self.assertEqual(self.quantities(self.kopi), (100, 96, 0, 4))  # available doesn't change

    def test_deleting_an_order_frees_its_quantity(self):
        order = make_order(self.cafe, OrderStatus.PENDING_PAYMENT, (self.kopi, 4))
        order.delete()
        self.assertEqual(self.quantities(self.kopi), (100, 100, 0, 0))

    def test_adding_stock_raises_available_only(self):
        make_order(self.cafe, OrderStatus.ORDER_COMPLETED, (self.kopi, 10))
        self.kopi.total_quantity += 50
        self.kopi.save()
        self.assertEqual(self.quantities(self.kopi), (150, 140, 0, 10))

    def test_load_stock_loads_many_products_in_one_query(self):
        make_order(self.cafe, OrderStatus.PENDING_PAYMENT, (self.kopi, 1), (self.toast, 2))
        products = list(Product.objects.order_by('pk'))
        with self.assertNumQueries(1):
            Product.load_stock(products)
        with self.assertNumQueries(0):
            self.assertEqual([p.quantity_on_hold for p in products], [1, 2])

    def test_quantities_are_loaded_once_and_refreshed_with_refresh_from_db(self):
        self.assertEqual(self.kopi.quantity_available, 100)
        make_order(self.cafe, OrderStatus.PENDING_PAYMENT, (self.kopi, 1))
        with self.assertNumQueries(0):
            self.assertEqual(self.kopi.quantity_available, 100)  # loaded before the order
        self.kopi.refresh_from_db()
        self.assertEqual(self.kopi.quantity_available, 99)

    def test_other_businesses_orders_do_not_count(self):
        # A (malformed) order of another business naming this product isn't counted.
        make_order(self.florist, OrderStatus.PENDING_PAYMENT, (self.kopi, 5))
        self.assertEqual(self.quantities(self.kopi), (100, 100, 0, 0))

    def test_total_cannot_go_below_on_hold_plus_sold(self):
        make_order(self.cafe, OrderStatus.PENDING_PAYMENT, (self.toast, 3))
        make_order(self.cafe, OrderStatus.ORDER_COMPLETED, (self.toast, 5))
        self.toast.total_quantity = 8  # available 0: fine
        self.toast.full_clean()
        self.toast.total_quantity = 7
        with self.assertRaises(ValidationError) as ctx:
            self.toast.full_clean()
        self.assertEqual(
            ctx.exception.message_dict['total_quantity'],
            ['Must be at least 8 (3 on hold and 5 sold in orders), so the quantity available is not negative.'],
        )

    def test_clean_uses_the_latest_orders(self):
        self.assertEqual(self.toast.quantity_available, 20)  # loaded before the order below
        make_order(self.cafe, OrderStatus.PENDING_PAYMENT, (self.toast, 15))
        self.toast.total_quantity = 10
        with self.assertRaises(ValidationError):
            self.toast.full_clean()
