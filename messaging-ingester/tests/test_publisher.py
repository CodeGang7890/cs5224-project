import json
import os
import unittest
import uuid
from concurrent.futures import Future
from unittest.mock import MagicMock, patch

from google.api_core import exceptions as google_exceptions

from app import publisher as publisher_module
from app.parsing import InboundMessage
from app.publisher import PubSubPublisher, PublishError, ensure_emulator_resources

TOPIC_PATH = 'projects/test-project/topics/test-topic'


def message(message_id='wamid.1', sender='+6591234567', text='Hi'):
    return InboundMessage(
        business_id=7,
        phone_number_id='106540352242922',
        message_id=message_id,
        from_number=sender,
        display_name='Alice',
        type='text',
        text=text,
        timestamp='2023-11-14T22:13:20+00:00',
    )


def done(result='server-id'):
    future = Future()
    future.set_result(result)
    return future


def failed(error=None):
    future = Future()
    future.set_exception(error or google_exceptions.ServiceUnavailable('down'))
    return future


class PubSubPublisherTests(unittest.TestCase):
    def setUp(self):
        self.client = MagicMock()
        self.client.topic_path.return_value = TOPIC_PATH
        self.client.publish.side_effect = lambda *args, **kwargs: done()
        self.publisher = PubSubPublisher('test-project', 'test-topic', client=self.client)

    def test_publishes_each_message(self):
        self.publisher.publish([message('wamid.1'), message('wamid.2', sender='+6598765432', text='café')])
        self.client.topic_path.assert_called_with('test-project', 'test-topic')
        self.assertEqual(self.client.publish.call_count, 2)
        args, kwargs = self.client.publish.call_args_list[1]
        self.assertEqual(args, (TOPIC_PATH,))
        self.assertEqual(json.loads(kwargs.pop('data')), message('wamid.2', sender='+6598765432', text='café').to_dict())
        self.assertEqual(
            kwargs,
            {
                'ordering_key': '+6598765432',
                'business_id': '7',
                'phone_number_id': '106540352242922',
                'message_id': 'wamid.2',
            },
        )

    def test_data_is_utf8_json(self):
        self.publisher.publish([message(text='café 🎂')])
        data = self.client.publish.call_args.kwargs['data']
        self.assertIn('café 🎂'.encode(), data)

    def test_nothing_to_publish(self):
        self.publisher.publish([])
        self.client.publish.assert_not_called()

    def test_failure_raises_and_resumes_the_ordering_key(self):
        results = iter([done(), failed(), failed()])
        self.client.publish.side_effect = lambda *args, **kwargs: next(results)
        batch = [message('wamid.1'), message('wamid.2', sender='+6598765432'), message('wamid.3', sender='+6598765432')]
        with self.assertLogs('app.publisher', 'ERROR'), self.assertRaisesRegex(PublishError, '2 of 3'):
            self.publisher.publish(batch)
        self.client.resume_publish.assert_called_once_with(TOPIC_PATH, '+6598765432')

    def test_timeout_counts_as_a_failure(self):
        self.client.publish.side_effect = lambda *args, **kwargs: Future()  # never completes
        with patch.object(publisher_module.config, 'PUBSUB_PUBLISH_TIMEOUT_SECONDS', 0.01):
            with self.assertLogs('app.publisher', 'ERROR'), self.assertRaises(PublishError):
                self.publisher.publish([message()])

    def test_client_is_created_lazily(self):
        with patch.object(publisher_module.pubsub_v1, 'PublisherClient') as client_class:
            lazy = PubSubPublisher('p', 't')
            client_class.assert_not_called()
            lazy.client
            options = client_class.call_args.kwargs['publisher_options']
            self.assertTrue(options.enable_message_ordering)


class EnsureEmulatorResourcesTests(unittest.TestCase):
    def test_does_nothing_without_the_emulator(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(publisher_module.pubsub_v1, 'PublisherClient') as client:
            ensure_emulator_resources()
        client.assert_not_called()

    def test_creates_topic_and_ordered_subscription(self):
        with patch.dict(os.environ, {'PUBSUB_EMULATOR_HOST': 'emulator:8085'}), \
                patch.object(publisher_module.pubsub_v1, 'PublisherClient') as publisher_class, \
                patch.object(publisher_module.pubsub_v1, 'SubscriberClient') as subscriber_class:
            publisher_class.return_value.topic_path.return_value = 'topic-path'
            subscriber_class.return_value.subscription_path.return_value = 'sub-path'
            subscriber_class.return_value.create_subscription.side_effect = google_exceptions.AlreadyExists('exists')
            with self.assertLogs('app.publisher', 'INFO'):
                ensure_emulator_resources()
        publisher_class.return_value.create_topic.assert_called_once_with(request={'name': 'topic-path'}, timeout=5)
        request = subscriber_class.return_value.create_subscription.call_args.kwargs['request']
        self.assertEqual(request, {'name': 'sub-path', 'topic': 'topic-path', 'enable_message_ordering': True})

    def test_retries_then_gives_up_without_crashing(self):
        with patch.dict(os.environ, {'PUBSUB_EMULATOR_HOST': 'emulator:8085'}), \
                patch.object(publisher_module.pubsub_v1, 'PublisherClient') as publisher_class, \
                patch.object(publisher_module.pubsub_v1, 'SubscriberClient'):
            publisher_class.return_value.create_topic.side_effect = google_exceptions.ServiceUnavailable('starting')
            with self.assertLogs('app.publisher', 'WARNING') as logs:
                ensure_emulator_resources(attempts=3, delay_seconds=0)
        self.assertEqual(publisher_class.return_value.create_topic.call_count, 3)
        self.assertIn('ERROR', logs.output[-1])


@unittest.skipUnless(os.getenv('PUBSUB_EMULATOR_HOST'), 'needs the Pub/Sub emulator (PUBSUB_EMULATOR_HOST)')
class EmulatorIntegrationTests(unittest.TestCase):
    """Publishes through the real client library to the local emulator and pulls the result back."""

    def setUp(self):
        from google.cloud import pubsub_v1

        suffix = uuid.uuid4().hex[:8]
        self.publisher = PubSubPublisher('local-project', f'test-topic-{suffix}')
        self.subscriber = pubsub_v1.SubscriberClient()
        self.topic_path = self.publisher.topic_path
        self.subscription_path = self.subscriber.subscription_path('local-project', f'test-sub-{suffix}')
        self.publisher.client.create_topic(request={'name': self.topic_path}, timeout=10)
        self.subscriber.create_subscription(
            request={'name': self.subscription_path, 'topic': self.topic_path, 'enable_message_ordering': True},
            timeout=10,
        )
        self.addCleanup(self.subscriber.delete_subscription, request={'subscription': self.subscription_path})
        self.addCleanup(self.publisher.client.delete_topic, request={'topic': self.topic_path})

    def test_round_trip(self):
        sent = [message('wamid.1', text='first'), message('wamid.2', text='café 🎂')]
        self.publisher.publish(sent)
        response = self.subscriber.pull(request={'subscription': self.subscription_path, 'max_messages': 10}, timeout=10)
        received = [r.message for r in response.received_messages]
        self.assertEqual([json.loads(m.data) for m in received], [m.to_dict() for m in sent])
        self.assertEqual(received[0].ordering_key, '+6591234567')
        self.assertEqual(
            dict(received[1].attributes),
            {'business_id': '7', 'phone_number_id': '106540352242922', 'message_id': 'wamid.2'},
        )
