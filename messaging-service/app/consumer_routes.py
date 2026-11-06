from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException, Request
from google.cloud import pubsub_v1

from . import config
from .consumer import TEST_NACK, TEST_NO_ACK, publish_test_message
from .schemas import ConsumerStatus, ConsumerTestMessage, ErrorResponse

router = APIRouter(tags=['consumer'])
# Only with PUBSUB_TEST_ENDPOINTS_ENABLED (create_app): for trying the retry / dead-letter settings.
test_router = APIRouter(prefix='/consumer/test', tags=['consumer'])


@router.get('/consumer', summary="The Pub/Sub consumer's status")
def consumer_status(request: Request) -> ConsumerStatus:
    """Whether this worker's consumer is pulling messages, and what it has done since it started.
    With several Gunicorn workers, each has its own consumer and counts: this is the one that
    answered."""
    consumer = request.app.state.consumer
    if consumer is None:
        return ConsumerStatus(enabled=False, running=False, subscription=None, handled=0, skipped=0, failed=0)
    stats = consumer.stats
    return ConsumerStatus(
        enabled=True,
        running=consumer.running,
        subscription=consumer.subscription,
        handled=stats.handled,
        skipped=stats.skipped,
        failed=stats.failed,
    )


@lru_cache
def get_test_publisher() -> pubsub_v1.PublisherClient:
    """The publisher for test messages, created on first use (tests override it)."""
    return pubsub_v1.PublisherClient()


def _publish(publisher, behavior: str) -> ConsumerTestMessage:
    try:
        message_id = publish_test_message(publisher, behavior)
    except Exception as exc:  # google.api_core errors, timeouts...
        raise HTTPException(status_code=503, detail=f'Could not publish the test message: {exc}') from exc
    topic = publisher.topic_path(config.GCP_PROJECT_ID, config.PUBSUB_TOPIC)
    return ConsumerTestMessage(behavior=behavior, pubsub_message_id=message_id, topic=topic)


_TEST_RESPONSES = {503: {'model': ErrorResponse, 'description': 'Pub/Sub refused the message or is unreachable.'}}


@test_router.post('/nack', status_code=202, summary='Publish a test message the consumer nacks', responses=_TEST_RESPONSES)
def test_nack(publisher=Depends(get_test_publisher)) -> ConsumerTestMessage:
    """Publishes a test message to the consumer's topic. The consumer waits
    PUBSUB_TEST_NACK_DELAY_SECONDS (5), then nacks it, every time it's delivered: Pub/Sub
    redelivers it after the retry backoff, and after the maximum delivery attempts moves it to the
    dead-letter topic. The consumer logs each delivery attempt."""
    return _publish(publisher, TEST_NACK)


@test_router.post(
    '/no-ack', status_code=202, summary='Publish a test message the consumer never acks', responses=_TEST_RESPONSES,
)
def test_no_ack(publisher=Depends(get_test_publisher)) -> ConsumerTestMessage:
    """Publishes a test message to the consumer's topic. The consumer leaves it without an ack or
    nack, as if it had crashed: Pub/Sub redelivers it once the ack deadline
    (PUBSUB_ACK_DEADLINE_SECONDS, 120) runs out, and after the maximum delivery attempts moves it
    to the dead-letter topic. The consumer logs each delivery attempt."""
    return _publish(publisher, TEST_NO_ACK)
