"""Pull-based Pub/Sub consumer: customer messages published by messaging-ingester.

Topic `whatsapp-inbound-messages`, one message per customer message; the data is JSON
(`business_id`, `phone_number_id`, `message_id`, `from`, `display_name`, `type`, `text`,
`timestamp`: see messaging-ingester/README.md, "Pub/Sub message contract").

Each message is answered by the chat flow (app/inbound.py: the customer's chat, the router, the
order / booking steps, the reply; duplicates by `message_id` are answered once), then
acknowledged. The subscriber uses streaming pull: the client library keeps a connection open and
calls `handle()` on its own threads, at most PUBSUB_MAX_MESSAGES at a time. The ingester publishes
with `<business_id>:<customer's number>` as the ordering key and the subscription has message
ordering, so one customer's messages to a business come in order and one at a time: the client
library holds the next message of a key until the previous one is acked (or nacked), which is only
once its turn is over and the replies are sent. Different customers' messages run in parallel.

- Handled (answered, or skipped: not text, unknown business, a duplicate) → ack.
- Handling raised (e.g. the LLM is down) → nack, so Pub/Sub redelivers it (the turn runs again,
  without saving the customer message twice).
- Not JSON, or not the contract's shape → logged and acked: redelivering it would never help.

A nacked message is redelivered after the subscription's retry backoff, and one not acked within
the ack deadline (PUBSUB_ACK_DEADLINE_SECONDS: the client keeps extending it while a message is
being handled) once it runs out; after the subscription's maximum delivery attempts, Pub/Sub moves
it to the dead-letter topic (docker-compose's pubsub-init sets these up).

Test messages (POST /consumer/test/…, app/consumer_routes.py, only with
PUBSUB_TEST_ENDPOINTS_ENABLED) carry the `test_behavior` attribute: the consumer misbehaves on
purpose, to try those settings: `nack` waits PUBSUB_TEST_NACK_DELAY_SECONDS then nacks; `no_ack`
leaves without acking (as if the worker had crashed).
"""

import json
import logging
import threading
import time
from datetime import datetime, timezone
from dataclasses import dataclass, field

from google.api_core import exceptions as google_exceptions
from google.cloud import pubsub_v1

from . import config, latency

logger = logging.getLogger(__name__)

REQUIRED_FIELDS = ('business_id', 'message_id', 'from', 'type')

# Test messages: the attribute, and what the consumer does with them.
TEST_BEHAVIOR_ATTRIBUTE = 'test_behavior'
TEST_NACK, TEST_NO_ACK = 'nack', 'no_ack'
TEST_BEHAVIORS = (TEST_NACK, TEST_NO_ACK)


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


def process(payload: dict, sessions=None, published=None) -> None:
    """The work for one customer message: answer it with the chat flow (app/inbound.py).

    Logs `[LATENCY][E2E]` (from here until the last reply was sent) and `[LATENCY][SUMMARY]`;
    with `published` (the Pub/Sub message's publish time), `[LATENCY][PUBSUB]` too: how long it waited.
    """
    from .db import get_sessionmaker  # here: building the app (and the tests) needs no database
    from .inbound import handle_inbound

    logger.info(
        'Customer message %s for business %s from %s (%s): %r',
        payload['message_id'], payload['business_id'], payload['from'], payload['type'], payload.get('text'),
    )
    with latency.bind(channel='whatsapp', business=payload['business_id'], msg=payload['message_id']):
        timer = latency.Timer()
        if published is not None:
            waited = (datetime.now(timezone.utc) - published).total_seconds()
            latency.log(['PUBSUB'], max(waited, 0.0))
        outcome = 'error'
        try:
            result = handle_inbound(sessions or get_sessionmaker(), payload)
            outcome = result.outcome
        finally:
            latency.log(['E2E'], timer.elapsed, outcome=outcome)
            latency.summary(timer.elapsed, outcome=outcome)
    if result.outcome == 'skipped':
        logger.info('Message %s not answered: %s', payload['message_id'], result.reason)


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


