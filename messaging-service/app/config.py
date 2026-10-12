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

# --- The chat flow's LLM calls (app/chat_flow, the same as configuration-service's chat_app/llm.py) --
# Sampling hyperparameters sent as Ollama `options` on every chat flow request. The seed is fixed
# (with the rest unchanged) so the same prompt gives the same reply, for testing.
OLLAMA_OPTIONS = {
    'seed': 42,
    'temperature': 0.7,
    'num_predict': 512,  # max tokens in the reply
    'top_k': 40,
    'top_p': 0.9,
    'min_p': 0.0,
    'repeat_penalty': 1.1,
    'repeat_last_n': 64,
    'presence_penalty': 0.0,
    'frequency_penalty': 0.0,
    # Context window (system prompt + conversation + reply). The question check and the reply can
    # carry the business's FAQs and product details, which don't fit in 4096 for a large catalogue.
    'num_ctx': 8192,
}
# The extraction step (generate_structured) wants the most likely answer, not a creative one.
STRUCTURED_OPTIONS = {**OLLAMA_OPTIONS, 'temperature': 0.0}
# How many rounds of tool calls the reply step may make before it must answer.
MAX_TOOL_ROUNDS = 3

# --- PostgreSQL (configuration-service's database) -----------------------------------------
# The chat flow reads the business's products, services, FAQs and chats, and writes chat messages,
# orders, bookings and questions there. configuration-service (Django) owns the schema: this
# service never creates or alters tables (no migrations here). Same variable names as
# configuration-service; defaults are docker-compose's PostgreSQL as seen from the host (port 5433).
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

# --- Logins (configuration-service's SimpleJWT access tokens) ------------------------------
# The Chat Sandbox's endpoint takes the same `Authorization: Bearer <access token>` as
# configuration-service: HS256, signed with its JWT_SIGNING_KEY. Must be the same value; empty →
# every token is rejected (401).
JWT_SIGNING_KEY = os.getenv('JWT_SIGNING_KEY', '')
JWT_ALGORITHM = 'HS256'

# --- CORS (the frontend calls the Chat Sandbox endpoint from the browser) ------------------
CORS_ALLOWED_ORIGINS = [
    origin.strip() for origin in os.getenv('CORS_ALLOWED_ORIGINS', 'http://localhost:5173').split(',') if origin.strip()
]

# --- API docs (FastAPI) -------------------------------------------------------------------
API_TITLE = 'Messaging Service API'
API_VERSION = 'v1'
