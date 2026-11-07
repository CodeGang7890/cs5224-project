"""Service settings. Constants live here; deployment-specific values come from environment variables."""

import os

# --- This service -------------------------------------------------------------------------
# Port 8001 is reserved for payment-ingester
PORT = 8001
# Gunicorn worker processes (gunicorn.conf.py).
WORKERS = int(os.getenv('WEB_CONCURRENCY', '2'))

# --- Xendit webhook receiver ---------------------------------------------------------------
# The token Xendit sends in the `x-callback-token` header (dashboard: Settings > Webhooks).
# The webhook is rejected when this is empty, so set it before testing with Xendit.
XENDIT_WEBHOOK_SECRET = os.getenv('XENDIT_WEBHOOK_SECRET', '')

# --- Xendit Payment Sessions API (the hosted payment link the customer pays on) -------------
# The secret key of the Xendit account (test mode for now). Server-side only: never in the
# frontend. Empty = creating payments is unavailable (the webhook receiver still works).
XENDIT_SECRET_KEY = os.getenv('XENDIT_SECRET_KEY', '')
XENDIT_API_BASE_URL = os.getenv('XENDIT_API_BASE_URL', 'https://api.xendit.co')
XENDIT_COUNTRY = os.getenv('XENDIT_COUNTRY', 'SG')
XENDIT_CURRENCY = os.getenv('XENDIT_CURRENCY', 'SGD')
# Comma-separated payment channels the customer may choose on Xendit's hosted page.
# Empty: every activated channel. `CARDS`: cards only.
XENDIT_ALLOWED_PAYMENT_CHANNELS = [
    channel.strip().upper()
    for channel in os.getenv('XENDIT_ALLOWED_PAYMENT_CHANNELS', 'CARDS').split(',')
    if channel.strip()
]
# How long the payment link stays open (seconds): 3 hours
XENDIT_SESSION_EXPIRY_SECONDS = int(os.getenv('XENDIT_SESSION_EXPIRY_SECONDS', '10800'))
XENDIT_TIMEOUT_SECONDS = int(os.getenv('XENDIT_TIMEOUT_SECONDS', '15'))
# Where the customer lands after the payment session completes or is stopped/canceled. Xendit
# requires HTTPS; leave empty for local development (the hosted page then uses its own result page).
XENDIT_SUCCESS_URL = os.getenv('XENDIT_SUCCESS_URL', '')
XENDIT_FAILURE_URL = os.getenv('XENDIT_FAILURE_URL', '')

# The shared key other services send in the X-Internal-Api-Key header to create payments
# (messaging-service). Must equal configuration-service's INTERNAL_API_KEY. Empty disables it.
INTERNAL_API_KEY = os.getenv('INTERNAL_API_KEY', 'dev-internal-api-key')

# --- Pub/Sub publisher (payment events to processing-service) ------------------------------
# A Pub/Sub topic for payment events. The processing-service pulls from its own subscription.
GCP_PROJECT_ID = os.getenv('GCP_PROJECT_ID', 'local-project')
PUBSUB_TOPIC = os.getenv('PUBSUB_TOPIC', 'payment-events')
# Timeout for publishing to Pub/Sub (seconds).
PUBSUB_PUBLISH_TIMEOUT_SECONDS = int(os.getenv('PUBSUB_PUBLISH_TIMEOUT_SECONDS', '5'))
# At most this many messages are published at once (Pub/Sub batch settings).
PUBSUB_MAX_BATCH_SIZE = int(os.getenv('PUBSUB_MAX_BATCH_SIZE', '1000'))
PUBSUB_MAX_LATENCY = float(os.getenv('PUBSUB_MAX_LATENCY', '0.1'))

# --- API docs (FastAPI) -------------------------------------------------------------------
API_TITLE = 'Payment Ingester API'
API_VERSION = 'v1'
