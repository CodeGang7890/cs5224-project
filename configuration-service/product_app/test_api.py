import base64
from datetime import datetime, timedelta
from decimal import Decimal

from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from auth_app.models import BusinessUser
from checkout_app.models import OrderItem, OrderStatus
from checkout_app.tests.test_schedule import at, book, future_monday
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


# --- Weekly availabilities and services ---------------------------------------------------------

@override_settings(SCHEDULE_TIME_ZONE='Asia/Singapore')
class ScheduleAPITestCase(BusinessAPITestCase):
    """BusinessAPITestCase, plus a photographer's weekly availability and a service for each business."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.mei = WeeklyAvailability.objects.create(business=cls.cafe, name='Mei', availability=open_hours((0, '09:00', '12:00')))
        cls.raj = WeeklyAvailability.objects.create(business=cls.cafe, name='Raj')
        cls.florist_calendar = WeeklyAvailability.objects.create(business=cls.florist, name='Florist calendar')
        cls.portrait = Service.objects.create(business=cls.cafe, name='Portrait', price='180.00', duration_minutes=60, buffer_minutes=15)
        cls.portrait.weekly_availability.set([cls.mei])
        cls.florist_service = Service.objects.create(business=cls.florist, name='Workshop', price='50.00', duration_minutes=120)


class WeeklyAvailabilityAPITests(ScheduleAPITestCase):
    list_url = reverse('product_app:weekly-availability-list')

    @staticmethod
    def detail_url(availability):
        return reverse('product_app:weekly-availability-detail', args=[availability.pk])

    def test_requires_login(self):
        self.assertEqual(self.client.get(self.list_url).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_lists_own_business_only(self):
        self.login(self.cafe_user)
        body = self.client.get(self.list_url).json()
        self.assertEqual([a['name'] for a in body['results']], ['Mei', 'Raj'])
        self.assertEqual(set(body['results'][0]), {'id', 'business', 'name', 'availability', 'services'})
        self.assertEqual(body['results'][0]['services'], [self.portrait.pk])
        self.assertEqual(len(body['results'][0]['availability']), 672)

    def test_create_defaults_to_not_available(self):
        self.login(self.cafe_user)
        response = self.client.post(self.list_url, {'name': 'Lina'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.content)
        self.assertEqual(response.json()['availability'], 'X' * 672)
        self.assertEqual(response.json()['business'], self.cafe.pk)
        self.assertEqual(response.json()['services'], [])

    def test_update_the_calendar(self):
        self.login(self.cafe_user)
        week = open_hours((1, '10:00', '18:00'), (2, '13:00', '14:00'), letter='O')
        response = self.client.patch(self.detail_url(self.raj), {'availability': week}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.raj.refresh_from_db()
        self.assertEqual(self.raj.availability, week)

    def test_invalid_input(self):
        self.login(self.cafe_user)
        cases = {
            'short': ({'name': 'A', 'availability': 'O' * 10}, 'availability'),
            'long': ({'name': 'A', 'availability': 'O' * 673}, 'availability'),
            'bad letter': ({'name': 'A', 'availability': 'O' * 671 + 'Z'}, 'availability'),
            'no name': ({'availability': 'O' * 672}, 'name'),
            'duplicate name': ({'name': 'Mei'}, 'non_field_errors'),
        }
        for label, (body, field) in cases.items():
            with self.subTest(label):
                response = self.client.post(self.list_url, body, format='json')
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn(field, response.json())

    def test_other_business(self):
        self.login(self.cafe_user)
        self.assertEqual(self.client.get(self.detail_url(self.florist_calendar)).status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(
            self.client.patch(self.detail_url(self.florist_calendar), {'name': 'Mine'}, format='json').status_code,
            status.HTTP_403_FORBIDDEN,
        )
        response = self.client.post(self.list_url, {'name': 'X', 'business': self.florist.pk}, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.login(self.no_business_user)
        self.assertEqual(self.client.post(self.list_url, {'name': 'X'}, format='json').status_code, status.HTTP_403_FORBIDDEN)

    def test_delete_keeps_the_services(self):
        self.login(self.cafe_user)
        self.assertEqual(self.client.delete(self.detail_url(self.mei)).status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(list(self.portrait.weekly_availability.all()), [])

    def test_calendar(self):
        monday = future_monday()
        book(self.portrait, self.mei, at(monday, '09:00'))  # 09:00–10:15 with the buffer, pending
        book(self.portrait, self.mei, at(monday, '11:00'), status=OrderStatus.ORDER_COMPLETED)
        self.login(self.cafe_user)
        url = reverse('product_app:weekly-availability-calendar', args=[self.mei.pk])
        response = self.client.get(url, {'week': (monday + timedelta(days=4)).isoformat()})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.content)
        body = response.json()
        self.assertEqual(body['week_start'], monday.isoformat())
        self.assertEqual(body['availability'][36:48], 'HHHHHOOOXXXX')
        self.assertEqual(
            [(b['service'], b['order_status']) for b in body['bookings']],
            [('Portrait', 'pending_payment'), ('Portrait', 'order_completed')],
        )
        self.assertEqual(set(body['bookings'][0]), {'id', 'service', 'start_time', 'end_time', 'blocked_until', 'order_status'})
        self.assertEqual(self.client.get(url).status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.client.get(url, {'week': 'monday'}).status_code, status.HTTP_400_BAD_REQUEST)
        other_url = reverse('product_app:weekly-availability-calendar', args=[self.florist_calendar.pk])
        self.assertEqual(self.client.get(other_url, {'week': monday.isoformat()}).status_code, status.HTTP_403_FORBIDDEN)


class ServiceAPITests(ScheduleAPITestCase):
    list_url = reverse('product_app:service-list')

    @staticmethod
    def detail_url(service):
        return reverse('product_app:service-detail', args=[service.pk])

    def valid(self, **overrides):
        return {
            'name': 'Family', 'price': '250.00', 'duration_minutes': 90, 'buffer_minutes': 30,
            'weekly_availability': [self.mei.pk, self.raj.pk], **overrides,
        }

    def test_requires_login(self):
        self.assertEqual(self.client.get(self.list_url).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_lists_own_business_only(self):
        self.login(self.cafe_user)
        body = self.client.get(self.list_url).json()
        self.assertEqual(
            body['results'],
            [{
                'id': self.portrait.pk, 'business': self.cafe.pk, 'name': 'Portrait', 'description': '', 'information': '',
                'price': '180.00', 'duration_minutes': 60, 'buffer_minutes': 15,
                'weekly_availability': [self.mei.pk], 'is_active': True,
            }],
        )

    def test_create_with_availabilities(self):
        self.login(self.cafe_user)
        response = self.client.post(self.list_url, self.valid(), format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.content)
        service = Service.objects.get(pk=response.json()['id'])
        self.assertEqual(set(service.weekly_availability.all()), {self.mei, self.raj})
        self.assertEqual(service.business, self.cafe)
        # Without availabilities: valid, but not bookable yet.
        response = self.client.post(self.list_url, self.valid(name='Later', weekly_availability=[]), format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_change_availabilities(self):
        self.login(self.cafe_user)
        response = self.client.patch(self.detail_url(self.portrait), {'weekly_availability': [self.raj.pk]}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(list(self.portrait.weekly_availability.all()), [self.raj])
        response = self.client.patch(self.detail_url(self.portrait), {'price': '200.00'}, format='json')
        self.assertEqual(list(self.portrait.weekly_availability.all()), [self.raj])  # untouched

    def test_another_business_availability_is_rejected(self):
        self.login(self.cafe_user)
        response = self.client.post(self.list_url, self.valid(weekly_availability=[self.mei.pk, self.florist_calendar.pk]), format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Not your business's weekly availability", response.json()['weekly_availability'][0])
        response = self.client.patch(
            self.detail_url(self.portrait), {'weekly_availability': [self.florist_calendar.pk]}, format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(list(self.portrait.weekly_availability.all()), [self.mei])
        response = self.client.post(self.list_url, self.valid(weekly_availability=[99999]), format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invalid_input(self):
        self.login(self.cafe_user)
        cases = {
            'duration not a whole block': ({'duration_minutes': 50}, 'duration_minutes'),
            'duration zero': ({'duration_minutes': 0}, 'duration_minutes'),
            'duration too long': ({'duration_minutes': 1455}, 'duration_minutes'),
            'buffer not a whole block': ({'buffer_minutes': 10}, 'buffer_minutes'),
            'negative price': ({'price': '-1.00'}, 'price'),
            'blank name': ({'name': ''}, 'name'),
            'duplicate name': ({'name': 'Portrait'}, 'non_field_errors'),
            'description too long': ({'description': 'x' * 301}, 'description'),
        }
        for label, (overrides, field) in cases.items():
            with self.subTest(label):
                response = self.client.post(self.list_url, self.valid(**overrides), format='json')
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn(field, response.json())

    def test_other_business(self):
        self.login(self.cafe_user)
        self.assertEqual(self.client.get(self.detail_url(self.florist_service)).status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.delete(self.detail_url(self.florist_service)).status_code, status.HTTP_403_FORBIDDEN)
        response = self.client.post(self.list_url, self.valid(business=self.florist.pk, weekly_availability=[]), format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(Service.objects.filter(pk=self.florist_service.pk).exists())

    def test_slots(self):
        monday = future_monday()
        book(self.portrait, self.mei, at(monday, '11:00'))  # 11:00–12:00, blocked until 12:15
        self.login(self.cafe_user)
        url = reverse('product_app:service-slots', args=[self.portrait.pk])
        response = self.client.get(url, {'date_from': monday.isoformat()})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.content)
        body = response.json()
        self.assertEqual((body['date_from'], body['date_to']), (monday.isoformat(), monday.isoformat()))
        # Mei is open 09:00–12:00; 60 minutes + a 15-minute buffer must end by the 11:00 booking.
        self.assertEqual(
            [datetime.fromisoformat(slot) for slot in body['slots']],
            [at(monday, hhmm) for hhmm in ('09:00', '09:15', '09:30', '09:45')],
        )
        response = self.client.get(url, {'date_from': (monday + timedelta(days=1)).isoformat()})
        self.assertEqual(response.json()['slots'], [])  # closed on Tuesday

    def test_slots_query(self):
        self.login(self.cafe_user)
        url = reverse('product_app:service-slots', args=[self.portrait.pk])
        monday = future_monday()
        self.assertEqual(self.client.get(url).status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.client.get(url, {'date_from': 'soon'}).status_code, status.HTTP_400_BAD_REQUEST)
        response = self.client.get(url, {'date_from': monday.isoformat(), 'date_to': (monday - timedelta(days=1)).isoformat()})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('date_to', response.json())
        response = self.client.get(url, {'date_from': monday.isoformat(), 'date_to': (monday + timedelta(days=100)).isoformat()})
        self.assertEqual(response.json()['date_to'], (monday + timedelta(days=30)).isoformat())  # 31 days at most
        other_url = reverse('product_app:service-slots', args=[self.florist_service.pk])
        self.assertEqual(self.client.get(other_url, {'date_from': monday.isoformat()}).status_code, status.HTTP_403_FORBIDDEN)
