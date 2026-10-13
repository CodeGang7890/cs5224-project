"""Invoice storage (app/storage.py), with a fake Cloud Storage client."""

import unittest
from unittest import mock

from app import storage


class StorageTests(unittest.TestCase):
    def test_no_bucket_means_no_upload_and_no_link(self):
        with mock.patch.object(storage.config, 'GCS_BUCKET', ''):
            self.assertIsNone(storage.upload_invoice(b'%PDF', 'invoices/x.pdf', client=mock.Mock()))
            self.assertIsNone(storage.invoice_link('invoices/x.pdf', client=mock.Mock()))

    def test_upload_puts_the_pdf_in_the_bucket(self):
        client = mock.Mock()
        with mock.patch.object(storage.config, 'GCS_BUCKET', 'my-bucket'):
            uri = storage.upload_invoice(b'%PDF', 'invoices/x.pdf', client=client)
        client.bucket.assert_called_once_with('my-bucket')
        client.bucket.return_value.blob.assert_called_once_with('invoices/x.pdf')
        client.bucket.return_value.blob.return_value.upload_from_string.assert_called_once_with(
            b'%PDF', content_type='application/pdf'
        )
        self.assertEqual(uri, 'gs://my-bucket/invoices/x.pdf')

    def test_a_user_login_has_no_service_account_so_no_link(self):
        client = mock.Mock()
        client._credentials = object()  # a user's credentials: no service_account_email
        with mock.patch.object(storage.config, 'GCS_BUCKET', 'my-bucket'):
            self.assertIsNone(storage.invoice_link('x.pdf', client=client))

    def test_a_link_that_cant_be_signed_is_none_not_an_error(self):
        client = mock.Mock()
        client._credentials.refresh.side_effect = RuntimeError('no service account')
        with mock.patch.object(storage.config, 'GCS_BUCKET', 'my-bucket'):
            self.assertIsNone(storage.invoice_link('x.pdf', client=client))
