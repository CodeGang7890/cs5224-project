import base64
from datetime import datetime, timedelta
from decimal import Decimal

from django.core.cache import cache
from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from auth_app.models import BusinessUser
from checkout_app.models import OrderItem, OrderStatus
from chat_app.models import ChatSession
from checkout_app.models import ScheduleItem
from checkout_app.tests.test_schedule import at, book, future_monday, open_week
from configuration_app.models import BusinessConfiguration

from .models import (
    FAQ,
    FAQ_ANSWER_MAX_LENGTH,
    PRODUCT_DESCRIPTION_MAX_LENGTH,
    PRODUCT_INFORMATION_MAX_LENGTH,
    PRODUCT_NAME_MAX_LENGTH,
    QUANTITY_MAX,
    Product,
    Service,
    ServiceProvider,
    WeeklyAvailability,
)
from .serializers import DERIVED_QUANTITY_ERROR, DERIVED_QUANTITY_FIELDS, ProductSerializer
from .tests import open_hours


class BusinessAPITestCase(APITestCase):
    """Two businesses, each with a user, a product and an FAQ; plus a user with no business."""

    @classmethod
    def setUpTestData(cls):
        cls.cafe = BusinessConfiguration.objects.create(business_name='Café', location='Singapore')
        cls.florist = BusinessConfiguration.objects.create(business_name='Florist', location='Singapore')

        cls.cafe_user = BusinessUser.objects.create_user(username='cafe', password='123', business=cls.cafe)
        cls.florist_user = BusinessUser.objects.create_user(
            username='florist', password='123', business=cls.florist
        )
        cls.no_business_user = BusinessUser.objects.create_user(username='nobiz', password='123')

        # 13 in total, 3 sold in a completed order: 10 available.
        cls.cafe_product = Product.objects.create(business=cls.cafe, name='Latte', price=Decimal('4.50'), total_quantity=13)
        OrderItem.objects.create(business=cls.cafe, order_status=OrderStatus.ORDER_COMPLETED, order_data={
            'items': [{'product_id': cls.cafe_product.pk, 'name': 'Latte', 'unit_price': '4.50', 'quantity': 3}], 'details': {},
        })
        cls.florist_product = Product.objects.create(
            business=cls.florist, name='Roses', price=Decimal('68.00')
        )
        cls.cafe_faq = FAQ.objects.create(business=cls.cafe, question='Open?', answer='7am to 6pm.')
        cls.florist_faq = FAQ.objects.create(business=cls.florist, question='Delivery?', answer='Yes.')

    def login(self, user):
        self.client.force_authenticate(user)


