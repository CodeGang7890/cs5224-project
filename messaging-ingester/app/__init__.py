import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.concurrency import run_in_threadpool

from . import config
from .errors import register_error_handlers
from .publisher import ensure_emulator_resources


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Local Pub/Sub emulator only (PUBSUB_EMULATOR_HOST): create the topic + debug subscription.
    await run_in_threadpool(ensure_emulator_resources)
    yield


def create_app() -> FastAPI:
    """Application factory: builds and configures the FastAPI app."""
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(name)s: %(message)s')
    # The HTTP clients log every request at INFO; the app logs what matters itself.
    for name in ('httpx', 'httpx2'):
        logging.getLogger(name).setLevel(logging.WARNING)
    app = FastAPI(
        title=config.API_TITLE,
        version=config.API_VERSION,
        description=(
            "Receives Meta's WhatsApp webhooks (one Callback URL per business: /webhook/{business_id}), "
            'checks them with configuration-service and publishes each customer message to Pub/Sub.'
        ),
        # OpenAPI spec at /openapi.json, Swagger UI at /docs (assets from the jsDelivr CDN).
        openapi_url='/openapi.json',
        docs_url='/docs',
        redoc_url=None,
        openapi_tags=[
            {'name': 'main', 'description': 'Service health'},
            {'name': 'webhook', 'description': "Meta's WhatsApp webhook"},
        ],
        lifespan=lifespan,
    )
    register_error_handlers(app)

    from .routes import router as main_router
    from .webhook import router as webhook_router

    app.include_router(main_router)
    app.include_router(webhook_router)
    return app
