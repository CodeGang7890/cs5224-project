"""Service settings. Edit these constants to change ports, the model or the system prompt;
deployment-specific values (hosts, Pub/Sub) can also come from environment variables."""

import os

# --- This service -------------------------------------------------------------------------
# 8000 is configuration-service, 8001 is reserved for payment-ingester, 8002 is messaging-ingester
# and 8003 processing-service, so this service runs on 8004.
PORT = 8004
# Gunicorn worker processes (gunicorn.conf.py). Each one runs its own Pub/Sub consumer, and they
# share the subscription's messages.
WORKERS = int(os.getenv('WEB_CONCURRENCY', '2'))

# --- Ollama (local LLM server) ------------------------------------------------------------
OLLAMA_PORT = 11434
# In Docker, Ollama runs on the host: OLLAMA_HOST=http://host.docker.internal:11434.
OLLAMA_HOST = os.getenv('OLLAMA_HOST', f'http://localhost:{OLLAMA_PORT}')
OLLAMA_MODEL = 'qwen2.5:7b-instruct-q4_K_M'
# Local models can be slow, especially on the first request while the model loads.
OLLAMA_TIMEOUT_SECONDS = 120

SYSTEM_PROMPT = (
    'You are a helpful assistant for Ansera Business Admin. '
    'Answer clearly and concisely.'
)

# --- /chat --------------------------------------------------------------------------------
CHAT_PROMPT_MAX_LENGTH = 4000

# --- Pub/Sub consumer (customer messages from messaging-ingester) --------------------------
# A pull subscriber (streaming pull) on its own subscription to the ingester's topic. Off unless
# PUBSUB_CONSUMER_ENABLED is set, so `python run.py` and the tests need no Pub/Sub; docker-compose
# turns it on. With PUBSUB_EMULATOR_HOST set, the library talks to the local emulator, and the
# consumer creates the topic and its subscription itself (on Google Cloud: Terraform).
PUBSUB_CONSUMER_ENABLED = os.getenv('PUBSUB_CONSUMER_ENABLED', '').lower() in ('1', 'true', 'yes')
GCP_PROJECT_ID = os.getenv('GCP_PROJECT_ID', 'local-project')
PUBSUB_TOPIC = os.getenv('PUBSUB_TOPIC', 'whatsapp-inbound-messages')
PUBSUB_SUBSCRIPTION = os.getenv('PUBSUB_SUBSCRIPTION', 'messaging-service-inbound')
# At most this many messages are handled at once, per worker (Pub/Sub flow control).
PUBSUB_MAX_MESSAGES = int(os.getenv('PUBSUB_MAX_MESSAGES', '5'))
# Stand-in for the real work (the chat flow, later): each message waits this long before its ack.
PROCESSING_SECONDS = float(os.getenv('PROCESSING_SECONDS', '2'))

# --- API docs (FastAPI) -------------------------------------------------------------------
API_TITLE = 'Messaging Service API'
API_VERSION = 'v1'
