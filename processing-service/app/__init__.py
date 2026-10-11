import logging

from fastapi import FastAPI

from . import config
from .errors import register_error_handlers


def create_app() -> FastAPI:
    """Application factory: builds and configures the FastAPI app."""
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(name)s: %(message)s')
    app = FastAPI(
        title=config.API_TITLE,
        version=config.API_VERSION,
        description='Processes payment events (see TODO.txt). For now: a hello world endpoint.',
        # OpenAPI spec at /openapi.json, Swagger UI at /docs (assets from the jsDelivr CDN).
        openapi_url='/openapi.json',
        docs_url='/docs',
        redoc_url=None,
        openapi_tags=[{'name': 'main', 'description': 'Service health'}],
    )
    register_error_handlers(app)

    from .routes import router as main_router

    app.include_router(main_router)
    return app
