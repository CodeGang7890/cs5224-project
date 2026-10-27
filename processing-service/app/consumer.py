"""Pull-based Pub/Sub consumer: payment events published by payment-ingester.

Topic `payment-events`, one message per payment event; the data is JSON
`{payment_reference, status, amount?}`: the order's / booking's 128-bit payment reference (32 hex
characters, from configuration-service), `success` or `fail`, and the amount Xendit reports
(used to check the event against the order's / booking's total).

Each event goes through the payment flow (app/payments.py: updates the order / booking in
PostgreSQL). The subscriber uses streaming pull: the client library keeps a connection open and
calls `handle()` on its own threads, at most PUBSUB_MAX_MESSAGES at a time.

- Applied → ack. Pub/Sub delivers at least once: a repeated event changes nothing.
- No such payment reference, the amount doesn't match, or the order / booking isn't waiting for
  this payment → logged as an error and acked: redelivering it would never help.
- Not JSON, or not the contract's shape → logged and acked, for the same reason.
- Anything else raised (e.g. the database is down) → nack, so Pub/Sub redelivers it.
"""

import json
import logging
import math
import re
import time
from collections.abc import Callable

from google.api_core import exceptions as google_exceptions
from google.cloud import pubsub_v1

from . import config
from .db import get_session
from .payments import STATUS_AFTER, PaymentEventError, apply_payment

logger = logging.getLogger(__name__)

STATUSES = tuple(STATUS_AFTER)  # success, fail
PAYMENT_REFERENCE = re.compile(r'^[0-9a-f]{32}$')  # configuration-service's 128-bit references


class InvalidMessageError(ValueError):
    """The Pub/Sub message isn't a payment event (not JSON, or fields missing or wrong)."""


def parse(data: bytes) -> dict:
    """The message's JSON, checked against the contract: a `payment_reference`, a known `status`,
    and (when present) a non-negative numeric `amount`."""
    try:
        payload = json.loads(data)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InvalidMessageError(f'not JSON: {exc}') from exc
    if not isinstance(payload, dict):
        raise InvalidMessageError('not a JSON object')
    
    # Xendit wraps essential event details inside the "data" key
    event_data = payload.get('data', {})
    if not event_data:
        raise InvalidMessageError('Xendit payload is missing the "data" object')

    reference = event_data.get('reference_id')
    if not isinstance(reference, str) or not PAYMENT_REFERENCE.match(reference.lower()):
        raise InvalidMessageError(f'payment_reference must be 32 hex characters, not {reference!r}')

    # Map Xendit "COMPLETED" status to our internal "success" status
    x_status = event_data.get('status')
    internal_status = 'success' if x_status == 'COMPLETED' else 'fail'
    
    amount = event_data.get('amount')
    new_payload = {
        'payment_reference': reference.lower(),
        'status': internal_status,
        'amount': amount
    }

    if amount is not None:
        if isinstance(amount, bool) or not isinstance(amount, (int, float)) or not math.isfinite(amount) or amount < 0:
            raise InvalidMessageError(f'amount must be a finite non-negative number, not {amount!r}')
        new_payload['amount'] = float(amount)

    return new_payload


def process(payload: dict, session_factory: Callable = get_session) -> None:
    """The work for one payment event: the payment flow, in its own session."""
    logger.info('Payment %s: %s (amount %s)', payload['payment_reference'], payload['status'], payload.get('amount'))
    with session_factory() as session:
        apply_payment(session, payload['payment_reference'], payload['status'], payload.get('amount'))


def handle(message, session_factory: Callable = get_session) -> None:
    """Callback for each pulled message (runs on the client library's threads)."""
    try:
        payload = parse(message.data)
    except InvalidMessageError as exc:
        logger.warning('Skipping Pub/Sub message %s: %s', message.message_id, exc)
        message.ack()
        return
    try:
        process(payload, session_factory)
    except PaymentEventError as exc:
        logger.error('Pub/Sub message %s not applied: %s', message.message_id, exc)
        message.ack()
        return
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
