import json
import os
import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app import config, create_app
from app.consumer import Consumer, InvalidMessageError, handle, parse


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


def event(payment_id='pay_1', status='success') -> FakeMessage:
    return FakeMessage(json.dumps({'payment_id': payment_id, 'status': status}).encode())


class ParseTests(unittest.TestCase):
    def test_a_payment_event(self):
        for status in ('success', 'fail'):
            self.assertEqual(parse(event(status=status).data), {'payment_id': 'pay_1', 'status': status})

    def test_anything_else_is_invalid(self):
        for data in (b'not json', b'[1]', b'{"status": "success"}', b'{"payment_id": "pay_1", "status": "paid"}'):
            with self.subTest(data=data), self.assertRaises(InvalidMessageError):
                parse(data)


@patch('app.consumer.time.sleep')
class HandleTests(unittest.TestCase):
    def test_logs_the_payment_id_and_status_waits_then_acks(self, sleep):
        pulled = event(status='fail')
        with self.assertLogs('app.consumer', level='INFO') as logs:
            handle(pulled)
        self.assertIn('Payment pay_1: fail', logs.output[0])
        sleep.assert_called_once_with(config.PROCESSING_SECONDS)
        self.assertTrue(pulled.acked)

    def test_a_failure_nacks_so_it_is_redelivered(self, sleep):
        sleep.side_effect = RuntimeError('boom')
        pulled = event()
        with self.assertLogs('app.consumer', level='ERROR'):
            handle(pulled)
        self.assertTrue(pulled.nacked)
        self.assertFalse(pulled.acked)

    def test_a_malformed_message_is_acked_without_processing(self, sleep):
        pulled = FakeMessage(b'garbage')
        with self.assertLogs('app.consumer', level='WARNING'):
            handle(pulled)
        self.assertTrue(pulled.acked)
        sleep.assert_not_called()


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
