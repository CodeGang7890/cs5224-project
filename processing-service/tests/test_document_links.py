"""Short links to the invoice / receipt PDFs (app/document_links.py)."""

import unittest
from unittest import mock

from app import document_links

REFERENCE = '0123456789abcdef0123456789abcdef'


class ShortLinkTests(unittest.TestCase):
    def test_the_link_configuration_service_reads(self):
        # The same token as configuration-service's checkout_app/tests/test_api.py: both services must agree.
        with mock.patch.multiple(document_links.config, DOCUMENTS_PUBLIC_URL='https://ansera.example', INTERNAL_API_KEY='test-key'):
            link = document_links.short_link('invoice', REFERENCE)
            self.assertEqual(link, f'https://ansera.example/d/i{REFERENCE}pRAYtf9KdFjdwQSA')
            self.assertTrue(document_links.short_link('receipt', REFERENCE).startswith(f'https://ansera.example/d/r{REFERENCE}'))
        self.assertLessEqual(len(link), 80)  # mock_whatsapp shows links up to 80 characters in full

    def test_no_public_url_or_key_means_no_short_link(self):
        for public_url, key in (('', 'test-key'), ('https://ansera.example', '')):
            with mock.patch.multiple(document_links.config, DOCUMENTS_PUBLIC_URL=public_url, INTERNAL_API_KEY=key):
                self.assertIsNone(document_links.short_link('invoice', REFERENCE))
