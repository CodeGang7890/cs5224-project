import json
import unittest

import httpx

from app.parsing import AccountUpdate
from app.verification import (
    BusinessNotConnectedError,
    ConfigurationServiceClient,
    Verification,
    ConfigurationServiceUnavailableError,
)

BASE_URL = 'http://configuration-service:8000/api'
API_KEY = 'test-internal-key'


class ConfigurationServiceClientTests(unittest.TestCase):
    def client(self, handler):
        """A client whose HTTP calls go to `handler` (records each request in self.requests)."""
        self.requests = []

        def record(request):
            self.requests.append(request)
            return handler(request)

        return ConfigurationServiceClient(BASE_URL, API_KEY, timeout=1, transport=httpx.MockTransport(record))

    @staticmethod
    def reply(status=200, json_body=None, text=None):
        def handler(request):
            if text is not None:
                return httpx.Response(status, text=text)
            return httpx.Response(status, json=json_body if json_body is not None else {'valid': True, 'phone_number_id': '123'})
        return handler

    # --- verify_token ---------------------------------------------------------------------

    def test_verify_token_request(self):
        result = self.client(self.reply()).verify_token(7, 'tok')
        self.assertEqual(result, Verification(valid=True, phone_number_id='123'))
        request = self.requests[0]
        self.assertEqual(request.method, 'POST')
        self.assertEqual(str(request.url), f'{BASE_URL}/internal/whatsapp/7/verify-token/')
        self.assertEqual(request.headers['X-Internal-Api-Key'], API_KEY)
        self.assertEqual(json.loads(request.content), {'verify_token': 'tok'})

    def test_invalid_answer(self):
        result = self.client(self.reply(json_body={'valid': False, 'phone_number_id': None})).verify_token(7, 'x')
        self.assertEqual(result, Verification(valid=False, phone_number_id=None))

    def test_only_true_counts_as_valid(self):
        for value in ('true', 1, 'yes', None):
            with self.subTest(value=value):
                result = self.client(self.reply(json_body={'valid': value, 'phone_number_id': '1'})).verify_token(7, 'x')
                self.assertFalse(result.valid)

    # --- verify_signature -----------------------------------------------------------------

    def test_verify_signature_forwards_the_exact_body_and_header(self):
        raw = '{"note":"caf\\u00e9", "spaces":  1}'.encode() + b'\xff'
        result = self.client(self.reply()).verify_signature(7, raw, 'sha256=abc')
        self.assertTrue(result.valid)
        request = self.requests[0]
        self.assertEqual(str(request.url), f'{BASE_URL}/internal/whatsapp/7/verify-signature/')
        self.assertEqual(request.content, raw)
        self.assertEqual(request.headers['X-Hub-Signature-256'], 'sha256=abc')
        self.assertEqual(request.headers['Content-Type'], 'application/octet-stream')
        self.assertEqual(request.headers['X-Internal-Api-Key'], API_KEY)

    def test_missing_signature_is_not_sent(self):
        self.client(self.reply()).verify_signature(7, b'{}', None)
        self.assertNotIn('X-Hub-Signature-256', self.requests[0].headers)

    # --- Failures -------------------------------------------------------------------------

    def test_404_means_not_connected(self):
        with self.assertRaises(BusinessNotConnectedError):
            self.client(self.reply(404, json_body={'detail': 'x'})).verify_token(7, 'x')

    def test_other_statuses_mean_unavailable(self):
        for status in (400, 401, 403, 405, 500, 502, 503):
            with self.subTest(status=status):
                with self.assertRaises(ConfigurationServiceUnavailableError):
                    self.client(self.reply(status, json_body={'detail': 'x'})).verify_signature(7, b'{}', 's')

    def test_unexpected_replies_mean_unavailable(self):
        for handler in (self.reply(text='not json'), self.reply(json_body={'ok': True}), self.reply(json_body=[1])):
            with self.subTest():
                with self.assertRaises(ConfigurationServiceUnavailableError):
                    self.client(handler).verify_token(7, 'x')

    def test_network_errors_mean_unavailable(self):
        for error in (httpx.ConnectError('refused'), httpx.ReadTimeout('slow'), httpx.RemoteProtocolError('bad')):
            with self.subTest(error=type(error).__name__):
                def handler(request, error=error):
                    raise error
                with self.assertRaises(ConfigurationServiceUnavailableError):
                    self.client(handler).verify_token(7, 'x')


class AppWebhookClientTests(ConfigurationServiceClientTests):
    """Our Meta app's own webhook checks (Embedded Signup)."""

    def test_verify_app_token_request(self):
        result = self.client(self.reply(json_body={'valid': True, 'phone_number_id': None})).verify_app_token('tok')
        self.assertEqual(result, Verification(valid=True, phone_number_id=None))
        request = self.requests[0]
        self.assertEqual(str(request.url), f'{BASE_URL}/internal/whatsapp/app/verify-token/')
        self.assertEqual(json.loads(request.content), {'verify_token': 'tok'})
        self.assertEqual(request.headers['X-Internal-Api-Key'], API_KEY)

    def test_verify_app_signature_forwards_the_exact_body_and_header(self):
        raw = b'{"entry": [] }'
        self.client(self.reply()).verify_app_signature(raw, 'sha256=abc')
        request = self.requests[0]
        self.assertEqual(str(request.url), f'{BASE_URL}/internal/whatsapp/app/verify-signature/')
        self.assertEqual(request.content, raw)
        self.assertEqual(request.headers['X-Hub-Signature-256'], 'sha256=abc')

    def test_404_means_not_configured(self):
        with self.assertRaises(BusinessNotConnectedError):
            self.client(self.reply(404, {'detail': 'not configured'})).verify_app_token('tok')

    def test_report_account_updates(self):
        updates = [AccountUpdate('111', 'DISABLED_UPDATE', ban_state='DISABLE')]
        self.assertEqual(self.client(self.reply(json_body={'changed': 1})).report_account_updates(updates), 1)
        request = self.requests[0]
        self.assertEqual(str(request.url), f'{BASE_URL}/internal/whatsapp/app/account-updates/')
        self.assertEqual(
            json.loads(request.content),
            {'updates': [{'waba_id': '111', 'event': 'DISABLED_UPDATE', 'ban_state': 'DISABLE', 'partner_app_id': ''}]},
        )
        self.assertEqual(request.headers['X-Internal-Api-Key'], API_KEY)

    def test_report_account_updates_failures(self):
        for reply in (self.reply(500, {'detail': 'boom'}), self.reply(json_body={'changed': 'one'}),
                      self.reply(json_body=['changed'])):
            with self.subTest(), self.assertRaises(ConfigurationServiceUnavailableError):
                self.client(reply).report_account_updates([AccountUpdate('111', 'ACCOUNT_DELETED')])
