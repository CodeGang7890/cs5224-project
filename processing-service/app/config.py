"""Service settings. Constants live here; deployment-specific values come from environment variables."""

import os

# --- This service -------------------------------------------------------------------------
# 8000 is configuration-service, 8001 is reserved for payment-ingester and 8002 is
# messaging-ingester, so this service runs on 8003.
PORT = 8003
# Gunicorn worker processes (gunicorn.conf.py).
WORKERS = int(os.getenv('WEB_CONCURRENCY', '2'))

# --- Pub/Sub consumer (payment events from payment-ingester) ------------------------------
# A pull subscriber (streaming pull) on its own subscription to the payment topic. Off unless
# PUBSUB_CONSUMER_ENABLED is set, so `python run.py` and the tests need no Pub/Sub; docker-compose
# turns it on. With PUBSUB_EMULATOR_HOST set, the library talks to the local emulator, and the
# consumer creates its subscription itself (on Google Cloud: Terraform).
PUBSUB_CONSUMER_ENABLED = os.getenv('PUBSUB_CONSUMER_ENABLED', '').lower() in ('1', 'true', 'yes')
GCP_PROJECT_ID = os.getenv('GCP_PROJECT_ID', 'local-project')
PUBSUB_TOPIC = os.getenv('PUBSUB_TOPIC', 'payment-events')
PUBSUB_SUBSCRIPTION = os.getenv('PUBSUB_SUBSCRIPTION', 'processing-service-payments')
# At most this many messages are handled at once, per worker (Pub/Sub flow control).
PUBSUB_MAX_MESSAGES = int(os.getenv('PUBSUB_MAX_MESSAGES', '5'))
# Stand-in for the real work (invoice, database, notifying the customer: later): each payment event
# waits this long before its ack.
PROCESSING_SECONDS = float(os.getenv('PROCESSING_SECONDS', '2'))

# --- API docs (FastAPI) -------------------------------------------------------------------
API_TITLE = 'Processing Service API'
API_VERSION = 'v1'
