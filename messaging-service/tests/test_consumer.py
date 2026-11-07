import json
from datetime import datetime, timedelta, timezone
import os
import unittest
from types import SimpleNamespace
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

    def __init__(self, data: bytes, message_id: str = 'pubsub-1', attributes=None, delivery_attempt=None):
        self.data = data
        self.message_id = message_id
        self.attributes = attributes or {}
        self.delivery_attempt = delivery_attempt
        self.acked = self.nacked = self.dropped = False

    def ack(self):
        self.acked = True

    def nack(self):
        self.nacked = True

    def drop(self):
        self.dropped = True


def message(payload=PAYLOAD) -> FakeMessage:
    return FakeMessage(json.dumps(payload).encode())


class ParseTests(unittest.TestCase):
    def test_the_ingesters_message(self):
        self.assertEqual(parse(json.dumps(PAYLOAD).encode()), PAYLOAD)

    def test_anything_else_is_invalid(self):
        for data in (b'not json', b'\xff\xfe', b'[1, 2]', json.dumps({'business_id': 1}).encode()):
            with self.subTest(data=data), self.assertRaises(InvalidMessageError):
                parse(data)


@patch('app.inbound.handle_inbound')
class HandleTests(unittest.TestCase):
    """handle(): the Pub/Sub side (ack / nack, stats); the chat flow is app/inbound.py (test_inbound.py)."""

    def setUp(self):
        self.stats = ConsumerStats()

    def test_a_message_is_logged_then_answered_then_acked(self, handle_inbound):
        handle_inbound.return_value = SimpleNamespace(outcome='replied')
        pulled = message()
        sessions = MagicMock()
        with self.assertLogs('app.consumer', level='INFO') as logs:
            handle(pulled, self.stats, sessions)
        self.assertTrue(pulled.acked)
        self.assertFalse(pulled.nacked)
        handle_inbound.assert_called_once_with(sessions, PAYLOAD)
        self.assertIn("Customer message wamid.1 for business 1 from +6591234567 (text): 'Hi! Do you have pandan chiffon cake?'", logs.output[0])
        self.assertEqual((self.stats.handled, self.stats.skipped, self.stats.failed), (1, 0, 0))

    def test_the_time_waiting_in_pubsub_is_logged(self, handle_inbound):
        handle_inbound.return_value = SimpleNamespace(outcome='replied')
        pulled = message()
        pulled.publish_time = datetime.now(timezone.utc) - timedelta(seconds=2)
        with self.assertLogs('app.latency', level='INFO') as logs:
            handle(pulled, self.stats, MagicMock())
        self.assertRegex(logs.output[0], r'\[LATENCY\]\[PUBSUB\] 2\.\d{3}s channel=whatsapp business=1 msg=wamid\.1$')
        self.assertRegex(logs.output[1], r'\[LATENCY\]\[E2E\] \d+\.\d{3}s channel=whatsapp business=1 msg=wamid\.1 outcome=replied$')

    def test_a_skipped_message_is_acked_too(self, handle_inbound):
        handle_inbound.return_value = SimpleNamespace(outcome='skipped', reason='already replied (a duplicate)')
        pulled = message()
        with self.assertLogs('app.consumer', level='INFO') as logs:
            handle(pulled, self.stats, MagicMock())
        self.assertTrue(pulled.acked)
        self.assertIn('not answered: already replied (a duplicate)', logs.output[-1])

    def test_a_failure_nacks_so_it_is_redelivered(self, handle_inbound):
        handle_inbound.side_effect = RuntimeError('the LLM is down')
        pulled = message()
        with self.assertLogs('app.consumer', level='ERROR'):
            handle(pulled, self.stats, MagicMock())
        self.assertTrue(pulled.nacked)
        self.assertFalse(pulled.acked)
        self.assertEqual((self.stats.handled, self.stats.failed), (0, 1))

    def test_a_malformed_message_is_acked_without_processing(self, handle_inbound):
        pulled = FakeMessage(b'garbage')
        with self.assertLogs('app.consumer', level='WARNING'):
            handle(pulled, self.stats)
        self.assertTrue(pulled.acked)
        handle_inbound.assert_not_called()
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
        flow_control = subscriber.subscribe.call_args.kwargs['flow_control']
        self.assertEqual(flow_control.max_messages, config.PUBSUB_MAX_MESSAGES)
        # Leases of the ack deadline (the library's default would be 60s whatever the subscription says).
        self.assertEqual(flow_control.min_duration_per_lease_extension, config.PUBSUB_ACK_DEADLINE_SECONDS)
        self.assertEqual(flow_control.max_duration_per_lease_extension, config.PUBSUB_ACK_DEADLINE_SECONDS)
        self.assertTrue(pull.running)
        # The callback handles each pulled message.
        callback = subscriber.subscribe.call_args.kwargs['callback']
        pulled = message()
        with patch('app.inbound.handle_inbound', return_value=SimpleNamespace(outcome='replied')), \
                self.assertLogs('app.consumer'):
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


