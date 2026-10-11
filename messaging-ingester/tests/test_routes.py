import unittest

from fastapi.testclient import TestClient

from app import create_app


class MainRouteTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(create_app())

    def test_health_check(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'message': 'messaging-ingester is running'})

    def test_unknown_route_uses_the_error_shape(self):
        response = self.client.get('/nope')
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {'code': 404, 'status': 'Not Found', 'message': 'Not Found'})


class APIDocsTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(create_app())

    def test_swagger_ui(self):
        response = self.client.get('/docs')
        self.assertEqual(response.status_code, 200)
        self.assertIn('swagger-ui', response.text)

    def test_openapi_lists_the_webhook(self):
        spec = self.client.get('/openapi.json').json()
        self.assertEqual(set(spec['paths']), {'/', '/webhook/{business_id}'})
        self.assertEqual(set(spec['paths']['/webhook/{business_id}']), {'get', 'post'})
        query = {p['name'] for p in spec['paths']['/webhook/{business_id}']['get']['parameters'] if p['in'] == 'query'}
        self.assertEqual(query, {'hub.mode', 'hub.verify_token', 'hub.challenge'})
