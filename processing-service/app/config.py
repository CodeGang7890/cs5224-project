"""Service settings. Constants live here; deployment-specific values come from environment variables."""

import os

# --- This service -------------------------------------------------------------------------
# 8000 is configuration-service, 8001 is reserved for payment-ingester and 8002 is
# messaging-ingester, so this service runs on 8003.
PORT = 8003
# Gunicorn worker processes (gunicorn.conf.py).
WORKERS = int(os.getenv('WEB_CONCURRENCY', '2'))

# --- API docs (FastAPI) -------------------------------------------------------------------
API_TITLE = 'Processing Service API'
API_VERSION = 'v1'
