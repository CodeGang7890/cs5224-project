"""Gunicorn settings (`gunicorn -c gunicorn.conf.py "app:create_app()"`, as in the Dockerfile).

Gunicorn runs WORKERS processes, each serving the FastAPI app with Uvicorn (uvicorn-worker's
worker class). Each worker also runs its own Pub/Sub consumer when PUBSUB_CONSUMER_ENABLED is set:
they share the subscription's messages. On Cloud Run, PORT is set by the platform.
"""

import os

from app.config import PORT, WORKERS

bind = f"0.0.0.0:{os.getenv('PORT', PORT)}"
workers = WORKERS
worker_class = 'uvicorn_worker.UvicornWorker'
# /chat waits for the LLM (up to OLLAMA_TIMEOUT_SECONDS, 120): give requests longer than that.
timeout = 150
# Shutting down: the consumer lets the messages it's handling finish (Consumer.stop).
graceful_timeout = 30
accesslog = '-'  # access log to stdout
errorlog = '-'
