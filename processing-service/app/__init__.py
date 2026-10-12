import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.concurrency import run_in_threadpool

from . import config
from .consumer import Consumer
from .errors import register_error_handlers


def lifespan_for(consumer: Consumer | None):
    """Starts the Pub/Sub consumer with the app (each Gunicorn worker runs one) and stops it on
    shutdown. `consumer` None: the consumer is off (PUBSUB_CONSUMER_ENABLED unset)."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if consumer is not None:
            await run_in_threadpool(consumer.start, bool(os.getenv('PUBSUB_EMULATOR_HOST')))
        yield
        if consumer is not None:
            await run_in_threadpool(consumer.stop)

    return lifespan


def create_app(consumer: Consumer | None = None) -> FastAPI:
    """Application factory: builds and configures the FastAPI app.

    The Pub/Sub consumer of payment events runs when PUBSUB_CONSUMER_ENABLED is set (or one is
    passed in, e.g. a test's, with fake clients); otherwise there is none.
    """
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(name)s: %(message)s')
    if consumer is None and config.PUBSUB_CONSUMER_ENABLED:
        consumer = Consumer()
    app = FastAPI(
        title=config.API_TITLE,
        version=config.API_VERSION,
        description='Processes the payment events payment-ingester publishes to Pub/Sub (for now: logs them).',
        # OpenAPI spec at /openapi.json, Swagger UI at /docs (assets from the jsDelivr CDN).
        openapi_url='/openapi.json',
        docs_url='/docs',
        redoc_url=None,
        openapi_tags=[{'name': 'main', 'description': 'Service health'}],
        lifespan=lifespan_for(consumer),
    )
    register_error_handlers(app)

    from .routes import router as main_router

    app.include_router(main_router)
    return app
