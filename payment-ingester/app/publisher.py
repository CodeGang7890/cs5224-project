"""Publisher for payment events to Pub/Sub (the hand-off to processing-service).

Each Pub/Sub message:
- data: JSON with payment_reference and status (UTF-8)
- attributes: payment_reference, status (for filtering without parsing)

If publishing fails, the webhook answers 503 and Xendit redelivers, so messages
may arrive twice: consumers must drop duplicates by payment_reference.
"""

import json
import logging
import os
import time
from typing import Any

from google.api_core import exceptions as google_exceptions
from google.cloud import pubsub_v1

from . import config

logger = logging.getLogger(__name__)


class PublishError(Exception):
    """At least one payment event couldn't be published."""


class Publisher:
    """Protocol for payment event publishers."""
    
    def publish(self, events: list[dict[str, Any]]) -> None:
        """Publish payment events to Pub/Sub."""
        ...


class PubSubPublisher:
    """Publishes payment events to Google Cloud Pub/Sub."""
    
    def __init__(
        self,
        project_id: str = config.GCP_PROJECT_ID,
        topic: str = config.PUBSUB_TOPIC,
        client: pubsub_v1.PublisherClient | None = None
    ):
        self._client = client
        self._project_id = project_id
        self._topic = topic
        self._publisher_options = pubsub_v1.types.PublisherOptions(
            enable_message_ordering=False  # Payment events don't need ordering
        )
    
    @property
    def client(self) -> pubsub_v1.PublisherClient:
        if self._client is None:
            self._client = pubsub_v1.PublisherClient(
                publisher_options=self._publisher_options
            )
        return self._client
    
    @property
    def topic_path(self) -> str:
        return self.client.topic_path(self._project_id, self._topic)
    
    def publish(self, events: list[dict[str, Any]]) -> None:
        """Publish payment events to Pub/Sub and wait for confirmation."""
        if not events:
            return
        
        topic_path = self.topic_path
        futures = []
        
        for event in events:
            try:
                future = self.client.publish(
                    topic_path,
                    data=json.dumps(event, ensure_ascii=False).encode(),
                    payment_reference=event['payment_reference'],
                    status=event['status'],
                )
                futures.append((event, future))
            except Exception as exc:
                logger.error('Could not prepare event for publishing: %s', exc)
                raise PublishError(f'Failed to prepare event: {exc}') from exc
        
        # Wait for all publishes to complete
        failed = []
        for event, future in futures:
            try:
                future.result(timeout=config.PUBSUB_PUBLISH_TIMEOUT_SECONDS)
                logger.info('Published payment event: %s', event['payment_reference'])
            except Exception as exc:
                logger.error('Could not publish payment event %s: %s', 
                           event['payment_reference'], exc)
                failed.append(event)
        
        if failed:
            raise PublishError(f'{len(failed)} of {len(events)} event(s) could not be published.')
        
        logger.info('Published %d payment event(s) to %s', len(events), topic_path)


def ensure_emulator_resources(attempts: int = 30, delay_seconds: float = 1.0) -> None:
    """Create Pub/Sub topic and subscription for local emulator only.
    
    On Google Cloud, these are created by Terraform. The emulator may still be
    starting (docker-compose), so this retries for a while.
    """
    if not os.getenv('PUBSUB_EMULATOR_HOST'):
        return
    
    publisher = pubsub_v1.PublisherClient()
    subscriber = pubsub_v1.SubscriberClient()
    topic_path = publisher.topic_path(config.GCP_PROJECT_ID, config.PUBSUB_TOPIC)
    subscription_path = subscriber.subscription_path(
        config.GCP_PROJECT_ID, 
        'payment-ingester-payments-debug'
    )
    
    for attempt in range(1, attempts + 1):
        try:
            _create_topic_if_missing(
                lambda: publisher.create_topic(request={'name': topic_path}, timeout=5)
            )
            _create_subscription_if_missing(
                lambda: subscriber.create_subscription(
                    request={'name': subscription_path, 'topic': topic_path},
                    timeout=5,
                )
            )
            logger.info('Pub/Sub emulator ready: %s, %s', topic_path, subscription_path)
            return
        except google_exceptions.GoogleAPIError as exc:
            logger.warning('Pub/Sub emulator not ready (attempt %d/%d): %s', 
                         attempt, attempts, exc)
            time.sleep(delay_seconds)
    
    logger.error('Could not set up the Pub/Sub emulator; publishing will fail.')


def _create_topic_if_missing(create_func) -> None:
    try:
        create_func()
    except google_exceptions.AlreadyExists:
        pass


def _create_subscription_if_missing(create_func) -> None:
    try:
        create_func()
    except google_exceptions.AlreadyExists:
        pass
