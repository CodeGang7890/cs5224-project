import json
import os
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
    payload = {'payment_reference': payment_reference, 'status': status}
    if amount is not None:
        payload['amount'] = amount
    return FakeMessage(json.dumps(payload).encode())


class ParseTests(unittest.TestCase):
    def test_a_payment_event(self):
        for status in ('success', 'fail'):
            self.assertEqual(parse(event(status=status).data), {'payment_reference': REFERENCE, 'status': status})
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
            event(status='paid').data,
            event('pay_1').data,
            event(42).data,
            event(amount=-1).data,
            event(amount=True).data,
            event(amount='12.50').data,
            event(amount=float('nan')).data,
            event(amount=float('inf')).data,
        )
        for data in bad:
            with self.subTest(data=data), self.assertRaises(InvalidMessageError):
                parse(data)


@patch('app.consumer.apply_payment')
class HandleTests(unittest.TestCase):
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
