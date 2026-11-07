"""Job settings. Database values come from environment variables, with the same names as
configuration-service's (it owns the database and every migration: this job only reads it)."""

import os

# --- PostgreSQL (configuration-service's database) -----------------------------------------
# Defaults are docker-compose's PostgreSQL as seen from the host (port 5433). In Docker,
# POSTGRES_HOST=postgres and POSTGRES_PORT=5432.
POSTGRES_DB = os.getenv('POSTGRES_DB', 'configuration_service')
POSTGRES_USER = os.getenv('POSTGRES_USER', 'postgres')
POSTGRES_PASSWORD = os.getenv('POSTGRES_PASSWORD', 'postgres')
POSTGRES_HOST = os.getenv('POSTGRES_HOST', 'localhost')
POSTGRES_PORT = int(os.getenv('POSTGRES_PORT', '5433'))
# A full SQLAlchemy URL overrides the values above (e.g. Cloud SQL, or SQLite in tests).
DATABASE_URL = os.getenv('DATABASE_URL', '')

# --- configuration-service: sends the customers' WhatsApp messages (app/whatsapp_sender.py) ---
# POST {CONFIGURATION_SERVICE_URL}/internal/whatsapp/{business_id}/send/ (X-Internal-Api-Key). It holds each
# business's WhatsApp access token, so this job never sees it.
CONFIGURATION_SERVICE_URL = os.getenv('CONFIGURATION_SERVICE_URL', 'http://localhost:8000/api').rstrip('/')
INTERNAL_API_KEY = os.getenv('INTERNAL_API_KEY', 'dev-internal-api-key')  # must equal configuration-service's
WHATSAPP_SEND_TIMEOUT_SECONDS = 20

# --- Email (SMTP relay: Brevo; app/email_sender.py) ---------------------------------------------
# Off unless EMAIL_ENABLED is set: then send_email() only logs what it would send, so development never
# emails anyone by accident. Turn it on in production only; the SMTP key goes in Secret Manager.
EMAIL_ENABLED = os.getenv('EMAIL_ENABLED', '').lower() in ('1', 'true', 'yes')
EMAIL_FROM = os.getenv('EMAIL_FROM', '')  # a sender the provider has verified
EMAIL_FROM_NAME = os.getenv('EMAIL_FROM_NAME', 'Ansera')
SMTP_HOST = os.getenv('SMTP_HOST', 'smtp-relay.brevo.com')
SMTP_PORT = int(os.getenv('SMTP_PORT', '587'))  # STARTTLS (Cloud Run blocks port 25)
SMTP_USERNAME = os.getenv('SMTP_USERNAME', '')
SMTP_PASSWORD = os.getenv('SMTP_PASSWORD', '')
SMTP_TIMEOUT_SECONDS = 20

# The currency shown on a payment reminder's amount
INVOICE_CURRENCY = os.getenv('INVOICE_CURRENCY', 'SGD')

# The businesses' time zone, for the times in the reminders (configuration-service's
# DJANGO_SCHEDULE_TIME_ZONE).
SCHEDULE_TIME_ZONE = os.getenv('SCHEDULE_TIME_ZONE', 'Asia/Singapore')

LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
