import unittest

from fastapi.testclient import TestClient

from app import create_app


class MainRouteTests(unittest.TestCase):
    def test_hello_world(self):
        response = TestClient(create_app()).get('/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'message': 'Hello, world! processing-service is running'})


if __name__ == '__main__':
    unittest.main()
