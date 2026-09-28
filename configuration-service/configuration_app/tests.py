from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from .models import BUSINESS_NAME_MAX_LENGTH, DESCRIPTION_MAX_LENGTH, BusinessConfiguration


class RandomNumberViewTests(TestCase):
    url = reverse('configuration_app:random-number')

    def test_returns_number_between_1_and_10(self):
        for _ in range(50):
            response = self.client.get(self.url)
            self.assertEqual(response.status_code, 200)
            self.assertIn(response.json()['value'], range(1, 11))

    def test_allows_frontend_dev_origin(self):
        response = self.client.get(self.url, headers={'Origin': 'http://localhost:5173'})
        self.assertEqual(response.headers.get('Access-Control-Allow-Origin'), 'http://localhost:5173')

    def test_preflight_from_frontend_dev_origin(self):
        response = self.client.options(
            self.url,
            headers={
                'Origin': 'http://localhost:5173',
                'Access-Control-Request-Method': 'GET',
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get('Access-Control-Allow-Origin'), 'http://localhost:5173')

    def test_rejects_unknown_origin(self):
        response = self.client.get(self.url, headers={'Origin': 'http://evil.example'})
        self.assertNotIn('Access-Control-Allow-Origin', response.headers)


class BusinessConfigurationModelTests(TestCase):
    def test_valid_business(self):
        BusinessConfiguration(business_name='Shop', location='Singapore').full_clean()

    def test_length_limits(self):
        cases = {
            'business_name': 'x' * (BUSINESS_NAME_MAX_LENGTH + 1),
            'description': 'x' * (DESCRIPTION_MAX_LENGTH + 1),
        }
        for field, value in cases.items():
            with self.subTest(field=field):
                business = BusinessConfiguration(business_name='Shop', location='Singapore')
                setattr(business, field, value)
                with self.assertRaises(ValidationError) as ctx:
                    business.full_clean()
                self.assertIn(field, ctx.exception.message_dict)

    def test_name_and_location_required(self):
        with self.assertRaises(ValidationError) as ctx:
            BusinessConfiguration(business_name='', location='').full_clean()
        self.assertEqual(set(ctx.exception.message_dict), {'business_name', 'location'})
