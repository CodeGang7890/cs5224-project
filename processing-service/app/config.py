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
# The ack deadline, in seconds: the subscription's (docker-compose's pubsub-init creates it with
# this) and the client's leases, extended by this much while an event is handled.
PUBSUB_ACK_DEADLINE_SECONDS = int(os.getenv('PUBSUB_ACK_DEADLINE_SECONDS', '60'))
# At most this many messages are handled at once, per worker (Pub/Sub flow control).
PUBSUB_MAX_MESSAGES = int(os.getenv('PUBSUB_MAX_MESSAGES', '5'))

# --- configuration-service: sends the customer's WhatsApp message (app/whatsapp_sender.py) ---
CONFIGURATION_SERVICE_URL = os.getenv('CONFIGURATION_SERVICE_URL', 'http://localhost:8000/api').rstrip('/')
INTERNAL_API_KEY = os.getenv('INTERNAL_API_KEY', 'dev-internal-api-key')
WHATSAPP_SEND_TIMEOUT_SECONDS = 20

# --- Email (Brevo) ---------------------------------------------------------------
EMAIL_ENABLED = os.getenv('EMAIL_ENABLED', '').lower() in ('1', 'true', 'yes')
EMAIL_FROM = os.getenv('EMAIL_FROM', '')
EMAIL_FROM_NAME = os.getenv('EMAIL_FROM_NAME', 'Ansera')
SMTP_HOST = os.getenv('SMTP_HOST', 'smtp-relay.brevo.com')
SMTP_PORT = int(os.getenv('SMTP_PORT', '587'))
SMTP_USERNAME = os.getenv('SMTP_USERNAME', '')
SMTP_PASSWORD = os.getenv('SMTP_PASSWORD', '')
SMTP_TIMEOUT_SECONDS = 20

# --- Invoice and receipt PDFs (Google Cloud Storage) ---------------------------------------
# The bucket for the invoice and receipt PDFs (Terraform: cs5224-ansera-app-objects). Unset: they are made
# but not uploaded (local development, the tests).
GCS_BUCKET = os.getenv('GCS_BUCKET', '')
INVOICE_CURRENCY = os.getenv('INVOICE_CURRENCY', 'SGD')
# Where customers open them: configuration-service's public address (e.g. https://ansera.hopto.org), for
# short links (app/document_links.py). Unset: the messages carry 7-day signed Cloud Storage links.
DOCUMENTS_PUBLIC_URL = os.getenv('DOCUMENTS_PUBLIC_URL', '').rstrip('/')

# --- PostgreSQL (configuration-service's database) -----------------------------------------
# The payment flow updates orders / bookings there (app/payments.py). Same variable names as
# configuration-service; defaults are docker-compose's PostgreSQL as seen from the host (port 5433).
# In Docker: POSTGRES_HOST=postgres, POSTGRES_PORT=5432.
POSTGRES_DB = os.getenv('POSTGRES_DB', 'configuration_service')
POSTGRES_USER = os.getenv('POSTGRES_USER', 'postgres')
POSTGRES_PASSWORD = os.getenv('POSTGRES_PASSWORD', 'postgres')
POSTGRES_HOST = os.getenv('POSTGRES_HOST', 'localhost')
POSTGRES_PORT = int(os.getenv('POSTGRES_PORT', '5433'))
# A full SQLAlchemy URL overrides the values above (e.g. Cloud SQL).
DATABASE_URL = os.getenv('DATABASE_URL', '')

# The time zone of the service providers' weekly availabilities: must equal configuration-service's
# SCHEDULE_TIME_ZONE (env DJANGO_SCHEDULE_TIME_ZONE there).
SCHEDULE_TIME_ZONE = os.getenv('SCHEDULE_TIME_ZONE', 'Asia/Singapore')

# --- API docs (FastAPI) -------------------------------------------------------------------
API_TITLE = 'Processing Service API'
API_VERSION = 'v1'
