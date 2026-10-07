import base64
from decimal import Decimal

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from auth_app.models import BusinessUser
from configuration_app.models import BusinessConfiguration

from .models import (
    FAQ,
    FAQ_ANSWER_MAX_LENGTH,
    PRODUCT_DESCRIPTION_MAX_LENGTH,
    PRODUCT_INFORMATION_MAX_LENGTH,
    PRODUCT_NAME_MAX_LENGTH,
    QUANTITY_MAX,
    Product,
)
from .serializers import ProductSerializer


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

        cls.cafe_product = Product.objects.create(
            business=cls.cafe, name='Latte', price=Decimal('4.50'), quantity_available=10, quantity_sold=3
        )
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
            self.list_url, {'name': 'Mocha', 'price': '5.20', 'quantity_available': 5}, format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        product = Product.objects.get(pk=response.data['id'])
        self.assertEqual(product.business, self.cafe)
        self.assertEqual(product.quantity_sold, 0)
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
        self.assertEqual(response.data['quantity_sold'], 3)

    def test_update_own_product(self):
        self.login(self.cafe_user)
        response = self.client.patch(
            self.detail_url(self.cafe_product),
            {'name': 'Iced Latte', 'price': '5.00', 'quantity_on_hold': 2, 'is_active': False},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.cafe_product.refresh_from_db()
        self.assertEqual(self.cafe_product.name, 'Iced Latte')
        self.assertEqual(self.cafe_product.price, Decimal('5.00'))
        self.assertEqual(self.cafe_product.quantity_on_hold, 2)
        self.assertFalse(self.cafe_product.is_active)

    def test_full_update_own_product(self):
        self.login(self.cafe_user)
        response = self.client.put(
            self.detail_url(self.cafe_product),
            {'name': 'Flat White', 'price': '4.80', 'quantity_available': 8},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.cafe_product.refresh_from_db()
        self.assertEqual(self.cafe_product.name, 'Flat White')
        self.assertEqual(self.cafe_product.business, self.cafe)

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

    # --- quantity_sold is read-only -------------------------------------------------

    def test_quantity_sold_cannot_be_edited(self):
        self.login(self.cafe_user)
        response = self.client.patch(self.detail_url(self.cafe_product), {'quantity_sold': 99}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('quantity_sold', response.data)
        self.cafe_product.refresh_from_db()
        self.assertEqual(self.cafe_product.quantity_sold, 3)

    def test_quantity_sold_cannot_be_set_on_create(self):
        self.login(self.cafe_user)
        response = self.client.post(
            self.list_url, {'name': 'Mocha', 'price': '5.20', 'quantity_sold': 10}, format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('quantity_sold', response.data)

    # --- Validation -----------------------------------------------------------------

    def test_validation_errors(self):
        self.login(self.cafe_user)
        cases = {
            'negative quantity_available': ({'quantity_available': -1}, 'quantity_available'),
            'negative quantity_on_hold': ({'quantity_on_hold': -5}, 'quantity_on_hold'),
            'quantity too large': ({'quantity_available': QUANTITY_MAX + 1}, 'quantity_available'),
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
