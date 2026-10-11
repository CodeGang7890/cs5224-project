"""Publishes customer messages to the Pub/Sub topic (the hand-off to messaging-service).

Each Pub/Sub message:
- data: the JSON from InboundMessage.to_dict() (UTF-8)
- attributes: business_id, phone_number_id, message_id (strings), for filtering without parsing
- ordering_key: the customer's number, so one customer's messages arrive in order (the
  subscription needs message ordering enabled)

If publishing fails, the webhook answers 503 and Meta redelivers the whole webhook, so messages
that did get published may arrive twice: consumers must drop duplicates by message_id.
"""

import json
import logging
import os
import time
from typing import Protocol

from google.api_core import exceptions as google_exceptions
from google.cloud import pubsub_v1

from . import config
from .parsing import InboundMessage

logger = logging.getLogger(__name__)


class PublishError(Exception):
    """At least one message couldn't be published."""


class Publisher(Protocol):
    def publish(self, messages: list[InboundMessage]) -> None: ...


class PubSubPublisher:
    def __init__(self, project_id: str = config.GCP_PROJECT_ID, topic: str = config.PUBSUB_TOPIC, client=None):
        # The client is created lazily, so building the app (and tests) needs no credentials.
        self._client = client
        self._project_id = project_id
        self._topic = topic

    @property
    def client(self) -> pubsub_v1.PublisherClient:
        if self._client is None:
            self._client = pubsub_v1.PublisherClient(
                publisher_options=pubsub_v1.types.PublisherOptions(enable_message_ordering=True)
            )
        return self._client

    @property
    def topic_path(self) -> str:
        return self.client.topic_path(self._project_id, self._topic)

    def publish(self, messages: list[InboundMessage]) -> None:
        """Publishes every message and waits for Pub/Sub to accept them all."""
        if not messages:
            return
        topic_path = self.topic_path
        futures = [
            (
                message,
                self.client.publish(
                    topic_path,
                    data=json.dumps(message.to_dict(), ensure_ascii=False).encode(),
                    ordering_key=message.from_number,
                    business_id=str(message.business_id),
                    phone_number_id=message.phone_number_id,
                    message_id=message.message_id,
                ),
            )
            for message in messages
        ]
        failed = []
        for message, future in futures:
            try:
                future.result(timeout=config.PUBSUB_PUBLISH_TIMEOUT_SECONDS)
            except Exception as exc:  # google.api_core errors, timeouts...
                logger.error('Could not publish message %s: %s', message.message_id, exc)
                failed.append(message)
        if failed:
            # After a failure, Pub/Sub pauses that ordering key until it's resumed.
            for ordering_key in {message.from_number for message in failed}:
                self.client.resume_publish(topic_path, ordering_key)
            raise PublishError(f'{len(failed)} of {len(messages)} message(s) could not be published.')
        logger.info('Published %d message(s) to %s', len(messages), topic_path)


def ensure_emulator_resources(attempts: int = 30, delay_seconds: float = 1.0) -> None:
    """With the local Pub/Sub emulator only: creates the topic and the debug subscription.

    On Google Cloud they're created by Terraform instead. The emulator may still be starting
    (docker-compose), so this retries for a while; if it still fails, it logs and gives up, and
    publishing answers 503 until the emulator is reachable.
    """
    if not os.getenv('PUBSUB_EMULATOR_HOST'):
        return
    publisher = pubsub_v1.PublisherClient()
    subscriber = pubsub_v1.SubscriberClient()
    topic_path = publisher.topic_path(config.GCP_PROJECT_ID, config.PUBSUB_TOPIC)
    subscription_path = subscriber.subscription_path(config.GCP_PROJECT_ID, config.PUBSUB_DEBUG_SUBSCRIPTION)
    for attempt in range(1, attempts + 1):
        try:
            _create_if_missing(lambda: publisher.create_topic(request={'name': topic_path}, timeout=5))
            _create_if_missing(
                lambda: subscriber.create_subscription(
                    request={'name': subscription_path, 'topic': topic_path, 'enable_message_ordering': True},
                    timeout=5,
                )
            )
            logger.info('Pub/Sub emulator ready: %s, %s', topic_path, subscription_path)
            return
        except google_exceptions.GoogleAPIError as exc:  # unavailable, timeout, retries exhausted...
            logger.warning('Pub/Sub emulator not ready (attempt %d/%d): %s', attempt, attempts, exc)
            time.sleep(delay_seconds)
    logger.error('Could not set up the Pub/Sub emulator topic; publishing will fail until it is reachable.')


def _create_if_missing(create) -> None:
    try:
        create()
    except google_exceptions.AlreadyExists:
        pass
