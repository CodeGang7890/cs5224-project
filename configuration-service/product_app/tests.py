from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase

from configuration_app.models import BusinessConfiguration

from .models import (
    FAQ,
    FAQ_ANSWER_MAX_LENGTH,
    PRODUCT_DESCRIPTION_MAX_LENGTH,
    PRODUCT_INFORMATION_MAX_LENGTH,
    QUANTITY_MAX,
    Product,
)


class ProductModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.business = BusinessConfiguration.objects.create(
            business_name='Test Café', location='Singapore'
        )

    def make_product(self, **overrides):
        fields = {'business': self.business, 'name': 'Latte', 'price': Decimal('4.50')}
        return Product(**{**fields, **overrides})

    def test_valid_product(self):
        product = self.make_product(total_quantity=10)
        product.full_clean()
        product.save()
        self.assertTrue(product.is_active)
        self.assertEqual((product.quantity_available, product.quantity_on_hold, product.quantity_sold), (10, 0, 0))

    def test_total_quantity_defaults_to_zero(self):
        product = self.make_product()
        product.full_clean()
        self.assertEqual((product.total_quantity, product.quantity_available), (0, 0))

    def test_negative_price_rejected_by_validation(self):
        with self.assertRaises(ValidationError) as ctx:
            self.make_product(price=Decimal('-0.01')).full_clean()
        self.assertIn('price', ctx.exception.message_dict)

    def test_negative_price_rejected_by_database(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.make_product(price=Decimal('-1')).save()

    def test_price_limited_to_two_decimal_places(self):
        with self.assertRaises(ValidationError):
            self.make_product(price=Decimal('1.999')).full_clean()

    def test_negative_total_quantity_rejected(self):
        with self.assertRaises(ValidationError) as ctx:
            self.make_product(total_quantity=-1).full_clean()
        self.assertIn('total_quantity', ctx.exception.message_dict)
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.make_product(total_quantity=-1).save()

    def test_total_quantity_limit(self):
        self.make_product(total_quantity=QUANTITY_MAX).full_clean()
        with self.assertRaises(ValidationError):
            self.make_product(total_quantity=QUANTITY_MAX + 1).full_clean()

    def test_description_and_information_length_limits(self):
        self.assertEqual((PRODUCT_DESCRIPTION_MAX_LENGTH, PRODUCT_INFORMATION_MAX_LENGTH), (300, 5000))
        for field, limit in (('description', PRODUCT_DESCRIPTION_MAX_LENGTH), ('information', PRODUCT_INFORMATION_MAX_LENGTH)):
            with self.subTest(field=field):
                self.make_product(**{field: 'x' * limit}).full_clean()
                with self.assertRaises(ValidationError) as ctx:
                    self.make_product(**{field: 'x' * (limit + 1)}).full_clean()
                self.assertIn(field, ctx.exception.message_dict)

    def test_description_and_information_are_optional(self):
        product = self.make_product()
        product.full_clean()
        self.assertEqual((product.description, product.information), ('', ''))

    def test_name_unique_per_business(self):
        self.make_product().save()
        with self.assertRaises(ValidationError):
            self.make_product().full_clean()
        other = BusinessConfiguration.objects.create(business_name='Other', location='Singapore')
        self.make_product(business=other).full_clean()  # same name, different business: OK

    def test_empty_name_rejected_by_database(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.make_product(name='').save()


class FAQModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.business = BusinessConfiguration.objects.create(
            business_name='Test Café', location='Singapore'
        )

    def test_long_answer_allowed_up_to_limit(self):
        FAQ(business=self.business, question='Q?', answer='x' * FAQ_ANSWER_MAX_LENGTH).full_clean()

    def test_answer_over_limit_rejected(self):
        faq = FAQ(business=self.business, question='Q?', answer='x' * (FAQ_ANSWER_MAX_LENGTH + 1))
        with self.assertRaises(ValidationError):
            faq.full_clean()

    def test_question_unique_per_business(self):
        FAQ.objects.create(business=self.business, question='Open?', answer='Yes')
        with self.assertRaises(ValidationError):
            FAQ(business=self.business, question='Open?', answer='Still yes').full_clean()

    def test_deleting_business_deletes_products_and_faqs(self):
        Product.objects.create(business=self.business, name='Latte', price=Decimal('4.50'))
        FAQ.objects.create(business=self.business, question='Open?', answer='Yes')
        self.business.delete()
        self.assertEqual(Product.objects.count(), 0)
        self.assertEqual(FAQ.objects.count(), 0)


class SampleProductAndFAQFixtureTests(TestCase):
    fixtures = ['sample_business_configurations', 'sample_products', 'sample_faqs', 'sample_order_items']

    def test_fixtures_are_valid(self):
        self.assertEqual(Product.objects.count(), 19)
        self.assertEqual(FAQ.objects.count(), 32)
        for record in [*Product.objects.all(), *FAQ.objects.all()]:
            with self.subTest(record=str(record)):
                record.full_clean()  # loaddata skips validation

    def test_no_product_is_oversold(self):
        for product in Product.load_stock(Product.objects.all()):
            with self.subTest(product=product.name):
                self.assertGreaterEqual(product.quantity_available, 0)
                product.full_clean()  # includes total_quantity ≥ on hold + sold

    def test_cafe_has_detailed_products_and_faqs(self):
        # Kopi & Co. Café (business 1) is the main test business for the chat assistant.
        cafe_products = Product.objects.filter(business_id=1, is_active=True)
        self.assertEqual(
            sorted(cafe_products.values_list('name', flat=True)),
            ['Iced Teh Tarik', 'Kaya Toast Set', 'Kopi C', 'Pandan Chiffon Cake (Whole)'],
        )
        for product in cafe_products:
            with self.subTest(product=product.name):
                self.assertTrue(product.description)  # a short summary
                self.assertGreater(len(product.information), 500)  # long enough to need get_product_details
        self.assertEqual(FAQ.objects.filter(business_id=1).count(), 12)

    def test_florist_has_a_realistic_catalogue_and_faqs(self):
        # Bloom & Twine Florist Studio (business 2): fresh, dried / preserved, soap and crochet flowers.
        products = Product.objects.filter(business_id=2)
        self.assertEqual(products.count(), 12)
        self.assertTrue(all(product.is_active for product in products))
        collections = {}
        for product in products:
            with self.subTest(product=product.name):
                sentences = [s for s in product.description.replace('!', '.').split('. ') if s.strip()]
                self.assertLessEqual(len(sentences), 2)  # 1-2 sentences
                self.assertGreater(len(product.information), 1000)  # the long details
                kind = product.information.split('\n', 1)[0]
                self.assertRegex(kind, r'^Type: (fresh|dried|preserved|soap|crochet) flowers')
                collections.setdefault(kind.split()[1], []).append(product.name)
                # Only the product itself (materials, care, allergies…): no prices, variants or logistics.
                self.assertNotRegex(product.information, r'(?i)\$|deliver|bulk|upgrade|add-on|colours:|made to order')
        self.assertEqual({key: len(names) for key, names in collections.items()},
                         {'fresh': 3, 'dried': 2, 'preserved': 1, 'soap': 3, 'crochet': 3})
        self.assertEqual(
            sorted(p.name for p in Product.load_stock(products) if p.quantity_available == 0),
            ['Crochet Forever Rose Bouquet (12 Stems)'],
        )
        bell_jar = Product.objects.get(name='Preserved Rose Bell Jar')
        self.assertEqual((bell_jar.total_quantity, bell_jar.quantity_available), (4, 1))  # the last one
        prices = sorted(products.values_list('price', flat=True))
        self.assertLess(prices[0], Decimal('10'))
        self.assertGreater(prices[-1], Decimal('200'))
        self.assertGreaterEqual(FAQ.objects.filter(business_id=2).count(), 15)


class ProductInformationMigrationTests(TransactionTestCase):
    """0003_product_information: a description longer than the new 300 limit moves to `information`."""

    before = [('product_app', '0002_product_quantity_max'), ('configuration_app', '0001_initial')]
    after = [('product_app', '0003_product_information')]

    def migrate(self, targets):
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(targets)
        return executor.loader.project_state(targets).apps

    def tearDown(self):
        self.migrate(MigrationExecutor(connection).loader.graph.leaf_nodes())

    def test_long_descriptions_move_to_information(self):
        apps = self.migrate(self.before)
        business = apps.get_model('configuration_app', 'BusinessConfiguration').objects.create(
            business_name='Café', location='SG'
        )
        Product = apps.get_model('product_app', 'Product')
        long_text = 'Made fresh every morning.\n\n' + 'Contains eggs and wheat. ' * 40
        long_product = Product.objects.create(business=business, name='Cake', price='28.00', description=long_text)
        short_product = Product.objects.create(business=business, name='Tea', price='2.00', description='Black tea.')

        Product = self.migrate(self.after).get_model('product_app', 'Product')
        long_product = Product.objects.get(pk=long_product.pk)
        self.assertEqual(long_product.information, long_text)
        self.assertLessEqual(len(long_product.description), PRODUCT_DESCRIPTION_MAX_LENGTH)
        self.assertTrue(long_product.description.startswith('Made fresh every morning. Contains eggs'))
        self.assertTrue(long_product.description.endswith('…'))
        short_product = Product.objects.get(pk=short_product.pk)
        self.assertEqual((short_product.description, short_product.information), ('Black tea.', ''))

        # And back: the long description is restored.
        Product = self.migrate(self.before).get_model('product_app', 'Product')
        self.assertEqual(Product.objects.get(pk=long_product.pk).description, long_text)



class ProductTotalQuantityMigrationTests(TransactionTestCase):
    """0004_product_total_quantity: the three stored quantities become one total_quantity."""

    before = [('product_app', '0003_product_information'), ('configuration_app', '0001_initial')]
    after = [('product_app', '0004_product_total_quantity')]

    def migrate(self, targets):
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(targets)
        return executor.loader.project_state(targets).apps

    def tearDown(self):
        self.migrate(MigrationExecutor(connection).loader.graph.leaf_nodes())

    def test_total_is_available_plus_on_hold_plus_sold(self):
        apps = self.migrate(self.before)
        business = apps.get_model('configuration_app', 'BusinessConfiguration').objects.create(
            business_name='Café', location='SG'
        )
        Product = apps.get_model('product_app', 'Product')
        product = Product.objects.create(
            business=business, name='Kopi', price='1.80', quantity_available=5, quantity_on_hold=2, quantity_sold=3
        )

        Product = self.migrate(self.after).get_model('product_app', 'Product')
        self.assertEqual(Product.objects.get(pk=product.pk).total_quantity, 10)

        # And back: everything counts as available.
        Product = self.migrate(self.before).get_model('product_app', 'Product')
        reverted = Product.objects.get(pk=product.pk)
        self.assertEqual((reverted.quantity_available, reverted.quantity_on_hold, reverted.quantity_sold), (10, 0, 0))


class ProductAdminTests(TestCase):
    """Django Admin shows the derived quantities and keeps total_quantity ≥ on hold + sold."""

    fixtures = ['sample_business_configurations', 'sample_products', 'sample_order_items']

    def setUp(self):
        from auth_app.models import BusinessUser

        self.client.force_login(BusinessUser.objects.create_superuser(username='admin', password='pw'))

    def test_changelist_shows_derived_quantities_with_one_orders_query(self):
        from django.test.utils import CaptureQueriesContext
        from django.urls import reverse

        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(reverse('admin:product_app_product_changelist'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Quantity available')
        order_queries = [q for q in queries if 'checkout_app_orderitem' in q['sql']]
        self.assertEqual(len(order_queries), 1)  # not one per product

    def test_change_form_rejects_total_below_on_hold_plus_sold(self):
        from django.urls import reverse

        bell_jar = Product.objects.get(name='Preserved Rose Bell Jar')  # 4 in total, 3 in orders
        url = reverse('admin:product_app_product_change', args=[bell_jar.pk])
        form = {
            'business': bell_jar.business_id, 'name': bell_jar.name, 'description': bell_jar.description,
            'information': bell_jar.information, 'price': str(bell_jar.price), 'total_quantity': 2, 'is_active': 'on',
        }
        response = self.client.post(url, form)
        self.assertEqual(response.status_code, 200)  # the form again, with the error
        self.assertContains(response, 'Must be at least 3 (1 on hold and 2 sold in orders)')
        bell_jar.refresh_from_db()
        self.assertEqual(bell_jar.total_quantity, 4)
        response = self.client.post(url, {**form, 'total_quantity': 10})
        self.assertEqual(response.status_code, 302)
        bell_jar.refresh_from_db()
        self.assertEqual(bell_jar.quantity_available, 7)
