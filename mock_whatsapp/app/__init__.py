"""mock_whatsapp: a stand-in for WhatsApp and Meta, to try the whole chat locally without them.

- As a customer (any phone number you pick), you chat with the sample businesses. Each message is
  sent to messaging-ingester's webhook exactly as Meta sends it (app/meta.py: the payload and its
  X-Hub-Signature-256 signature, with the business's App Secret).
- The replies come back to the fake Graph API (app/graph_api.py: POST /v25.0/{phone_number_id}/messages,
  called by configuration-service's internal send endpoint), as they would to Meta, and show up in
  the chat.
"""

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from . import config, db


def create_app() -> FastAPI:
    db.init()
    app = FastAPI(title='Mock WhatsApp', docs_url='/docs', redoc_url=None)
    app.mount('/static', StaticFiles(directory=config.BASE_DIR / 'static'), name='static')

    from .graph_api import router as graph_router
    from .routes import router as ui_router

    app.include_router(ui_router)
    app.include_router(graph_router)
    return app
