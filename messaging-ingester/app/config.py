"""Service settings. Constants live here; deployment-specific values come from environment variables."""

import os

# --- This service -------------------------------------------------------------------------
# 8000 is configuration-service and 8001 messaging-service, so this service runs on 8002.
PORT = 8002

# --- configuration-service (holds each business's WhatsApp secrets) -----------------------
# The ingester holds no secrets: it asks configuration-service's internal API to check Meta's
# verify token and webhook signatures (yes/no answers only).
CONFIGURATION_SERVICE_URL = os.getenv('CONFIGURATION_SERVICE_URL', 'http://localhost:8000/api').rstrip('/')
# Shared key for /api/internal/ (must equal configuration-service's INTERNAL_API_KEY).
INTERNAL_API_KEY = os.getenv('INTERNAL_API_KEY', 'dev-internal-api-key')
INTERNAL_API_KEY_HEADER = 'X-Internal-Api-Key'
CONFIGURATION_SERVICE_TIMEOUT_SECONDS = 5

# --- Meta (WhatsApp Cloud API) webhooks ---------------------------------------------------
SIGNATURE_HEADER = 'X-Hub-Signature-256'

# --- Pub/Sub ------------------------------------------------------------------------------
# With PUBSUB_EMULATOR_HOST set (docker-compose), the client library talks to the local emulator
# instead of Google Cloud, and the ingester creates the topic and a debug subscription itself.
GCP_PROJECT_ID = os.getenv('GCP_PROJECT_ID', 'local-project')
PUBSUB_TOPIC = os.getenv('PUBSUB_TOPIC', 'whatsapp-inbound-messages')
PUBSUB_DEBUG_SUBSCRIPTION = 'whatsapp-inbound-debug'  # emulator only: for checking what was published
PUBSUB_PUBLISH_TIMEOUT_SECONDS = 10

# --- API docs (FastAPI) -------------------------------------------------------------------
API_TITLE = 'Messaging Ingester API'
API_VERSION = 'v1'