class ProductAPITests(BusinessAPITestCase):
    list_url = reverse('product_app:product-list')

    @staticmethod
    def detail_url(product):
        return reverse('product_app:product-detail', args=[product.pk])

    # --- Authentication -------------------------------------------------------------

    def test_requires_authentication(self):
        for method, url in [
            ('get', self.list_url),
            ('post', self.list_url),
            ('get', self.detail_url(self.cafe_product)),
            ('patch', self.detail_url(self.cafe_product)),
            ('delete', self.detail_url(self.cafe_product)),
        ]:
            with self.subTest(method=method, url=url):
                response = getattr(self.client, method)(url)
                self.assertIn(
                    response.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)
                )
        self.assertTrue(Product.objects.filter(pk=self.cafe_product.pk).exists())

    def test_basic_auth_login_works(self):
        # This is how Swagger UI's "Authorize" (basicAuth) sends credentials.
        token = base64.b64encode(b'cafe:123').decode()
        self.client.credentials(HTTP_AUTHORIZATION=f'Basic {token}')
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    # --- Own business ---------------------------------------------------------------

    def test_list_only_returns_own_business_products(self):
        self.login(self.cafe_user)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([p['id'] for p in response.data['results']], [self.cafe_product.pk])

    def test_create_defaults_to_own_business(self):
        self.login(self.cafe_user)
        response = self.client.post(
            self.list_url, {'name': 'Mocha', 'price': '5.20', 'total_quantity': 5}, format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        product = Product.objects.get(pk=response.data['id'])
        self.assertEqual(product.business, self.cafe)
        self.assertEqual(
            {key: response.data[key] for key in ('total_quantity', 'quantity_available', 'quantity_on_hold', 'quantity_sold')},
            {'total_quantity': 5, 'quantity_available': 5, 'quantity_on_hold': 0, 'quantity_sold': 0},
        )
        self.assertTrue(product.is_active)

    def test_create_and_update_description_and_information(self):
        self.login(self.cafe_user)
        description = 'd' * PRODUCT_DESCRIPTION_MAX_LENGTH
        information = 'i' * PRODUCT_INFORMATION_MAX_LENGTH
        response = self.client.post(
            self.list_url,
            {'name': 'Mocha', 'price': '5.20', 'description': description, 'information': information},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual((response.data['description'], response.data['information']), (description, information))
        product = Product.objects.get(pk=response.data['id'])
        self.assertEqual((product.description, product.information), (description, information))

        response = self.client.patch(self.detail_url(product), {'information': 'Contains dairy.'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        product.refresh_from_db()
        self.assertEqual((product.description, product.information), (description, 'Contains dairy.'))

    def test_information_defaults_to_blank(self):
        self.login(self.cafe_user)
        response = self.client.post(self.list_url, {'name': 'Mocha', 'price': '5.20'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual((response.data['description'], response.data['information']), ('', ''))

    def test_create_with_own_business_explicitly(self):
        self.login(self.cafe_user)
        response = self.client.post(
            self.list_url, {'business': self.cafe.pk, 'name': 'Mocha', 'price': '5.20'}, format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

    def test_retrieve_own_product(self):
        self.login(self.cafe_user)
        response = self.client.get(self.detail_url(self.cafe_product))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['name'], 'Latte')
        self.assertEqual(response.data['total_quantity'], 13)
        self.assertEqual(response.data['quantity_sold'], 3)
        self.assertEqual(response.data['quantity_available'], 10)

    def test_update_own_product(self):
        self.login(self.cafe_user)
        response = self.client.patch(
            self.detail_url(self.cafe_product),
            {'name': 'Iced Latte', 'price': '5.00', 'total_quantity': 20, 'is_active': False},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.cafe_product.refresh_from_db()
        self.assertEqual(self.cafe_product.name, 'Iced Latte')
        self.assertEqual(self.cafe_product.price, Decimal('5.00'))
        self.assertEqual(self.cafe_product.total_quantity, 20)
        self.assertFalse(self.cafe_product.is_active)

    def test_full_update_own_product(self):
        self.login(self.cafe_user)
        response = self.client.put(
            self.detail_url(self.cafe_product),
            {'name': 'Flat White', 'price': '4.80', 'total_quantity': 8},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.cafe_product.refresh_from_db()
        self.assertEqual(self.cafe_product.name, 'Flat White')
        self.assertEqual(self.cafe_product.business, self.cafe)
        self.assertEqual(self.cafe_product.total_quantity, 8)

    def test_full_update_without_total_quantity_keeps_it(self):
        self.login(self.cafe_user)
        response = self.client.put(self.detail_url(self.cafe_product), {'name': 'Latte', 'price': '4.50'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.cafe_product.refresh_from_db()
        self.assertEqual(self.cafe_product.total_quantity, 13)

    def test_delete_own_product(self):
        self.login(self.cafe_user)
        response = self.client.delete(self.detail_url(self.cafe_product))
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Product.objects.filter(pk=self.cafe_product.pk).exists())

    # --- Other business: 403 --------------------------------------------------------

    def test_other_business_product_is_forbidden(self):
        self.login(self.cafe_user)
        url = self.detail_url(self.florist_product)
        for method, data in [('get', None), ('put', {'name': 'X', 'price': '1'}), ('patch', {'name': 'X'}), ('delete', None)]:
            with self.subTest(method=method):
                response = getattr(self.client, method)(url, data, format='json')
                self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.florist_product.refresh_from_db()
        self.assertEqual(self.florist_product.name, 'Roses')

    def test_create_for_other_business_is_forbidden(self):
        self.login(self.cafe_user)
        response = self.client.post(
            self.list_url, {'business': self.florist.pk, 'name': 'Tulips', 'price': '10.00'}, format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(Product.objects.filter(name='Tulips').exists())

    def test_moving_product_to_other_business_is_forbidden(self):
        self.login(self.cafe_user)
        response = self.client.patch(
            self.detail_url(self.cafe_product), {'business': self.florist.pk}, format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.cafe_product.refresh_from_db()
        self.assertEqual(self.cafe_product.business, self.cafe)

    def test_user_without_business_cannot_create_or_access(self):
        self.login(self.no_business_user)
        response = self.client.post(self.list_url, {'name': 'X', 'price': '1.00'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.get(self.detail_url(self.cafe_product)).status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.get(self.list_url).data['results'], [])

    # --- Derived quantities are read-only --------------------------------------------

    def test_derived_quantities_cannot_be_edited(self):
        self.login(self.cafe_user)
        for field in DERIVED_QUANTITY_FIELDS:
            with self.subTest(field):
                response = self.client.patch(self.detail_url(self.cafe_product), {field: 99}, format='json')
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertEqual(response.data, {field: [DERIVED_QUANTITY_ERROR]})
        self.cafe_product.refresh_from_db()
        self.assertEqual((self.cafe_product.total_quantity, self.cafe_product.quantity_sold), (13, 3))

    def test_derived_quantities_cannot_be_set_on_create(self):
        self.login(self.cafe_user)
        for field in DERIVED_QUANTITY_FIELDS:
            with self.subTest(field):
                response = self.client.post(self.list_url, {'name': 'Mocha', 'price': '5.20', field: 10}, format='json')
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn(field, response.data)
        self.assertFalse(Product.objects.filter(name='Mocha').exists())

    def test_derived_quantity_errors_are_reported_with_other_errors(self):
        self.login(self.cafe_user)
        response = self.client.patch(
            self.detail_url(self.cafe_product), {'quantity_available': 5, 'price': '-1'}, format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(set(response.data), {'quantity_available', 'price'})

    # --- Validation -----------------------------------------------------------------

    def test_validation_errors(self):
        self.login(self.cafe_user)
        cases = {
            'negative total_quantity': ({'total_quantity': -1}, 'total_quantity'),
            'total_quantity too large': ({'total_quantity': QUANTITY_MAX + 1}, 'total_quantity'),
            'non-integer total_quantity': ({'total_quantity': 'lots'}, 'total_quantity'),
            'negative price': ({'price': '-0.01'}, 'price'),
            'too many decimals': ({'price': '1.999'}, 'price'),
            'price too large': ({'price': '100000000.00'}, 'price'),
            'name too long': ({'name': 'x' * (PRODUCT_NAME_MAX_LENGTH + 1)}, 'name'),
            'blank name': ({'name': '   '}, 'name'),
            'description too long': ({'description': 'x' * (PRODUCT_DESCRIPTION_MAX_LENGTH + 1)}, 'description'),
            'information too long': ({'information': 'x' * (PRODUCT_INFORMATION_MAX_LENGTH + 1)}, 'information'),
            'non-numeric price': ({'price': 'free'}, 'price'),
        }
        for label, (data, field) in cases.items():
            with self.subTest(label):
                response = self.client.patch(self.detail_url(self.cafe_product), data, format='json')
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn(field, response.data)

    def test_create_requires_name_and_price(self):
        self.login(self.cafe_user)
        response = self.client.post(self.list_url, {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(set(response.data), {'name', 'price'})

    def test_duplicate_name_in_same_business_rejected(self):
        self.login(self.cafe_user)
        response = self.client.post(self.list_url, {'name': 'Latte', 'price': '4.00'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_same_name_in_other_business_allowed(self):
        self.login(self.florist_user)
        response = self.client.post(self.list_url, {'name': 'Latte', 'price': '4.00'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)


class FAQAPITests(BusinessAPITestCase):
    list_url = reverse('product_app:faq-list')

    @staticmethod
    def detail_url(faq):
        return reverse('product_app:faq-detail', args=[faq.pk])

    def test_requires_authentication(self):
        self.assertIn(
            self.client.get(self.list_url).status_code,
            (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
        )

    def test_list_only_returns_own_business_faqs(self):
        self.login(self.cafe_user)
        response = self.client.get(self.list_url)
        self.assertEqual([f['id'] for f in response.data['results']], [self.cafe_faq.pk])

    def test_crud_own_faq(self):
        self.login(self.cafe_user)
        response = self.client.post(
            self.list_url, {'question': 'Wi-Fi?', 'answer': 'Free for customers.'}, format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        faq_url = reverse('product_app:faq-detail', args=[response.data['id']])
        self.assertEqual(FAQ.objects.get(pk=response.data['id']).business, self.cafe)

        response = self.client.patch(faq_url, {'answer': 'Free, password on receipt.'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['answer'], 'Free, password on receipt.')

        self.assertEqual(self.client.get(faq_url).status_code, status.HTTP_200_OK)
        self.assertEqual(self.client.delete(faq_url).status_code, status.HTTP_204_NO_CONTENT)

    def test_other_business_faq_is_forbidden(self):
        self.login(self.cafe_user)
        url = self.detail_url(self.florist_faq)
        for method, data in [('get', None), ('patch', {'answer': 'No.'}), ('delete', None)]:
            with self.subTest(method=method):
                response = getattr(self.client, method)(url, data, format='json')
                self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(FAQ.objects.filter(pk=self.florist_faq.pk, answer='Yes.').exists())

    def test_create_for_other_business_is_forbidden(self):
        self.login(self.cafe_user)
        response = self.client.post(
            self.list_url, {'business': self.florist.pk, 'question': 'Q?', 'answer': 'A.'}, format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_validation_errors(self):
        self.login(self.cafe_user)
        cases = {
            'answer too long': ({'answer': 'x' * (FAQ_ANSWER_MAX_LENGTH + 1)}, 'answer'),
            'question too long': ({'question': 'x' * 301}, 'question'),
            'blank question': ({'question': ''}, 'question'),
            'duplicate question': ({'question': 'Open?', 'answer': 'Again.'}, 'non_field_errors'),
        }
        for label, (data, field) in cases.items():
            with self.subTest(label):
                payload = {'question': 'New?', 'answer': 'Yes.', **data}
                response = self.client.post(self.list_url, payload, format='json')
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn(field, response.data)

    def test_long_answer_within_limit_accepted(self):
        self.login(self.cafe_user)
        response = self.client.post(
            self.list_url,
            {'question': 'Long?', 'answer': 'x' * FAQ_ANSWER_MAX_LENGTH},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)


class BusinessListAPITests(BusinessAPITestCase):
    """GET /api/businesses/<business_id>/products/ and /api/businesses/<business_id>/faqs/"""

    MISSING_BUSINESS_ID = 999_999

    @staticmethod
    def products_url(business_id):
        return reverse('product_app:business-product-list', args=[business_id])

    @staticmethod
    def faqs_url(business_id):
        return reverse('product_app:business-faq-list', args=[business_id])

    def both_urls(self, business_id):
        return {'products': self.products_url(business_id), 'faqs': self.faqs_url(business_id)}

    # --- 200 ------------------------------------------------------------------------

    def test_lists_all_products_of_own_business(self):
        inactive = Product.objects.create(
            business=self.cafe, name='Old Blend', price=Decimal('3.00'), is_active=False
        )
        self.login(self.cafe_user)
        response = self.client.get(self.products_url(self.cafe.pk))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 2)
        self.assertEqual(
            {p['id'] for p in response.data['results']}, {self.cafe_product.pk, inactive.pk}
        )
        self.assertTrue(all(p['business'] == self.cafe.pk for p in response.data['results']))
        self.assertEqual(set(response.data['results'][0]), set(ProductSerializer.Meta.fields))

    def test_lists_all_faqs_of_own_business(self):
        self.login(self.florist_user)
        response = self.client.get(self.faqs_url(self.florist.pk))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([f['id'] for f in response.data['results']], [self.florist_faq.pk])
        self.assertEqual(response.data['results'][0]['question'], 'Delivery?')

    def test_empty_business_returns_empty_list(self):
        empty = BusinessConfiguration.objects.create(business_name='New Shop', location='Singapore')
        user = BusinessUser.objects.create_user(username='newshop', password='123', business=empty)
        self.login(user)
        for name, url in self.both_urls(empty.pk).items():
            with self.subTest(name):
                response = self.client.get(url)
                self.assertEqual(response.status_code, status.HTTP_200_OK)
                self.assertEqual(response.data['count'], 0)
                self.assertEqual(response.data['results'], [])

    def test_results_are_paginated(self):
        Product.objects.bulk_create(
            Product(business=self.cafe, name=f'Item {i:02}', price=Decimal('1.00')) for i in range(25)
        )
        self.login(self.cafe_user)
        first = self.client.get(self.products_url(self.cafe.pk))
        self.assertEqual(first.data['count'], 26)
        self.assertEqual(len(first.data['results']), 20)
        self.assertIsNotNone(first.data['next'])
        second = self.client.get(self.products_url(self.cafe.pk), {'page': 2})
        self.assertEqual(len(second.data['results']), 6)

    def test_bearer_token_works(self):
        cache.clear()  # the login rate limit counts in the cache, across the whole test run
        tokens = self.client.post(
            reverse('auth_app:token-obtain'), {'username': 'cafe', 'password': '123'}, format='json'
        ).data
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
        self.assertEqual(self.client.get(self.products_url(self.cafe.pk)).status_code, status.HTTP_200_OK)

    # --- 400: business not found ----------------------------------------------------

    def test_unknown_business_id_returns_400(self):
        self.login(self.cafe_user)
        for name, url in self.both_urls(self.MISSING_BUSINESS_ID).items():
            with self.subTest(name):
                response = self.client.get(url)
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn('business_id', response.data)
                self.assertIn(str(self.MISSING_BUSINESS_ID), str(response.data['business_id'][0]))

    def test_non_numeric_business_id_is_not_routed(self):
        self.login(self.cafe_user)
        self.assertEqual(self.client.get('/api/businesses/abc/products/').status_code, status.HTTP_404_NOT_FOUND)

    # --- 401: not logged in ---------------------------------------------------------

    def test_not_logged_in_returns_401(self):
        for business_id in (self.cafe.pk, self.MISSING_BUSINESS_ID):
            for name, url in self.both_urls(business_id).items():
                with self.subTest(name, business_id=business_id):
                    self.assertEqual(self.client.get(url).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_invalid_token_returns_401(self):
        self.client.credentials(HTTP_AUTHORIZATION='Bearer not-a-token')
        for name, url in self.both_urls(self.cafe.pk).items():
            with self.subTest(name):
                self.assertEqual(self.client.get(url).status_code, status.HTTP_401_UNAUTHORIZED)

    # --- 403: not your business -----------------------------------------------------

    def test_other_business_returns_403(self):
        self.login(self.cafe_user)
        for name, url in self.both_urls(self.florist.pk).items():
            with self.subTest(name):
                response = self.client.get(url)
                self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
                self.assertNotIn('results', response.data)

    def test_user_without_business_returns_403(self):
        self.login(self.no_business_user)
        for name, url in self.both_urls(self.cafe.pk).items():
            with self.subTest(name):
                self.assertEqual(self.client.get(url).status_code, status.HTTP_403_FORBIDDEN)

    # --- Read-only ------------------------------------------------------------------

    def test_endpoints_are_read_only(self):
        self.login(self.cafe_user)
        for name, url in self.both_urls(self.cafe.pk).items():
            for method in ('post', 'put', 'patch', 'delete'):
                with self.subTest(name, method=method):
                    response = getattr(self.client, method)(url, {}, format='json')
                    self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)


class ProductQuantityAPITests(BusinessAPITestCase):
    """total_quantity is the only stored quantity; on hold / sold / available come from the orders."""

    list_url = reverse('product_app:product-list')

    @staticmethod
    def detail_url(product):
        return reverse('product_app:product-detail', args=[product.pk])

    def setUp(self):
        self.login(self.cafe_user)
        # Mocha: 20 in total; 2 pending payment + 3 paid = 5 on hold; 4 completed = 4 sold; 11 available.
        self.mocha = Product.objects.create(business=self.cafe, name='Mocha', price=Decimal('5.20'), total_quantity=20)
        for status_, quantity in (
            (OrderStatus.PENDING_PAYMENT, 2), (OrderStatus.PAYMENT_RECEIVED, 3), (OrderStatus.ORDER_COMPLETED, 4),
        ):
            self.order(self.cafe, status_, (self.mocha, quantity))

    @staticmethod
    def order(business, status_, *lines):
        return OrderItem.objects.create(business=business, order_status=status_, order_data={
            'items': [
                {'product_id': p.pk, 'name': p.name, 'unit_price': str(p.price), 'quantity': q} for p, q in lines
            ],
            'details': {},
        })

    def quantities(self, data):
        return tuple(data[key] for key in ('total_quantity', 'quantity_available', 'quantity_on_hold', 'quantity_sold'))

    def patch_total(self, total):
        return self.client.patch(self.detail_url(self.mocha), {'total_quantity': total}, format='json')

    def test_quantities_are_derived_from_orders(self):
        self.assertEqual(self.quantities(self.client.get(self.detail_url(self.mocha)).data), (20, 11, 5, 4))

    def test_list_derives_every_products_quantities(self):
        results = {p['name']: self.quantities(p) for p in self.client.get(self.list_url).data['results']}
        self.assertEqual(results, {'Latte': (13, 10, 0, 3), 'Mocha': (20, 11, 5, 4)})

    def test_list_reads_the_orders_once_however_many_products(self):
        def queries_for_list():
            from django.db import connection
            from django.test.utils import CaptureQueriesContext
            with CaptureQueriesContext(connection) as queries:
                self.assertEqual(self.client.get(self.list_url).status_code, status.HTTP_200_OK)
            return len(queries)

        before = queries_for_list()
        for index in range(5):
            product = Product.objects.create(business=self.cafe, name=f'Tea {index}', price='2.00', total_quantity=9)
            self.order(self.cafe, OrderStatus.PENDING_PAYMENT, (product, 1))
        self.assertEqual(queries_for_list(), before)

    def test_business_list_endpoint_has_the_derived_quantities(self):
        url = reverse('product_app:business-product-list', args=[self.cafe.pk])
        results = {p['name']: self.quantities(p) for p in self.client.get(url).data['results']}
        self.assertEqual(results['Mocha'], (20, 11, 5, 4))

    def test_other_businesses_orders_do_not_count(self):
        self.order(self.florist, OrderStatus.PENDING_PAYMENT, (self.florist_product, 1))
        self.assertEqual(self.quantities(self.client.get(self.detail_url(self.mocha)).data), (20, 11, 5, 4))

    def test_adding_stock(self):
        response = self.patch_total(50)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(self.quantities(response.data), (50, 41, 5, 4))

    def test_reducing_stock_down_to_nothing_available(self):
        response = self.patch_total(15)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(self.quantities(response.data), (15, 6, 5, 4))
        response = self.patch_total(9)  # on hold + sold: 0 available
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(self.quantities(response.data), (9, 0, 5, 4))

    def test_reducing_stock_below_on_hold_plus_sold_is_rejected(self):
        response = self.patch_total(8)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data, {'total_quantity': [
            'Must be at least 9 (5 on hold and 4 sold in orders), so the quantity available is not negative.'
        ]})
        self.mocha.refresh_from_db()
        self.assertEqual(self.mocha.total_quantity, 20)

    def test_rejected_reduction_changes_nothing_else(self):
        response = self.client.patch(self.detail_url(self.mocha), {'total_quantity': 0, 'name': 'Iced Mocha'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.mocha.refresh_from_db()
        self.assertEqual((self.mocha.name, self.mocha.total_quantity), ('Mocha', 20))

    def test_full_update_is_checked_too(self):
        response = self.client.put(
            self.detail_url(self.mocha), {'name': 'Mocha', 'price': '5.20', 'total_quantity': 1}, format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('total_quantity', response.data)

    def test_reduction_is_checked_against_the_latest_orders(self):
        self.client.get(self.detail_url(self.mocha))
        self.order(self.cafe, OrderStatus.PENDING_PAYMENT, (self.mocha, 6))  # placed since: 15 on hold + sold
        self.assertEqual(self.patch_total(12).status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.patch_total(15).status_code, status.HTTP_200_OK)

    def test_completing_an_order_keeps_available_the_same(self):
        pending = OrderItem.objects.filter(order_status=OrderStatus.PENDING_PAYMENT).get()
        pending.order_status = OrderStatus.ORDER_COMPLETED
        pending.save()
        self.assertEqual(self.quantities(self.client.get(self.detail_url(self.mocha)).data), (20, 11, 3, 6))

    def test_new_product_can_have_any_total(self):
        response = self.client.post(self.list_url, {'name': 'Tea', 'price': '2.00', 'total_quantity': 0}, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(self.quantities(response.data), (0, 0, 0, 0))

    def test_updating_other_fields_does_not_check_the_total(self):
        Product.objects.filter(pk=self.mocha.pk).update(total_quantity=1)  # e.g. orders placed in Django Admin
        response = self.client.patch(self.detail_url(self.mocha), {'price': '5.50'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(self.quantities(response.data), (1, -8, 5, 4))  # shown as it is, so it can be fixed
        self.assertEqual(self.patch_total(9).status_code, status.HTTP_200_OK)


# --- Service providers, their weeks, and services ------------------------------------------------

@override_settings(SCHEDULE_TIME_ZONE='Asia/Singapore')
class ScheduleAPITestCase(BusinessAPITestCase):
    """BusinessAPITestCase, plus two photographers and a service for the café, and the florist's own."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.mei = ServiceProvider.objects.create(business=cls.cafe, name='Mei', description='Lead photographer')
        cls.raj = ServiceProvider.objects.create(business=cls.cafe, name='Raj')
        cls.florist_provider = ServiceProvider.objects.create(business=cls.florist, name='Florist provider')
        cls.portrait = Service.objects.create(business=cls.cafe, name='Portrait', price='180.00', duration_minutes=60, buffer_minutes=15)
        cls.portrait.service_providers.set([cls.mei])
        cls.florist_service = Service.objects.create(business=cls.florist, name='Workshop', price='50.00', duration_minutes=120)
        cls.monday = future_monday()

    def setUp(self):
        self.week = open_week(self.mei, self.monday, (0, '09:00', '12:00'))


class ServiceProviderAPITests(ScheduleAPITestCase):
    list_url = reverse('product_app:service-provider-list')

    @staticmethod
    def detail_url(provider, action=None):
        if action:
            return reverse(f'product_app:service-provider-{action}', args=[provider.pk])
        return reverse('product_app:service-provider-detail', args=[provider.pk])

    def test_requires_login(self):
        self.assertEqual(self.client.get(self.list_url).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_crud(self):
        self.login(self.cafe_user)
        body = self.client.get(self.list_url).json()
        self.assertEqual(
            body['results'],
            [
                {'id': self.mei.pk, 'business': self.cafe.pk, 'name': 'Mei', 'description': 'Lead photographer', 'is_active': True, 'services': [self.portrait.pk]},
                {'id': self.raj.pk, 'business': self.cafe.pk, 'name': 'Raj', 'description': '', 'is_active': True, 'services': []},
            ],
        )
        response = self.client.post(self.list_url, {'name': 'Studio A', 'description': 'The big room'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.content)
        created = ServiceProvider.objects.get(pk=response.json()['id'])
        self.assertEqual((created.business, created.is_active), (self.cafe, True))
        self.assertEqual(self.client.patch(self.detail_url(created), {'is_active': False}, format='json').status_code, 200)
        self.assertEqual(self.client.delete(self.detail_url(created)).status_code, status.HTTP_204_NO_CONTENT)

    def test_invalid_input(self):
        self.login(self.cafe_user)
        for body, field in (({'name': ''}, 'name'), ({'name': 'Mei'}, 'non_field_errors'), ({'name': 'x', 'description': 'y' * 301}, 'description')):
            with self.subTest(body=body):
                response = self.client.post(self.list_url, body, format='json')
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn(field, response.json())

    def test_other_business(self):
        self.login(self.cafe_user)
        for action in (None, 'calendar'):
            with self.subTest(action=action):
                self.assertEqual(self.client.get(self.detail_url(self.florist_provider, action), {'week': self.monday.isoformat()}).status_code, 403)
        self.assertEqual(self.client.post(self.detail_url(self.florist_provider, 'slots'), {}, format='json').status_code, 403)
        self.assertEqual(self.client.post(self.detail_url(self.florist_provider, 'copy-week'), {}, format='json').status_code, 403)
        self.assertEqual(self.client.post(self.list_url, {'name': 'X', 'business': self.florist.pk}, format='json').status_code, 403)

    # --- Calendar -------------------------------------------------------------------

    def test_calendar_shows_the_week_and_who_booked(self):
        session = ChatSession.objects.create(business=self.cafe, is_sandbox=True)
        pending = book(self.portrait, self.mei, at(self.monday, '09:00'), chat_session=session, is_sandbox=True)
        pending.schedule_data['details'] = {'name': 'Alice', 'email': 'alice@example.com'}
        pending.save()
        paid = book(self.portrait, self.mei, at(self.monday, '10:30'), status=OrderStatus.PAYMENT_RECEIVED)
        self.login(self.cafe_user)
        response = self.client.get(self.detail_url(self.mei, 'calendar'), {'week': (self.monday + timedelta(days=4)).isoformat()})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.content)
        body = response.json()
        self.assertEqual((body['service_provider'], body['week'], body['id']), (self.mei.pk, self.monday.isoformat(), self.week.pk))
        # 09:00–10:15 on hold (with its buffer), 10:15–10:30 open, 10:30–11:45 booked, then open, closed.
        self.assertEqual(body['availability'][36:50], 'HHHHH' + 'O' + 'XXXXX' + 'O' + 'UU')
        self.assertEqual(len(body['bookings']), 2)
        first = body['bookings'][0]
        self.assertEqual(first, {
            'id': pending.pk, 'service': 'Portrait', 'customer': 'Alice', 'details': {'name': 'Alice', 'email': 'alice@example.com'},
            'start_time': first['start_time'], 'end_time': first['end_time'], 'blocked_until': first['blocked_until'],
            'order_status': 'pending_payment', 'payment_reference': pending.payment_reference, 'total': '180.00',
            'is_sandbox': True, 'chat_session': session.pk, 'start_block': 36, 'end_block': 40, 'until_block': 41,
        })
        self.assertEqual(body['time_zone'], 'Asia/Singapore')
        self.assertEqual(datetime.fromisoformat(first['blocked_until']), at(self.monday, '10:15'))
        self.assertEqual((body['bookings'][1]['id'], body['bookings'][1]['customer']), (paid.pk, None))
        self.assertEqual([body['bookings'][1][k] for k in ('start_block', 'end_block', 'until_block')], [42, 46, 47])

    def test_calendar_block_positions_of_a_booking_across_weeks(self):
        # Sunday 23:30 to Monday 00:30 (+ 15 min buffer): the first week sees blocks 670–674, the next -2–2.
        sunday = self.monday + timedelta(days=6)
        next_week = WeeklyAvailability.objects.create(
            service_provider=self.mei, week=self.monday + timedelta(weeks=1), availability='O' * 672
        )
        self.week.availability = 'O' * 672
        self.week.save()
        book(self.portrait, self.mei, at(sunday, '23:30'))
        self.login(self.cafe_user)
        url = self.detail_url(self.mei, 'calendar')
        first = self.client.get(url, {'week': self.monday.isoformat()}).json()
        second = self.client.get(url, {'week': next_week.week.isoformat()}).json()
        blocks = ('start_block', 'end_block', 'until_block')
        self.assertEqual([first['bookings'][0][k] for k in blocks], [670, 674, 675])
        self.assertEqual([second['bookings'][0][k] for k in blocks], [-2, 2, 3])
        self.assertEqual(first['availability'][670:], 'HH')
        self.assertEqual(second['availability'][:4], 'HHHO')

    def test_calendar_of_a_week_without_availability(self):
        self.login(self.cafe_user)
        body = self.client.get(self.detail_url(self.raj, 'calendar'), {'week': self.monday.isoformat()}).json()
        self.assertEqual((body['id'], body['availability'], body['bookings']), (None, 'U' * 672, []))
        url = self.detail_url(self.mei, 'calendar')
        self.assertEqual(self.client.get(url).status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.client.get(url, {'week': 'monday'}).status_code, status.HTTP_400_BAD_REQUEST)

    # --- Adding slots ---------------------------------------------------------------

    def test_add_slots_for_the_next_two_weeks(self):
        self.login(self.cafe_user)
        start = self.monday + timedelta(weeks=1)
        response = self.client.post(self.detail_url(self.raj, 'slots'), {
            'date_from': start.isoformat(), 'date_to': (start + timedelta(days=13)).isoformat(),
            'weekdays': [0, 1, 2, 3, 4], 'time_from': '09:00', 'time_to': '17:00',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.content)
        body = response.json()
        self.assertEqual((body['changed'], body['skipped']), (320, 0))
        self.assertEqual([w['week'] for w in body['weeks']], [start.isoformat(), (start + timedelta(weeks=1)).isoformat()])
        self.assertEqual(body['weeks'][0]['availability'], open_hours(*[(d, '09:00', '17:00') for d in range(5)]))
        self.assertEqual(WeeklyAvailability.objects.filter(service_provider=self.raj).count(), 2)

    def test_close_slots_and_until_midnight(self):
        book(self.portrait, self.mei, at(self.monday, '10:00'))
        self.login(self.cafe_user)
        response = self.client.post(self.detail_url(self.mei, 'slots'), {
            'date_from': self.monday.isoformat(), 'date_to': self.monday.isoformat(), 'weekdays': [0],
            'time_from': '00:00', 'time_to': '24:00', 'available': False,
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.content)
        self.assertEqual((response.json()['changed'], response.json()['skipped']), (7, 5))  # the booking's 5 blocks stay
        self.week.refresh_from_db()
        self.assertEqual(self.week.availability[36:50], 'UUUU' + 'HHHHH' + 'UUUUU')

    def test_add_slots_validation(self):
        self.login(self.cafe_user)
        valid = {'date_from': self.monday.isoformat(), 'date_to': self.monday.isoformat(), 'weekdays': [0], 'time_from': '09:00', 'time_to': '10:00'}
        cases = {
            'date_to before date_from': ({'date_to': (self.monday - timedelta(days=1)).isoformat()}, 'date_to'),
            'over 26 weeks': ({'date_to': (self.monday + timedelta(weeks=26)).isoformat()}, 'date_to'),
            'no weekdays': ({'weekdays': []}, 'weekdays'),
            'bad weekday': ({'weekdays': [7]}, 'weekdays'),
            'off the grid': ({'time_from': '09:10'}, 'time_from'),
            'to off the grid': ({'time_to': '10:05'}, 'time_to'),
            'to before from': ({'time_to': '08:00'}, 'time_to'),
            'to not a time': ({'time_to': 'noon'}, 'time_to'),
        }
        for label, (changes, field) in cases.items():
            with self.subTest(label):
                response = self.client.post(self.detail_url(self.mei, 'slots'), {**valid, **changes}, format='json')
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn(field, response.json())
        self.assertEqual(self.client.post(self.detail_url(self.mei, 'slots'), valid, format='json').status_code, 200)

    # --- Copying a week -------------------------------------------------------------

    def test_copy_week(self):
        self.login(self.cafe_user)
        response = self.client.post(self.detail_url(self.mei, 'copy-week'), {'source_week': self.monday.isoformat(), 'weeks': 3}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.content)
        body = response.json()
        self.assertEqual([w['week'] for w in body['weeks']],
                         [(self.monday + timedelta(weeks=n)).isoformat() for n in (1, 2, 3)])
        self.assertTrue(all(w['availability'] == self.week.availability for w in body['weeks']))
        # To a chosen week instead of the next one.
        target = self.monday + timedelta(weeks=8)
        response = self.client.post(self.detail_url(self.mei, 'copy-week'), {'source_week': self.monday.isoformat(), 'target_week': target.isoformat()}, format='json')
        self.assertEqual([w['week'] for w in response.json()['weeks']], [target.isoformat()])

    def test_copy_week_validation(self):
        self.login(self.cafe_user)
        url = self.detail_url(self.mei, 'copy-week')
        cases = {
            'not a Monday': ({'source_week': (self.monday + timedelta(days=1)).isoformat()}, 'source_week'),
            'target not a Monday': ({'source_week': self.monday.isoformat(), 'target_week': (self.monday + timedelta(days=8)).isoformat()}, 'target_week'),
            'same week': ({'source_week': self.monday.isoformat(), 'target_week': self.monday.isoformat()}, 'target_week'),
            'too many weeks': ({'source_week': self.monday.isoformat(), 'weeks': 27}, 'weeks'),
            'missing source': ({}, 'source_week'),
        }
        for label, (body, field) in cases.items():
            with self.subTest(label):
                response = self.client.post(url, body, format='json')
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn(field, response.json())


class WeeklyAvailabilityAPITests(ScheduleAPITestCase):
    list_url = reverse('product_app:weekly-availability-list')

    @staticmethod
    def detail_url(week):
        return reverse('product_app:weekly-availability-detail', args=[week.pk])

    def test_requires_login(self):
        self.assertEqual(self.client.get(self.list_url).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_lists_own_providers_weeks_with_filters(self):
        open_week(self.mei, self.monday + timedelta(weeks=1))
        open_week(self.raj, self.monday)
        open_week(self.florist_provider, self.monday)
        self.login(self.cafe_user)
        body = self.client.get(self.list_url).json()
        self.assertEqual(body['count'], 3)
        self.assertEqual(set(body['results'][0]), {'id', 'service_provider', 'week', 'availability'})
        self.assertEqual(self.client.get(self.list_url, {'service_provider': self.raj.pk}).json()['count'], 1)
        response = self.client.get(self.list_url, {'week_after': (self.monday + timedelta(days=1)).isoformat()})
        self.assertEqual([w['week'] for w in response.json()['results']], [(self.monday + timedelta(weeks=1)).isoformat()])

    def test_create_with_open_and_closed_blocks_only(self):
        self.login(self.cafe_user)
        nxt = (self.monday + timedelta(weeks=1)).isoformat()
        response = self.client.post(self.list_url, {'service_provider': self.mei.pk, 'week': nxt}, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.content)
        self.assertEqual(response.json()['availability'], 'U' * 672)
        for letters in ('H' * 672, 'U' * 671 + 'X'):
            with self.subTest(letters=letters[-1]):
                response = self.client.post(self.list_url, {'service_provider': self.raj.pk, 'week': nxt, 'availability': letters}, format='json')
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn('H and X come from bookings', response.json()['availability'][0])

    def test_create_validation(self):
        self.login(self.cafe_user)
        cases = {
            'not a Monday': ({'service_provider': self.raj.pk, 'week': (self.monday + timedelta(days=2)).isoformat()}, 'week'),
            'twice': ({'service_provider': self.mei.pk, 'week': self.monday.isoformat()}, 'non_field_errors'),
            'bad letters': ({'service_provider': self.raj.pk, 'week': self.monday.isoformat(), 'availability': 'O' * 10}, 'availability'),
            'unknown provider': ({'service_provider': 99999, 'week': self.monday.isoformat()}, 'service_provider'),
        }
        for label, (body, field) in cases.items():
            with self.subTest(label):
                response = self.client.post(self.list_url, body, format='json')
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn(field, response.json())
        response = self.client.post(self.list_url, {'service_provider': self.florist_provider.pk, 'week': self.monday.isoformat()}, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_open_and_close_blocks(self):
        self.login(self.cafe_user)
        letters = open_hours((0, '09:00', '12:00'), (2, '13:00', '15:00'))
        response = self.client.patch(self.detail_url(self.week), {'availability': letters}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.content)
        self.week.refresh_from_db()
        self.assertEqual(self.week.availability, letters)

    def test_booked_blocks_cant_change(self):
        book(self.portrait, self.mei, at(self.monday, '09:00'))  # 09:00–10:15 H
        self.week.refresh_from_db()
        self.login(self.cafe_user)
        cases = {
            'freeing a booked block': self.week.availability.replace('H', 'O', 1),
            'closing a booked block': self.week.availability.replace('H', 'U', 1),
            'booked by hand': self.week.availability.replace('O', 'X', 1),
        }
        for label, letters in cases.items():
            with self.subTest(label):
                response = self.client.patch(self.detail_url(self.week), {'availability': letters}, format='json')
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn('availability', response.json())
        before = self.week.availability
        self.week.refresh_from_db()
        self.assertEqual(self.week.availability, before)
        # The other blocks can still change.
        closed = before.replace('O', 'U')
        self.assertEqual(self.client.patch(self.detail_url(self.week), {'availability': closed}, format='json').status_code, 200)

    def test_an_edit_made_from_stale_letters_cant_overwrite_a_new_booking(self):
        # The owner loaded the week, then a customer booked, then the owner saves the old letters.
        stale = self.week.availability
        book(self.portrait, self.mei, at(self.monday, '09:00'))
        self.login(self.cafe_user)
        response = self.client.put(self.detail_url(self.week), {
            'service_provider': self.mei.pk, 'week': self.monday.isoformat(), 'availability': stale,
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("booked blocks (H / X) can't be changed", response.json()['availability'][0])

    def test_provider_and_week_cant_change(self):
        self.login(self.cafe_user)
        for body, field in (({'service_provider': self.raj.pk}, 'service_provider'), ({'week': (self.monday + timedelta(weeks=1)).isoformat()}, 'week')):
            with self.subTest(field):
                response = self.client.patch(self.detail_url(self.week), body, format='json')
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn(field, response.json())

    def test_delete_only_without_bookings(self):
        self.login(self.cafe_user)
        book(self.portrait, self.mei, at(self.monday, '09:00'))
        response = self.client.delete(self.detail_url(self.week))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('has bookings', response.json()['availability'][0])
        ScheduleItem.objects.all().delete()  # the letters are freed (O), so now it can go
        self.assertEqual(self.client.delete(self.detail_url(self.week)).status_code, status.HTTP_204_NO_CONTENT)

    def test_other_business(self):
        theirs = open_week(self.florist_provider, self.monday)
        self.login(self.cafe_user)
        self.assertEqual(self.client.get(self.detail_url(theirs)).status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.patch(self.detail_url(theirs), {'availability': 'O' * 672}, format='json').status_code, 403)
        self.assertEqual(self.client.delete(self.detail_url(theirs)).status_code, status.HTTP_403_FORBIDDEN)


class ServiceAPITests(ScheduleAPITestCase):
    list_url = reverse('product_app:service-list')

    @staticmethod
    def detail_url(service):
        return reverse('product_app:service-detail', args=[service.pk])

    def valid(self, **overrides):
        return {
            'name': 'Family', 'price': '250.00', 'duration_minutes': 90, 'buffer_minutes': 30,
            'service_providers': [self.mei.pk, self.raj.pk], **overrides,
        }

    def test_requires_login(self):
        self.assertEqual(self.client.get(self.list_url).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_lists_own_business_only(self):
        self.login(self.cafe_user)
        self.assertEqual(
            self.client.get(self.list_url).json()['results'],
            [{
                'id': self.portrait.pk, 'business': self.cafe.pk, 'name': 'Portrait', 'description': '', 'information': '',
                'price': '180.00', 'duration_minutes': 60, 'buffer_minutes': 15, 'start_interval_minutes': 15,
                'service_providers': [self.mei.pk], 'is_active': True,
            }],
        )

    def test_create_and_change_providers(self):
        self.login(self.cafe_user)
        response = self.client.post(self.list_url, self.valid(), format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.content)
        service = Service.objects.get(pk=response.json()['id'])
        self.assertEqual(set(service.service_providers.all()), {self.mei, self.raj})
        self.client.patch(self.detail_url(service), {'service_providers': [self.raj.pk]}, format='json')
        self.assertEqual(list(service.service_providers.all()), [self.raj])
        self.client.patch(self.detail_url(service), {'price': '200.00'}, format='json')
        self.assertEqual(list(service.service_providers.all()), [self.raj])  # untouched

    def test_another_business_provider_is_rejected(self):
        self.login(self.cafe_user)
        response = self.client.post(self.list_url, self.valid(service_providers=[self.mei.pk, self.florist_provider.pk]), format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Not your business's service provider", response.json()['service_providers'][0])
        self.assertEqual(self.client.post(self.list_url, self.valid(service_providers=[99999]), format='json').status_code, 400)

    def test_invalid_input(self):
        self.login(self.cafe_user)
        cases = {
            'duration not a whole block': ({'duration_minutes': 50}, 'duration_minutes'),
            'duration zero': ({'duration_minutes': 0}, 'duration_minutes'),
            'buffer not a whole block': ({'buffer_minutes': 10}, 'buffer_minutes'),
            'negative price': ({'price': '-1.00'}, 'price'),
            'duplicate name': ({'name': 'Portrait'}, 'non_field_errors'),
        }
        for label, (overrides, field) in cases.items():
            with self.subTest(label):
                response = self.client.post(self.list_url, self.valid(**overrides), format='json')
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn(field, response.json())

    def test_other_business(self):
        self.login(self.cafe_user)
        self.assertEqual(self.client.get(self.detail_url(self.florist_service)).status_code, status.HTTP_403_FORBIDDEN)
        response = self.client.post(self.list_url, self.valid(business=self.florist.pk, service_providers=[]), format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_slots(self):
        book(self.portrait, self.mei, at(self.monday, '11:00'))  # 11:00–12:00, blocked until 12:15
        self.login(self.cafe_user)
        url = reverse('product_app:service-slots', args=[self.portrait.pk])
        body = self.client.get(url, {'date_from': self.monday.isoformat()}).json()
        self.assertEqual(
            [datetime.fromisoformat(slot) for slot in body['slots']],
            [at(self.monday, hhmm) for hhmm in ('09:00', '09:15', '09:30', '09:45')],
        )
        self.assertEqual(self.client.get(url, {'date_from': (self.monday + timedelta(days=1)).isoformat()}).json()['slots'], [])
        self.assertEqual(self.client.get(url).status_code, status.HTTP_400_BAD_REQUEST)
        response = self.client.get(url, {'date_from': self.monday.isoformat(), 'date_to': (self.monday + timedelta(days=100)).isoformat()})
        self.assertEqual(response.json()['date_to'], (self.monday + timedelta(days=30)).isoformat())

    def test_start_interval(self):
        self.login(self.cafe_user)
        response = self.client.post(self.list_url, self.valid(start_interval_minutes=30), format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.content)
        self.assertEqual(response.json()['start_interval_minutes'], 30)
        self.assertEqual(self.client.post(self.list_url, self.valid(name='Default'), format='json').json()['start_interval_minutes'], 15)
        for minutes in (0, 20, 1455, 'hourly'):
            with self.subTest(minutes=minutes):
                response = self.client.post(self.list_url, self.valid(name=f'Bad {minutes}', start_interval_minutes=minutes), format='json')
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn('start_interval_minutes', response.json())
        response = self.client.patch(self.detail_url(self.portrait), {'start_interval_minutes': 60}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.content)
        self.portrait.refresh_from_db()
        self.assertEqual(self.portrait.start_interval_minutes, 60)

    def test_slots_follow_the_start_interval(self):
        self.portrait.start_interval_minutes = 60
        self.portrait.save()
        self.login(self.cafe_user)
        url = reverse('product_app:service-slots', args=[self.portrait.pk])
        body = self.client.get(url, {'date_from': self.monday.isoformat()}).json()
        self.assertEqual(
            [datetime.fromisoformat(slot) for slot in body['slots']],
            [at(self.monday, hhmm) for hhmm in ('09:00', '10:00', '11:00')],  # open 09:00–12:00, 1-hour Portrait
        )
