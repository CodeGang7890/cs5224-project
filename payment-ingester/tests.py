"""Tests for payment-ingester: Xendit Payment Sessions, webhooks, and the internal API."""

import json
import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app import xendit_api
from app.routes import app
from app.publisher import PublishError, PubSubPublisher
from app.xendit_api import XenditApiError, XenditUnavailableError
from app.xendit_webhook import InvalidWebhookError, parse_webhook, verify_signature


class TestWebhookVerification(unittest.TestCase):
    """The x-callback-token header is the configured webhook token (not a body signature)."""

    def test_missing_secret_rejects(self):
        with patch('app.xendit_webhook.config.XENDIT_WEBHOOK_SECRET', ''):
            self.assertFalse(verify_signature('some-token'))

    def test_missing_token_rejects(self):
        with patch('app.xendit_webhook.config.XENDIT_WEBHOOK_SECRET', 'secret'):
            self.assertFalse(verify_signature(None))

    def test_wrong_token_rejects(self):
        with patch('app.xendit_webhook.config.XENDIT_WEBHOOK_SECRET', 'secret'):
            self.assertFalse(verify_signature('other'))

    def test_matching_token_passes(self):
        with patch('app.xendit_webhook.config.XENDIT_WEBHOOK_SECRET', 'secret'):
            self.assertTrue(verify_signature('secret'))


class TestParseWebhook(unittest.TestCase):
    def test_session_completed_is_success(self):
        payload = {
            'event': 'payment_session.completed',
            'data': {
                'payment_session_id': 'ps-123',
                'payment_id': 'py-456',
                'reference_id': 'a' * 32,
                'status': 'COMPLETED',
                'amount': 100.00,
                'currency': 'SGD',
            },
        }
        result = parse_webhook(payload)
        self.assertEqual(result['payment_reference'], 'a' * 32)
        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['xendit_payment_id'], 'py-456')
        self.assertEqual(result['amount'], 100.0)
        self.assertEqual(result['currency'], 'SGD')

    def test_session_expired_is_fail(self):
        payload = {
            'event': 'payment_session.expired',
            'data': {
                'payment_session_id': 'ps-123',
                'reference_id': 'b' * 32,
                'status': 'EXPIRED',
                'amount': 50.00,
                'currency': 'SGD',
            },
        }
        self.assertEqual(parse_webhook(payload)['status'], 'fail')

    def test_payment_failure_is_fail(self):
        payload = {
            'event': 'payment.failure',
            'data': {
                'payment_id': 'py-789',
                'reference_id': 'c' * 32,
                'status': 'FAILED',
                'request_amount': 75.50,
                'currency': 'SGD',
            },
        }
        result = parse_webhook(payload)
        self.assertEqual(result['status'], 'fail')
        self.assertEqual(result['amount'], 75.5)

    def test_payment_capture_is_success(self):
        payload = {
            'event': 'payment.capture',
            'data': {
                'payment_id': 'py-789',
                'reference_id': 'd' * 32,
                'status': 'SUCCEEDED',
                'request_amount': 20.00,
                'currency': 'SGD',
            },
        }
        self.assertEqual(parse_webhook(payload)['status'], 'success')

    def test_unsupported_event_is_ignored(self):
        payload = {'event': 'payment.authorization', 'data': {'reference_id': 'e' * 32, 'status': 'AUTHORIZED'}}
        with self.assertRaises(InvalidWebhookError):
            parse_webhook(payload)

    def test_missing_reference_is_invalid(self):
        payload = {'event': 'payment_session.completed', 'data': {'status': 'COMPLETED'}}
        with self.assertRaises(InvalidWebhookError):
            parse_webhook(payload)

    def test_unexpected_status_is_invalid(self):
        payload = {'event': 'payment_session.completed', 'data': {'reference_id': 'f' * 32, 'status': 'ACTIVE'}}
        with self.assertRaises(InvalidWebhookError):
            parse_webhook(payload)


