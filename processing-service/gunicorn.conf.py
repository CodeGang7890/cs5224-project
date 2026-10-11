"""Gunicorn settings (`gunicorn -c gunicorn.conf.py "app:create_app()"`, as in the Dockerfile).

Gunicorn runs WORKERS processes, each serving the FastAPI app with Uvicorn (uvicorn-worker's
worker class). On Cloud Run, PORT is set by the platform.
"""

import os

from app.config import PORT, WORKERS

bind = f"0.0.0.0:{os.getenv('PORT', PORT)}"
workers = WORKERS
worker_class = 'uvicorn_worker.UvicornWorker'
accesslog = '-'  # access log to stdout
errorlog = '-'
