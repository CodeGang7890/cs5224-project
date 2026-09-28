from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from configuration_app.models import BusinessConfiguration

from .models import FAQ, FAQ_ANSWER_MAX_LENGTH, PRODUCT_DESCRIPTION_MAX_LENGTH, Product


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

    def test_description_length_limit(self):
        with self.assertRaises(ValidationError):
            self.make_product(description='x' * (PRODUCT_DESCRIPTION_MAX_LENGTH + 1)).full_clean()

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
