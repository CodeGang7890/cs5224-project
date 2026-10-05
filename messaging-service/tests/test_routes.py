import unittest

from fastapi.testclient import TestClient

from app import create_app


class IndexRouteTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(create_app())

    def test_returns_hello_world_json(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['content-type'], 'application/json')
        self.assertEqual(response.json(), {'message': 'Hello, World!'})

    def test_unknown_route_returns_404(self):
        response = self.client.get('/does-not-exist')
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {'code': 404, 'status': 'Not Found', 'message': 'Not Found'})


if __name__ == '__main__':
    unittest.main()
