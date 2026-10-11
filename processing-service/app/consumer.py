"""Pull-based Pub/Sub consumer: payment events published by payment-ingester.

Topic `payment-events`, one message per payment event; the data is JSON `{payment_id, status}`,
where status is `success` or `fail` (see payment-ingester/README.md).

For now each event is only logged, then the consumer sleeps PROCESSING_SECONDS as a stand-in for
the real work (see TODO.txt), then acknowledges it. The subscriber uses streaming pull: the client
library keeps a connection open and calls `handle()` on its own threads, at most
PUBSUB_MAX_MESSAGES at a time.

- Handled → ack. Handling raised → nack, so Pub/Sub redelivers it.
- Not JSON, or not the contract's shape → logged and acked: redelivering it would never help.
- Pub/Sub delivers at least once: make the real work idempotent per `payment_id` (TODO).
"""

import json
import logging
import time

from google.api_core import exceptions as google_exceptions
from google.cloud import pubsub_v1

from . import config

logger = logging.getLogger(__name__)

STATUSES = ('success', 'fail')


class InvalidMessageError(ValueError):
    """The Pub/Sub message isn't a payment event (not JSON, or fields missing or wrong)."""


def parse(data: bytes) -> dict:
    """The message's JSON, checked against the contract: a `payment_id` and a known `status`."""
    try:
        payload = json.loads(data)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InvalidMessageError(f'not JSON: {exc}') from exc
    if not isinstance(payload, dict):
        raise InvalidMessageError('not a JSON object')
    if not payload.get('payment_id'):
        raise InvalidMessageError('missing payment_id')
    if payload.get('status') not in STATUSES:
        raise InvalidMessageError(f'status must be one of {", ".join(STATUSES)}, not {payload.get("status")!r}')
    return payload


def process(payload: dict) -> None:
    """The work for one payment event: for now, log it and wait (the real logic comes later)."""
    logger.info('Payment %s: %s', payload['payment_id'], payload['status'])
    time.sleep(config.PROCESSING_SECONDS)


def handle(message) -> None:
    """Callback for each pulled message (runs on the client library's threads)."""
    try:
        payload = parse(message.data)
    except InvalidMessageError as exc:
        logger.warning('Skipping Pub/Sub message %s: %s', message.message_id, exc)
        message.ack()
        return
    try:
        process(payload)
    except Exception:
        logger.exception('Processing Pub/Sub message %s failed; it will be redelivered', message.message_id)
        message.nack()
        return
    message.ack()


def ensure_emulator_resources(subscriber, publisher, attempts: int = 30, delay_seconds: float = 1.0) -> None:
    """With the local emulator only: creates the topic (docker-compose's pubsub-init normally has
    already) and this service's subscription. The emulator may still be starting, so this retries."""
    topic = publisher.topic_path(config.GCP_PROJECT_ID, config.PUBSUB_TOPIC)
    subscription = subscriber.subscription_path(config.GCP_PROJECT_ID, config.PUBSUB_SUBSCRIPTION)
    for attempt in range(1, attempts + 1):
        try:
            try:
                publisher.create_topic(request={'name': topic}, timeout=5)
            except google_exceptions.AlreadyExists:
                pass
            try:
                subscriber.create_subscription(request={'name': subscription, 'topic': topic}, timeout=5)
            except google_exceptions.AlreadyExists:
                pass
            logger.info('Pub/Sub emulator ready: %s → %s', topic, subscription)
            return
        except google_exceptions.GoogleAPIError as exc:
            logger.warning('Pub/Sub emulator not ready (attempt %d/%d): %s', attempt, attempts, exc)
            time.sleep(delay_seconds)
    logger.error('Gave up creating the Pub/Sub emulator resources; the consumer may not receive anything')


class Consumer:
    """The streaming pull subscriber: start() when the app starts, stop() when it shuts down."""

    def __init__(self, subscriber=None, publisher=None):
        self._subscriber = subscriber
        self._publisher = publisher
        self._future = None

    @property
    def subscription(self) -> str:
        return f'projects/{config.GCP_PROJECT_ID}/subscriptions/{config.PUBSUB_SUBSCRIPTION}'

    def start(self, emulator: bool = False) -> None:
        # The clients are created here, not at import time, so building the app needs no credentials.
        self._subscriber = self._subscriber or pubsub_v1.SubscriberClient()
        if emulator:
            ensure_emulator_resources(self._subscriber, self._publisher or pubsub_v1.PublisherClient())
        self._future = self._subscriber.subscribe(
            self.subscription,
            callback=handle,
            flow_control=pubsub_v1.types.FlowControl(max_messages=config.PUBSUB_MAX_MESSAGES),
        )
        logger.info('Pulling payment events from %s (at most %d at a time)', self.subscription, config.PUBSUB_MAX_MESSAGES)

    def stop(self, timeout_seconds: float = 10) -> None:
        """Stops pulling; messages being handled get up to `timeout_seconds` to finish."""
        if self._future is None:
            return
        self._future.cancel()
        try:
            self._future.result(timeout=timeout_seconds)
        except Exception:  # cancelled, or the stream had already failed: nothing left to do
            pass
        if self._subscriber is not None:
            self._subscriber.close()
        logger.info('Stopped pulling from %s', self.subscription)