class TestPubSubPublisher(unittest.TestCase):
    def test_publish_empty_list(self):
        PubSubPublisher().publish([])

    @patch('app.publisher.pubsub_v1')
    def test_publish_success(self, _mock_pubsub):
        client = MagicMock()
        client.publish.return_value.result.return_value = 'msg_id_123'
        publisher = PubSubPublisher(client=client)
        publisher.publish([
            {'payment_reference': 'ref1', 'status': 'success', 'amount': 10.0},
            {'payment_reference': 'ref2', 'status': 'fail', 'amount': 20.0},
        ])
        self.assertEqual(client.publish.call_count, 2)

    @patch('app.publisher.pubsub_v1')
    def test_publish_timeout(self, _mock_pubsub):
        client = MagicMock()
        client.publish.return_value.result.side_effect = Exception('Timeout')
        publisher = PubSubPublisher(client=client)
        with self.assertRaises(PublishError):
            publisher.publish([{'payment_reference': 'ref1', 'status': 'success', 'amount': 10.0}])


class TestFastAPIApp(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_health_check(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('message', data)
        self.assertEqual(data['status'], 'healthy')

    @patch('app.routes.verify_signature')
    @patch('app.routes.parse_webhook')
    @patch('app.routes.PubSubPublisher')
    def test_webhook_success(self, mock_publisher_class, mock_parse, mock_verify):
        mock_verify.return_value = True
        mock_parse.return_value = {
            'payment_reference': 'a' * 32,
            'status': 'success',
            'amount': 10.0,
        }
        mock_publisher = MagicMock()
        mock_publisher_class.return_value = mock_publisher

        response = self.client.post(
            '/webhook',
            content=json.dumps({'event': 'payment_session.completed', 'data': {'reference_id': 'a' * 32}}),
            headers={'x-callback-token': 'token', 'Content-Type': 'application/json'},
        )

        self.assertEqual(response.status_code, 200)
        mock_publisher.publish.assert_called_once()

    @patch('app.routes.verify_signature')
    def test_webhook_invalid_token(self, mock_verify):
        mock_verify.return_value = False
        response = self.client.post(
            '/webhook',
            content='{}',
            headers={'x-callback-token': 'wrong'},
        )
        self.assertEqual(response.status_code, 401)

    @patch('app.routes.verify_signature')
    def test_webhook_invalid_json(self, mock_verify):
        mock_verify.return_value = True
        response = self.client.post(
            '/webhook',
            content='not valid json',
            headers={'x-callback-token': 'token'},
        )
        self.assertEqual(response.status_code, 400)


class TestCreatePaymentApi(unittest.TestCase):
    """POST /payments (messaging-service creates the Xendit payment session for a placed order)."""

    VALID_BODY = {
        'kind': 'order',
        'item_id': 7,
        'amount': 123.45,
        'payment_reference': 'a' * 32,
        'customer': {'given_name': 'Alice', 'email': 'alice@example.com'},
        'description': 'Order #7',
    }

    def setUp(self):
        self.client = TestClient(app)

    @patch('app.routes.hmac.compare_digest', return_value=True)
    @patch('app.routes.xendit_api.create_payment')
    def test_create_payment_success(self, mock_create, _mock_digest):
        mock_create.return_value = {
            'xendit_payment_id': 'ps-123',
            'payment_url': 'https://xen.to/abc',
        }
        response = self.client.post(
            '/payments',
            json=self.VALID_BODY,
            headers={'X-Internal-Api-Key': 'some-key'},
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data['xendit_payment_id'], 'ps-123')
        self.assertEqual(data['payment_url'], 'https://xen.to/abc')
        mock_create.assert_called_once()

    def test_create_payment_missing_key(self):
        response = self.client.post('/payments', json=self.VALID_BODY)
        self.assertEqual(response.status_code, 401)

    def test_create_payment_wrong_key(self):
        response = self.client.post(
            '/payments',
            json=self.VALID_BODY,
            headers={'X-Internal-Api-Key': 'wrong-key'},
        )
        self.assertEqual(response.status_code, 401)

    @patch('app.routes.hmac.compare_digest', return_value=True)
    @patch('app.routes.xendit_api.create_payment')
    def test_create_payment_xendit_unavailable(self, mock_create, _mock_digest):
        mock_create.side_effect = XenditUnavailableError('Could not reach Xendit')
        response = self.client.post(
            '/payments',
            json=self.VALID_BODY,
            headers={'X-Internal-Api-Key': 'some-key'},
        )
        self.assertEqual(response.status_code, 503)

    @patch('app.routes.hmac.compare_digest', return_value=True)
    @patch('app.routes.xendit_api.create_payment')
    def test_create_payment_xendit_refused(self, mock_create, _mock_digest):
        mock_create.side_effect = XenditApiError(400, 'amount must be positive')
        response = self.client.post(
            '/payments',
            json=self.VALID_BODY,
            headers={'X-Internal-Api-Key': 'some-key'},
        )
        self.assertEqual(response.status_code, 502)

    def test_create_payment_invalid_body(self):
        response = self.client.post(
            '/payments',
            json={'kind': 'order'},
            headers={'X-Internal-Api-Key': 'some-key'},
        )
        self.assertEqual(response.status_code, 422)


class TestXenditApi(unittest.TestCase):
    """The Payment Sessions request (POST /sessions) and its answer."""

    def test_not_configured(self):
        with patch('app.xendit_api.config.XENDIT_SECRET_KEY', ''):
            with self.assertRaises(XenditUnavailableError):
                xendit_api.create_payment(10.0, 'a' * 32, {'given_name': 'Alice', 'email': 'a@example.com'})

    def test_email_too_long(self):
        with patch('app.xendit_api.config.XENDIT_SECRET_KEY', 'secret'):
            with self.assertRaises(XenditApiError):
                xendit_api.create_payment(
                    10.0, 'a' * 32, {'given_name': 'Alice', 'email': f'{"a" * 49}@example.com'}
                )

    @patch('app.xendit_api.httpx.post')
    def test_creates_a_payment_link_session(self, mock_post):
        response = MagicMock()
        response.status_code = 201
        response.json.return_value = {
            'payment_session_id': 'ps-123',
            'payment_link_url': 'https://xen.to/abc',
        }
        mock_post.return_value = response
        with patch.multiple(
            'app.xendit_api.config',
            XENDIT_SECRET_KEY='secret',
            XENDIT_API_BASE_URL='https://api.xendit.co',
            XENDIT_COUNTRY='SG',
            XENDIT_CURRENCY='SGD',
            XENDIT_ALLOWED_PAYMENT_CHANNELS=['CARDS'],
            XENDIT_SESSION_EXPIRY_SECONDS=1800,
            XENDIT_SUCCESS_URL='',
            XENDIT_FAILURE_URL='',
        ):
            result = xendit_api.create_payment(
                123.45,
                'a' * 32,
                {'given_name': 'Alice Tan', 'email': 'alice@example.com'},
                description='Order #7',
            )

        self.assertEqual(result, {'xendit_payment_id': 'ps-123', 'payment_url': 'https://xen.to/abc'})
        url, kwargs = mock_post.call_args.args[0], mock_post.call_args.kwargs
        self.assertEqual(url, 'https://api.xendit.co/sessions')
        body = kwargs['json']
        self.assertEqual(body['reference_id'], 'a' * 32)
        self.assertEqual(body['session_type'], 'PAY')
        self.assertEqual(body['mode'], 'PAYMENT_LINK')
        self.assertEqual(body['amount'], 123.45)
        self.assertEqual(body['currency'], 'SGD')
        self.assertEqual(body['country'], 'SG')
        self.assertEqual(body['allowed_payment_channels'], ['CARDS'])
        self.assertEqual(body['customer']['email'], 'alice@example.com')
        self.assertEqual(body['customer']['individual_detail'], {'given_names': 'Alice', 'surname': 'Tan'})
        self.assertNotIn('success_return_url', body)
        self.assertNotIn('cancel_return_url', body)

    @patch('app.xendit_api.httpx.post')
    def test_refused_by_xendit(self, mock_post):
        response = MagicMock()
        response.status_code = 400
        response.text = 'invalid amount'
        mock_post.return_value = response
        with patch('app.xendit_api.config.XENDIT_SECRET_KEY', 'secret'):
            with self.assertRaises(XenditApiError) as ctx:
                xendit_api.create_payment(10.0, 'a' * 32, {'given_name': 'Alice', 'email': 'a@example.com'})
        self.assertEqual(ctx.exception.status_code, 400)


if __name__ == '__main__':
    unittest.main()
