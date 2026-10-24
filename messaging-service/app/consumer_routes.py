from fastapi import APIRouter, Request

from .schemas import ConsumerStatus

router = APIRouter(tags=['consumer'])


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
