import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app import config, create_app
from app.consumer import Consumer, InvalidMessageError, handle, parse
from app.payments import PaymentNotFoundError

REFERENCE = '3f9c1a2b4d5e6f708192a3b4c5d6e7f8'


class FakeMessage:
    """The parts of a pulled pubsub_v1 Message the consumer uses."""

    def __init__(self, data: bytes, message_id: str = 'pubsub-1'):
        self.data = data
        self.message_id = message_id
        self.acked = self.nacked = False

    def ack(self):
        self.acked = True

    def nack(self):
        self.nacked = True


def event(payment_reference=REFERENCE, status='success', amount=None) -> FakeMessage:
    payload = {
        'payment_reference': payment_reference,
        'status': status,
        'amount': amount,
    }
    return FakeMessage(json.dumps(payload).encode())


class ParseTests(unittest.TestCase):
    def test_nested_xendit_payloads_are_still_accepted(self):
        for status, expected in (
            ('COMPLETED', 'success'), ('SUCCEEDED', 'success'),
            ('EXPIRED', 'fail'), ('FAILED', 'fail'), ('CANCELED', 'fail'),
        ):
            with self.subTest(status=status):
                data = json.dumps({'data': {'reference_id': REFERENCE, 'status': status, 'amount': 5.5}}).encode()
                self.assertEqual(parse(data), {'payment_reference': REFERENCE, 'status': expected, 'amount': 5.5})

    def test_a_payment_event(self):
        for status in ('success', 'fail'):
            self.assertEqual(
                parse(event(status=status).data), {'payment_reference': REFERENCE, 'status': status, 'amount': None},
            )
        self.assertEqual(parse(event(REFERENCE.upper()).data)['payment_reference'], REFERENCE)
        self.assertEqual(
            parse(event(status='success', amount=12.5).data),
            {'payment_reference': REFERENCE, 'status': 'success', 'amount': 12.5},
        )
        self.assertEqual(
            parse(event(status='success', amount=0).data),
            {'payment_reference': REFERENCE, 'status': 'success', 'amount': 0.0},
        )

    def test_anything_else_is_invalid(self):
        bad = (
            b'not json',
            b'[1]',
            b'{"status": "success"}',
            b'{"data": {}}',
            b'{"data": null}',
            b'{"data": [1]}',
            b'{"data": "invalid"}',
            event('pay_1').data,
            event(42).data,
            event(status='PENDING').data,
            event(status=None).data,
            event(status=[]).data,
            event(amount=-1).data,
            event(amount=True).data,
            event(amount='12.50').data,
            event(amount=float('nan')).data,
            event(amount=float('inf')).data,
        )
        for data in bad:
            with self.subTest(data=data), self.assertRaises(InvalidMessageError):
                parse(data)

    def test_unknown_xendit_status_is_rejected_instead_of_becoming_a_failed_payment(self):
        for status in (None, 'PENDING', 'ACTIVE', 'unknown', []):
            with self.subTest(status=status), self.assertRaises(InvalidMessageError):
                parse(json.dumps({'data': {'reference_id': REFERENCE, 'status': status}}).encode())

    def test_nested_xendit_amount_is_validated(self):
        for amount in (-1, True, '5.50', float('nan'), float('inf')):
            with self.subTest(amount=amount), self.assertRaises(InvalidMessageError):
                parse(json.dumps({'data': {
                    'reference_id': REFERENCE, 'status': 'COMPLETED', 'amount': amount,
                }}).encode())