def _publish_time(message) -> datetime | None:
    """The Pub/Sub message's publish time (aware), if it has one."""
    published = getattr(message, 'publish_time', None)
    if not isinstance(published, datetime):
        return None
    return published if published.tzinfo else published.replace(tzinfo=timezone.utc)


def handle(message, stats: ConsumerStats, sessions=None) -> None:
    """Callback for each pulled message (runs on the client library's threads)."""
    behavior = (getattr(message, 'attributes', None) or {}).get(TEST_BEHAVIOR_ATTRIBUTE)
    if behavior in TEST_BEHAVIORS:
        handle_test(message, behavior)
        return
    try:
        payload = parse(message.data)
    except InvalidMessageError as exc:
        logger.warning('Skipping Pub/Sub message %s: %s', message.message_id, exc)
        message.ack()
        stats.count('skipped')
        return
    try:
        process(payload, sessions, _publish_time(message))
    except Exception:
        logger.exception('Processing Pub/Sub message %s failed; it will be redelivered', message.message_id)
        message.nack()
        stats.count('failed')
        return
    message.ack()
    stats.count('handled')


def handle_test(message, behavior: str) -> None:
    """A test message (not counted in the stats): nack it after a while, or leave without acking."""
    attempt = getattr(message, 'delivery_attempt', None)  # set when the subscription has a dead-letter policy
    if behavior == TEST_NACK:
        logger.warning(
            'Test message %s (delivery attempt %s): nacking it in %ss', message.message_id, attempt,
            config.PUBSUB_TEST_NACK_DELAY_SECONDS,
        )
        time.sleep(config.PUBSUB_TEST_NACK_DELAY_SECONDS)
        message.nack()
        return
    logger.warning(
        'Test message %s (delivery attempt %s): leaving without an ack; redelivered after the %ss ack deadline',
        message.message_id, attempt, config.PUBSUB_ACK_DEADLINE_SECONDS,
    )
    # Neither ack nor nack, and no more lease extensions (the client would keep extending it for up
    # to an hour otherwise): as if the worker had crashed.
    message.drop()


def publish_test_message(publisher, behavior: str) -> str:
    """Publishes a test message (POST /consumer/test/…) to the topic; returns its Pub/Sub id."""
    topic = publisher.topic_path(config.GCP_PROJECT_ID, config.PUBSUB_TOPIC)
    data = json.dumps({'test': behavior, 'sent_time': datetime.now(timezone.utc).isoformat()}).encode()
    future = publisher.publish(topic, data, **{TEST_BEHAVIOR_ATTRIBUTE: behavior})
    return future.result(timeout=config.PUBSUB_PUBLISH_TIMEOUT_SECONDS)


def flow_control() -> pubsub_v1.types.FlowControl:
    """At most PUBSUB_MAX_MESSAGES at a time; leases of PUBSUB_ACK_DEADLINE_SECONDS (the library's
    own default is 60s, whatever the subscription says)."""
    return pubsub_v1.types.FlowControl(
        max_messages=config.PUBSUB_MAX_MESSAGES,
        min_duration_per_lease_extension=config.PUBSUB_ACK_DEADLINE_SECONDS,
        max_duration_per_lease_extension=config.PUBSUB_ACK_DEADLINE_SECONDS,
    )


def ensure_emulator_resources(subscriber, publisher, attempts: int = 30, delay_seconds: float = 1.0) -> None:
    """With the local emulator only: creates the topic (if the ingester hasn't yet) and this
    service's subscription, with message ordering (the ingester's ordering key is the business and
    the customer), if docker-compose's pubsub-init hasn't (it adds the ack deadline, retry backoff
    and dead-letter topic). The emulator may still be starting, so this retries for a while."""
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

    def __init__(self, subscriber=None, publisher=None, sessions=None):
        self._subscriber = subscriber
        self._sessions = sessions  # the database (default: config's, created on first use)
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
            callback=lambda message: handle(message, self.stats, self._sessions),
            flow_control=flow_control(),
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
