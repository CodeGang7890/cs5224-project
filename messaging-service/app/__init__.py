from fastapi import FastAPI

from . import config
from .errors import register_error_handlers


def create_app() -> FastAPI:
    """Application factory: builds and configures the FastAPI app."""
    app = FastAPI(
        title=config.API_TITLE,
        version=config.API_VERSION,
        # OpenAPI spec at /openapi.json, Swagger UI at /docs (assets from the jsDelivr CDN).
        openapi_url='/openapi.json',
        docs_url='/docs',
        redoc_url=None,
        openapi_tags=[
            {'name': 'main', 'description': 'Service health / hello world'},
            {'name': 'chat', 'description': 'One-off chat with the LLM (Ollama)'},
        ],
    )
    register_error_handlers(app)

    from .chat import router as chat_router
    from .routes import router as main_router

    app.include_router(main_router)
    app.include_router(chat_router)
    return app
