import unittest

from app import create_app


class IndexRouteTests(unittest.TestCase):
    def setUp(self):
        self.client = create_app({'TESTING': True}).test_client()

    def test_returns_hello_world_json(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, 'application/json')
        self.assertEqual(response.get_json(), {'message': 'Hello, World!'})

    def test_unknown_route_returns_404(self):
        self.assertEqual(self.client.get('/does-not-exist').status_code, 404)


if __name__ == '__main__':
    unittest.main()
