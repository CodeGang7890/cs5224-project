"""Settings. Environment variables override the defaults (all for local development)."""

import json
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# 8xxx ports are kept for the project's services, so this runs on 9000. It listens on 0.0.0.0, so the
# containers (configuration-service, sending replies) can reach it on the host.
PORT = int(os.getenv('PORT', '9000'))
HOST = os.getenv('HOST', '0.0.0.0')

# Where Meta would send the webhooks: messaging-ingester (/webhook/{business_id}).
INGESTER_URL = os.getenv('INGESTER_URL', 'http://localhost:8002').rstrip('/')
INGESTER_TIMEOUT_SECONDS = 15

# The Graph API version in the fake API's paths (configuration-service's META_GRAPH_API_URL ends with it).
GRAPH_API_VERSION = 'v26.0'

# Where the load balancer serves this page (e.g. /whatsapp: it strips it before the request gets here), so
# the page's own links, files and API calls include it. Empty: served at /.
PUBLIC_PATH_PREFIX = os.getenv('MOCK_WHATSAPP_PUBLIC_PATH_PREFIX', '').rstrip('/')

DB_PATH = Path(os.getenv('MOCK_WHATSAPP_DB', BASE_DIR / 'mock_whatsapp.sqlite3'))

# The sample businesses' WhatsApp connections: the same as configuration-service's fixture
# sample_whatsapp_configurations.json (dummy credentials), plus a dummy WhatsApp Business Account id.
BUSINESSES_FILE = Path(os.getenv('MOCK_WHATSAPP_BUSINESSES', BASE_DIR / 'businesses.json'))


def businesses() -> list[dict]:
    return json.loads(BUSINESSES_FILE.read_text())


def business_by_phone_number_id(phone_number_id: str) -> dict | None:
    return next((b for b in businesses() if b['phone_number_id'] == phone_number_id), None)


def business_by_id(business_id: int) -> dict | None:
    return next((b for b in businesses() if b['business_id'] == business_id), None)
