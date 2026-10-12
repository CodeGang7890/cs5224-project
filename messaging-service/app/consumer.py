"""Pull-based Pub/Sub consumer: customer messages published by messaging-ingester.

Topic `whatsapp-inbound-messages`, one message per customer message; the data is JSON
(`business_id`, `phone_number_id`, `message_id`, `from`, `display_name`, `type`, `text`,
`timestamp`: see messaging-ingester/README.md, "Pub/Sub message contract").

For now each message is only logged, then the consumer sleeps PROCESSING_SECONDS as a stand-in for
the real work (the chat flow, later), then acknowledges it. The subscriber uses streaming pull: the
client library keeps a connection open and calls `handle()` on its own threads, at most
PUBSUB_MAX_MESSAGES at a time.

- Handled → ack. Handling raised → nack, so Pub/Sub redelivers it.
- Not JSON, or not the contract's shape → logged and acked: redelivering it would never help.
- Pub/Sub delivers at least once (and the ingester may publish a message twice): drop duplicates
  by `message_id` before doing real work (TODO, when there is real work).
"""

import json
import logging
import threading
import time
from dataclasses import dataclass, field

from google.api_core import exceptions as google_exceptions
from google.cloud import pubsub_v1

from . import config

logger = logging.getLogger(__name__)

REQUIRED_FIELDS = ('business_id', 'message_id', 'from', 'type')


class InvalidMessageError(ValueError):
    """The Pub/Sub message isn't one of the ingester's (not JSON, or fields missing)."""


def parse(data: bytes) -> dict:
    """The message's JSON, checked against the contract's required fields."""
    try:
        payload = json.loads(data)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InvalidMessageError(f'not JSON: {exc}') from exc
    if not isinstance(payload, dict):
        raise InvalidMessageError('not a JSON object')
    missing = [name for name in REQUIRED_FIELDS if name not in payload]
    if missing:
        raise InvalidMessageError(f'missing {", ".join(missing)}')
    return payload


def process(payload: dict) -> None:
    """The work for one customer message: for now, log it and wait (the chat flow comes later)."""
    logger.info(
        'Customer message %s for business %s from %s (%s): %r',
        payload['message_id'], payload['business_id'], payload['from'], payload['type'], payload.get('text'),
    )
    time.sleep(config.PROCESSING_SECONDS)


@dataclass
class ConsumerStats:
    """What the consumer has done since it started (GET /consumer)."""

    handled: int = 0  # processed and acked
    skipped: int = 0  # malformed: acked without processing
    failed: int = 0  # processing raised: nacked, to be redelivered
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def count(self, outcome: str) -> None:
        with self._lock:
            setattr(self, outcome, getattr(self, outcome) + 1)


def handle(message, stats: ConsumerStats) -> None:
    """Callback for each pulled message (runs on the client library's threads)."""
    try:
        payload = parse(message.data)
    except InvalidMessageError as exc:
        logger.warning('Skipping Pub/Sub message %s: %s', message.message_id, exc)
        message.ack()
        stats.count('skipped')
        return
    try:
        process(payload)
    except Exception:
        logger.exception('Processing Pub/Sub message %s failed; it will be redelivered', message.message_id)
        message.nack()
        stats.count('failed')
        return
    message.ack()
    stats.count('handled')


def ensure_emulator_resources(subscriber, publisher, attempts: int = 30, delay_seconds: float = 1.0) -> None:
    """With the local emulator only: creates the topic (if the ingester hasn't yet) and this
    service's subscription, with message ordering (the ingester orders by customer). The emulator
    may still be starting, so this retries for a while."""
    topic = publisher.topic_path(config.GCP_PROJECT_ID, config.PUBSUB_TOPIC)
    subscription = subscriber.subscription_path(config.GCP_PROJECT_ID, config.PUBSUB_SUBSCRIPTION)
    for attempt in range(1, attempts + 1):
        try:
            try:
                publisher.create_topic(request={'name': topic}, timeout=5)
            except google_exceptions.AlreadyExists:
                pass
            try:
                subscriber.create_subscription(
                    request={'name': subscription, 'topic': topic, 'enable_message_ordering': True}, timeout=5
                )
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
        self.stats = ConsumerStats()

    @property
    def running(self) -> bool:
        return self._future is not None and not self._future.done()

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
            callback=lambda message: handle(message, self.stats),
            flow_control=pubsub_v1.types.FlowControl(max_messages=config.PUBSUB_MAX_MESSAGES),
        )
        logger.info('Pulling messages from %s (at most %d at a time)', self.subscription, config.PUBSUB_MAX_MESSAGES)

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
