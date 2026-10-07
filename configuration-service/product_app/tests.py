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
        product = self.make_product(quantity_available=10)
        product.full_clean()
        product.save()
        self.assertTrue(product.is_active)
        self.assertEqual(product.quantity_on_hold, 0)

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

    def test_negative_quantities_rejected(self):
        for field in ('quantity_available', 'quantity_on_hold', 'quantity_sold'):
            with self.subTest(field=field):
                with self.assertRaises(ValidationError) as ctx:
                    self.make_product(**{field: -1}).full_clean()
                self.assertIn(field, ctx.exception.message_dict)
                with self.assertRaises(IntegrityError), transaction.atomic():
                    self.make_product(**{field: -1}).save()

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
    fixtures = ['sample_business_configurations', 'sample_products', 'sample_faqs']

    def test_fixtures_are_valid(self):
        self.assertEqual(Product.objects.count(), 10)
        self.assertEqual(FAQ.objects.count(), 16)
        for record in [*Product.objects.all(), *FAQ.objects.all()]:
            with self.subTest(record=str(record)):
                record.full_clean()  # loaddata skips validation

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

