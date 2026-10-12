import json
import os
import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from google.api_core import exceptions as google_exceptions

from app import config, consumer, create_app
from app.consumer import Consumer, ConsumerStats, InvalidMessageError, ensure_emulator_resources, handle, parse

PAYLOAD = {
    'business_id': 1,
    'phone_number_id': '1359207187280395',
    'message_id': 'wamid.1',
    'from': '+6591234567',
    'display_name': 'Alice',
    'type': 'text',
    'text': 'Hi! Do you have pandan chiffon cake?',
    'timestamp': '2026-10-07T09:45:59+00:00',
}


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


def message(payload=PAYLOAD) -> FakeMessage:
    return FakeMessage(json.dumps(payload).encode())


class ParseTests(unittest.TestCase):
    def test_the_ingesters_message(self):
        self.assertEqual(parse(json.dumps(PAYLOAD).encode()), PAYLOAD)

    def test_anything_else_is_invalid(self):
        for data in (b'not json', b'\xff\xfe', b'[1, 2]', json.dumps({'business_id': 1}).encode()):
            with self.subTest(data=data), self.assertRaises(InvalidMessageError):
                parse(data)


@patch('app.consumer.time.sleep')
class HandleTests(unittest.TestCase):
    def setUp(self):
        self.stats = ConsumerStats()

    def test_a_message_is_logged_then_processed_then_acked(self, sleep):
        pulled = message()
        with self.assertLogs('app.consumer', level='INFO') as logs:
            handle(pulled, self.stats)
        self.assertTrue(pulled.acked)
        self.assertFalse(pulled.nacked)
        sleep.assert_called_once_with(config.PROCESSING_SECONDS)
        self.assertIn("Customer message wamid.1 for business 1 from +6591234567 (text): 'Hi! Do you have pandan chiffon cake?'", logs.output[0])
        self.assertEqual((self.stats.handled, self.stats.skipped, self.stats.failed), (1, 0, 0))

    def test_a_failure_nacks_so_it_is_redelivered(self, sleep):
        sleep.side_effect = RuntimeError('boom')
        pulled = message()
        with self.assertLogs('app.consumer', level='ERROR'):
            handle(pulled, self.stats)
        self.assertTrue(pulled.nacked)
        self.assertFalse(pulled.acked)
        self.assertEqual((self.stats.handled, self.stats.failed), (0, 1))

    def test_a_malformed_message_is_acked_without_processing(self, sleep):
        pulled = FakeMessage(b'garbage')
        with self.assertLogs('app.consumer', level='WARNING'):
            handle(pulled, self.stats)
        self.assertTrue(pulled.acked)
        sleep.assert_not_called()
        self.assertEqual((self.stats.handled, self.stats.skipped), (0, 1))


class EmulatorResourcesTests(unittest.TestCase):
    def clients(self):
        subscriber, publisher = MagicMock(), MagicMock()
        publisher.topic_path.return_value = 'projects/p/topics/t'
        subscriber.subscription_path.return_value = 'projects/p/subscriptions/s'
        return subscriber, publisher

    def test_creates_the_topic_and_an_ordered_subscription(self):
        subscriber, publisher = self.clients()
        ensure_emulator_resources(subscriber, publisher)
        publisher.create_topic.assert_called_once_with(request={'name': 'projects/p/topics/t'}, timeout=5)
        subscriber.create_subscription.assert_called_once_with(
            request={'name': 'projects/p/subscriptions/s', 'topic': 'projects/p/topics/t', 'enable_message_ordering': True},
            timeout=5,
        )

    def test_already_existing_is_fine(self):
        subscriber, publisher = self.clients()
        publisher.create_topic.side_effect = google_exceptions.AlreadyExists('topic')
        subscriber.create_subscription.side_effect = google_exceptions.AlreadyExists('subscription')
        ensure_emulator_resources(subscriber, publisher)  # no error

    @patch('app.consumer.time.sleep')
    def test_retries_while_the_emulator_starts(self, sleep):
        subscriber, publisher = self.clients()
        publisher.create_topic.side_effect = [google_exceptions.ServiceUnavailable('starting'), None]
        with self.assertLogs('app.consumer', level='WARNING'):
            ensure_emulator_resources(subscriber, publisher, attempts=3, delay_seconds=0)
        self.assertEqual(publisher.create_topic.call_count, 2)
        subscriber.create_subscription.assert_called_once()


class ConsumerTests(unittest.TestCase):
    def test_streaming_pull_on_its_subscription_with_flow_control(self):
        subscriber = MagicMock()
        future = subscriber.subscribe.return_value
        future.done.return_value = False
        pull = Consumer(subscriber=subscriber)
        self.assertFalse(pull.running)
        pull.start()
        path, = subscriber.subscribe.call_args.args
        self.assertEqual(path, f'projects/{config.GCP_PROJECT_ID}/subscriptions/{config.PUBSUB_SUBSCRIPTION}')
        self.assertEqual(subscriber.subscribe.call_args.kwargs['flow_control'].max_messages, config.PUBSUB_MAX_MESSAGES)
        self.assertTrue(pull.running)
        # The callback handles each pulled message.
        callback = subscriber.subscribe.call_args.kwargs['callback']
        pulled = message()
        with patch('app.consumer.time.sleep'), self.assertLogs('app.consumer'):
            callback(pulled)
        self.assertTrue(pulled.acked)
        self.assertEqual(pull.stats.handled, 1)
        pull.stop()
        future.cancel.assert_called_once()
        subscriber.close.assert_called_once()

    def test_with_the_emulator_it_creates_its_resources_first(self):
        subscriber, publisher = MagicMock(), MagicMock()
        with patch.object(consumer, 'ensure_emulator_resources') as ensure:
            Consumer(subscriber=subscriber, publisher=publisher).start(emulator=True)
        ensure.assert_called_once_with(subscriber, publisher)
        subscriber.subscribe.assert_called_once()


class AppConsumerTests(unittest.TestCase):
    def test_off_by_default(self):
        with TestClient(create_app()) as client:
            self.assertEqual(client.get('/consumer').json(), {
                'enabled': False, 'running': False, 'subscription': None, 'handled': 0, 'skipped': 0, 'failed': 0,
            })

    def test_started_and_stopped_with_the_app(self):
        subscriber = MagicMock()
        subscriber.subscribe.return_value.done.return_value = False
        pull = Consumer(subscriber=subscriber)
        with patch.dict(os.environ, {'PUBSUB_EMULATOR_HOST': ''}), TestClient(create_app(consumer=pull)) as client:
            subscriber.subscribe.assert_called_once()
            status = client.get('/consumer').json()
            self.assertEqual((status['enabled'], status['running'], status['handled']), (True, True, 0))
            self.assertTrue(status['subscription'].endswith('/subscriptions/messaging-service-inbound'))
        subscriber.close.assert_called_once()  # stopped on shutdown

    def test_the_llm_endpoint_is_still_there(self):
        spec = TestClient(create_app()).get('/openapi.json').json()
        self.assertEqual(
            set(spec['paths']),
            {'/', '/chat', '/consumer', '/api/chat/sandbox-sessions/{pk}/messages/', '/api/chat/sessions/messages/'},
        )


if __name__ == '__main__':
    unittest.main()