@patch('app.consumer.apply_payment')
class HandleTests(unittest.TestCase):
    def test_completed_xendit_webhook_through_the_actual_ingester_publisher(self, apply_payment):
        # A separate interpreter avoids colliding with both services' "app" packages.
        # Pub/Sub is mocked; parsing and serialization use the real producer code.
        webhook = {
            'event': 'payment_session.completed',
            'created': '2026-10-27T12:28:30.091Z',
            'api_version': 'v1',
            'data': {
                'reference_id': '127017c92ec1d69189ab08917543192f',
                'status': 'COMPLETED',
                'amount': 5.5,
                'currency': 'SGD',
                'payment_id': 'py-9eba653d-83cd-8504-bad4-8a536099a1b4',
                'payment_session_id': 'ps-6ae0988c6e3e5e546730ab94',
            },
        }
        script = '''
import json
import sys
from unittest.mock import MagicMock
from app.xendit_webhook import parse_webhook
from app.publisher import PubSubPublisher
client = MagicMock()
PubSubPublisher(project_id='test-project', topic='payment-queue', client=client).publish(
    [parse_webhook(json.load(sys.stdin))]
)
sys.stdout.buffer.write(client.publish.call_args.kwargs['data'])
'''
        published = subprocess.run(
            [sys.executable, '-c', script],
            cwd=Path(__file__).resolve().parents[2] / 'payment-ingester',
            input=json.dumps(webhook).encode(), capture_output=True, check=True, timeout=30,
        )
        pulled = FakeMessage(published.stdout)
        handle(pulled, session_factory=MagicMock())
        self.assertEqual(apply_payment.call_args.args[1:], (webhook['data']['reference_id'], 'success', 5.5))
        self.assertTrue(pulled.acked)
        self.assertFalse(pulled.nacked)

    def test_runs_the_payment_flow_then_acks(self, apply_payment):
        pulled = event(status='fail', amount=12.5)
        with self.assertLogs('app.consumer', level='INFO') as logs:
            handle(pulled, session_factory=MagicMock())
        self.assertIn(f'Payment {REFERENCE}: fail', logs.output[0])
        self.assertEqual(apply_payment.call_args.args[1:], (REFERENCE, 'fail', 12.5))
        self.assertTrue(pulled.acked)

    def test_an_unknown_payment_reference_is_logged_and_acked(self, apply_payment):
        apply_payment.side_effect = PaymentNotFoundError('no such reference')
        pulled = event()
        with self.assertLogs('app.consumer', level='ERROR'):
            handle(pulled, session_factory=MagicMock())
        self.assertTrue(pulled.acked)

    def test_a_failure_nacks_so_it_is_redelivered(self, apply_payment):
        apply_payment.side_effect = RuntimeError('database down')
        pulled = event()
        with self.assertLogs('app.consumer', level='ERROR'):
            handle(pulled, session_factory=MagicMock())
        self.assertTrue(pulled.nacked)
        self.assertFalse(pulled.acked)

    def test_a_malformed_message_is_acked_without_processing(self, apply_payment):
        pulled = FakeMessage(b'garbage')
        with self.assertLogs('app.consumer', level='WARNING'):
            handle(pulled)
        self.assertTrue(pulled.acked)
        apply_payment.assert_not_called()


class ConsumerTests(unittest.TestCase):
    def test_streaming_pull_on_the_payment_subscription(self):
        subscriber = MagicMock()
        pull = Consumer(subscriber=subscriber)
        pull.start()
        path, = subscriber.subscribe.call_args.args
        self.assertEqual(path, f'projects/{config.GCP_PROJECT_ID}/subscriptions/processing-service-payments')
        self.assertIs(subscriber.subscribe.call_args.kwargs['callback'], handle)
        self.assertEqual(subscriber.subscribe.call_args.kwargs['flow_control'].max_messages, config.PUBSUB_MAX_MESSAGES)
        pull.stop()
        subscriber.subscribe.return_value.cancel.assert_called_once()
        subscriber.close.assert_called_once()

    def test_with_the_emulator_it_creates_its_subscription_first(self):
        subscriber, publisher = MagicMock(), MagicMock()
        publisher.topic_path.return_value = 'projects/p/topics/payment-events'
        subscriber.subscription_path.return_value = 'projects/p/subscriptions/s'
        Consumer(subscriber=subscriber, publisher=publisher).start(emulator=True)
        subscriber.create_subscription.assert_called_once_with(
            request={'name': 'projects/p/subscriptions/s', 'topic': 'projects/p/topics/payment-events'}, timeout=5
        )
        subscriber.subscribe.assert_called_once()

    def test_started_and_stopped_with_the_app(self):
        subscriber = MagicMock()
        with patch.dict(os.environ, {'PUBSUB_EMULATOR_HOST': ''}), TestClient(create_app(consumer=Consumer(subscriber))):
            subscriber.subscribe.assert_called_once()
        subscriber.close.assert_called_once()


if __name__ == '__main__':
    unittest.main()
