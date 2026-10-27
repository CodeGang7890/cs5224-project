from unittest import TestCase
from unittest.mock import patch

from app.db import database_url


class DatabaseUrlTests(TestCase):
    @patch('app.db.config.DATABASE_URL', '')
    @patch('app.db.config.POSTGRES_HOST', '/cloudsql/project:us-central1:main-postgres')
    def test_cloud_sql_uses_unix_socket_host(self):
        url = database_url()
        self.assertIsNone(url.host)
        self.assertIsNone(url.port)
        self.assertEqual(url.query['host'], '/cloudsql/project:us-central1:main-postgres')

    @patch('app.db.config.DATABASE_URL', '')
    @patch('app.db.config.POSTGRES_HOST', 'postgres')
    @patch('app.db.config.POSTGRES_PORT', 5432)
    def test_local_postgres_uses_tcp_host(self):
        url = database_url()
        self.assertEqual(url.host, 'postgres')
        self.assertEqual(url.port, 5432)
        self.assertEqual(url.query, {})