class TestMessageTests(unittest.TestCase):
    """Test messages (POST /consumer/test/...): the consumer nacks them after a while, or leaves them
    without an ack, never treating them as customer messages."""

    def setUp(self):
        self.stats = ConsumerStats()

    def marked(self, behavior):
        return FakeMessage(b'{"test": "%s"}' % behavior.encode(), attributes={'test_behavior': behavior}, delivery_attempt=2)

    @patch('app.consumer.time.sleep')
    @patch('app.inbound.handle_inbound')
    def test_nack_waits_then_nacks(self, handle_inbound, sleep):
        pulled = self.marked('nack')
        with self.assertLogs('app.consumer', level='WARNING') as logs:
            handle(pulled, self.stats)
        sleep.assert_called_once_with(config.PUBSUB_TEST_NACK_DELAY_SECONDS)
        self.assertEqual((pulled.acked, pulled.nacked, pulled.dropped), (False, True, False))
        self.assertIn('delivery attempt 2', logs.output[0])
        handle_inbound.assert_not_called()
        self.assertEqual((self.stats.handled, self.stats.skipped, self.stats.failed), (0, 0, 0))

    @patch('app.consumer.time.sleep')
    def test_no_ack_leaves_it_without_acking(self, sleep):
        pulled = self.marked('no_ack')
        with self.assertLogs('app.consumer', level='WARNING') as logs:
            handle(pulled, self.stats)
        # Dropped from lease management: no ack, no nack, redelivered after the ack deadline.
        self.assertEqual((pulled.acked, pulled.nacked, pulled.dropped), (False, False, True))
        sleep.assert_not_called()
        self.assertIn(f'{config.PUBSUB_ACK_DEADLINE_SECONDS}s ack deadline', logs.output[0])

    def test_an_unknown_behavior_is_an_ordinary_malformed_message(self):
        pulled = self.marked('explode')
        with self.assertLogs('app.consumer', level='WARNING'):
            handle(pulled, self.stats)
        self.assertTrue(pulled.acked)
        self.assertEqual(self.stats.skipped, 1)


class TestEndpointsTests(unittest.TestCase):
    """POST /consumer/test/nack and /consumer/test/no-ack: only with PUBSUB_TEST_ENDPOINTS_ENABLED."""

    def client(self, enabled=True, publisher=None):
        from app.consumer_routes import get_test_publisher

        with patch.object(config, 'PUBSUB_TEST_ENDPOINTS_ENABLED', enabled):
            app = create_app(consumer=None)
        self.publisher = publisher or MagicMock()
        self.publisher.topic_path.side_effect = lambda project, topic: f'projects/{project}/topics/{topic}'
        self.publisher.publish.return_value.result.return_value = '42'
        app.dependency_overrides[get_test_publisher] = lambda: self.publisher
        return TestClient(app)

    def test_off_by_default(self):
        client = self.client(enabled=False)
        self.assertEqual(client.post('/consumer/test/nack').status_code, 404)
        self.assertEqual(client.post('/consumer/test/no-ack').status_code, 404)

    def test_publishes_a_test_message_to_the_consumers_topic(self):
        client = self.client()
        for path, behavior in (('nack', 'nack'), ('no-ack', 'no_ack')):
            with self.subTest(path=path):
                response = client.post(f'/consumer/test/{path}')
                self.assertEqual(response.status_code, 202, response.json())
                topic = f'projects/{config.GCP_PROJECT_ID}/topics/{config.PUBSUB_TOPIC}'
                self.assertEqual(response.json(), {'behavior': behavior, 'pubsub_message_id': '42', 'topic': topic})
                args, kwargs = self.publisher.publish.call_args
                self.assertEqual(args[0], topic)
                self.assertEqual(json.loads(args[1])['test'], behavior)
                self.assertEqual(kwargs, {'test_behavior': behavior})

    def test_publishing_failure_is_503(self):
        client = self.client()
        self.publisher.publish.return_value.result.side_effect = google_exceptions.ServiceUnavailable('emulator down')
        response = client.post('/consumer/test/nack')
        self.assertEqual(response.status_code, 503)
        self.assertIn('Could not publish the test message', response.json()['message'])
