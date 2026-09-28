from django.test import TestCase
from django.urls import reverse


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
