import json
import unittest

from fastapi.testclient import TestClient

from app import create_app
from app.webhook import get_publisher, get_verifier

from .helpers import (
    BUSINESS_ID,
    NOT_CONNECTED,
    PHONE_NUMBER_ID,
    UNAVAILABLE,
    VALID_SIGNATURE,
    VERIFY_TOKEN,
    FakePublisher,
    FakeVerifier,
    body,
    change,
    text_message,
    webhook,
)

URL = f'/webhook/{BUSINESS_ID}'


class WebhookTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.verifier = FakeVerifier()
        self.publisher = FakePublisher()
        self.app.dependency_overrides[get_verifier] = lambda: self.verifier
        self.app.dependency_overrides[get_publisher] = lambda: self.publisher
        self.client = TestClient(self.app)


class VerifySubscriptionTests(WebhookTestCase):
    """GET /webhook/<business_id>: Meta's handshake when the owner saves the Callback URL."""

    def handshake(self, mode='subscribe', token=VERIFY_TOKEN, challenge='1158201444', url=URL):
        params = {'hub.mode': mode, 'hub.verify_token': token, 'hub.challenge': challenge}
        return self.client.get(url, params={k: v for k, v in params.items() if v is not None})

    def test_echoes_the_challenge(self):
        with self.assertLogs('app.webhook', 'INFO'):
            response = self.handshake()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.text, '1158201444')
        self.assertTrue(response.headers['content-type'].startswith('text/plain'))
        self.assertEqual(self.verifier.calls, [('verify_token', BUSINESS_ID, VERIFY_TOKEN)])

    def test_wrong_token_is_403(self):
        with self.assertLogs('app.webhook', 'WARNING'):
            response = self.handshake(token='wrong')
        self.assertEqual(response.status_code, 403)
        self.assertNotIn('1158201444', response.text)

    def test_wrong_mode_is_403_without_asking(self):
        response = self.handshake(mode='unsubscribe')
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.verifier.calls, [])

    def test_not_connected_is_404(self):
        self.verifier.error = NOT_CONNECTED
        response = self.handshake()
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()['message'], 'This business has not connected WhatsApp.')

    def test_configuration_service_down_is_503(self):
        self.verifier.error = UNAVAILABLE
        with self.assertLogs('app.webhook', 'ERROR'):
            response = self.handshake()
        self.assertEqual(response.status_code, 503)

    def test_missing_parameters_are_422(self):
        for missing in ('mode', 'token', 'challenge'):
            with self.subTest(missing=missing):
                response = self.handshake(**{missing: None})
                self.assertEqual(response.status_code, 422)
                self.assertIn('query', response.json()['errors'])

    def test_business_id_must_be_a_number(self):
        self.assertEqual(self.handshake(url='/webhook/abc').status_code, 422)


class ReceiveWebhookTests(WebhookTestCase):
    """POST /webhook/<business_id>: incoming WhatsApp events."""

    def send(self, payload, signature=VALID_SIGNATURE, raw=None, url=URL):
        headers = {'Content-Type': 'application/json'}
        if signature is not None:
            headers['X-Hub-Signature-256'] = signature
        return self.client.post(url, content=raw if raw is not None else body(payload), headers=headers)

    def test_publishes_customer_messages(self):
        response = self.send(webhook(change([text_message('wamid.1'), text_message('wamid.2', body='Two cakes')])))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'published': 2})
        self.assertEqual([m.message_id for m in self.publisher.published], ['wamid.1', 'wamid.2'])
        self.assertEqual(
            self.publisher.published[1].to_dict(),
            {
                'business_id': BUSINESS_ID,
                'phone_number_id': PHONE_NUMBER_ID,
                'message_id': 'wamid.2',
                'from': '+6591234567',
                'display_name': 'Alice',
                'type': 'text',
                'text': 'Two cakes',
                'timestamp': '2023-11-14T22:13:20+00:00',
            },
        )

    def test_forwards_the_exact_bytes_and_signature_for_checking(self):
        raw = b'{"object": "whatsapp_business_account",  "entry": [], "note": "caf\\u00e9"}'
        with self.assertLogs('app.webhook', 'WARNING'):  # 'sha256=abc' isn't the fake's valid signature
            self.send(None, raw=raw, signature='sha256=abc')
        self.assertEqual(self.verifier.calls, [('verify_signature', BUSINESS_ID, raw, 'sha256=abc')])

    def test_bad_or_missing_signature_is_401_and_nothing_is_published(self):
        for signature in ('sha256=forged', None):
            with self.subTest(signature=signature):
                with self.assertLogs('app.webhook', 'WARNING'):
                    response = self.send(webhook(change([text_message()])), signature=signature)
                self.assertEqual(response.status_code, 401)
                self.assertEqual(self.publisher.calls, 0)
        self.assertEqual(self.verifier.calls[-1][3], None)  # a missing header is forwarded as None

    def test_not_connected_is_404(self):
        self.verifier.error = NOT_CONNECTED
        self.assertEqual(self.send(webhook(change([text_message()]))).status_code, 404)
        self.assertEqual(self.publisher.calls, 0)

    def test_configuration_service_down_is_503(self):
        self.verifier.error = UNAVAILABLE
        with self.assertLogs('app.webhook', 'ERROR'):
            response = self.send(webhook(change([text_message()])))
        self.assertEqual(response.status_code, 503)
        self.assertEqual(self.publisher.calls, 0)

    def test_publish_failure_is_503_so_meta_retries(self):
        self.publisher.fail = True
        with self.assertLogs('app.webhook', 'ERROR'):
            response = self.send(webhook(change([text_message()])))
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()['message'], 'Could not publish the messages; try again later.')

    def test_statuses_only_is_200_with_nothing_published(self):
        statuses = [{'id': 'wamid.out', 'status': 'read', 'timestamp': '1700000000', 'recipient_id': '6591234567'}]
        response = self.send(webhook(change(statuses=statuses)))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'published': 0})
        self.assertEqual(self.publisher.published, [])

    def test_messages_for_another_number_are_not_published(self):
        payload = webhook(change([text_message('wamid.other')], phone_number_id='999'), change([text_message('wamid.mine')]))
        with self.assertLogs('app.parsing', 'WARNING'):
            response = self.send(payload)
        self.assertEqual(response.json(), {'published': 1})
        self.assertEqual([m.message_id for m in self.publisher.published], ['wamid.mine'])

    def test_signed_body_that_is_not_json_is_400(self):
        for raw in (b'not json', b'\xff\xfe', b''):
            with self.subTest(raw=raw):
                response = self.send(None, raw=raw)
                self.assertEqual(response.status_code, 400)
        self.assertEqual(self.publisher.calls, 0)

    def test_signed_json_with_an_unexpected_shape_publishes_nothing(self):
        for payload in ([], {'entry': 'x'}, 'text'):
            with self.subTest(payload=payload):
                response = self.send(payload)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json(), {'published': 0})

    def test_signature_is_checked_before_parsing(self):
        with self.assertLogs('app.webhook', 'WARNING'):
            response = self.send(None, raw=b'not json', signature='sha256=forged')
        self.assertEqual(response.status_code, 401)

    def test_business_id_comes_from_the_url(self):
        self.send(webhook(change([text_message()])), url='/webhook/42')
        self.assertEqual(self.verifier.calls[0][1], 42)
        self.assertEqual(self.publisher.published[0].business_id, 42)


if __name__ == '__main__':
    unittest.main()
