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

LLM_PROVIDERS = ('ollama', 'vertex_ai')
LLM_PROVIDER = os.getenv('LLM_PROVIDER', 'ollama').strip().lower()
if LLM_PROVIDER not in LLM_PROVIDERS:
    raise ValueError(f'LLM_PROVIDER must be one of {", ".join(LLM_PROVIDERS)}, not {LLM_PROVIDER!r}.')

# --- Ollama (local LLM server) ------------------------------------------------------------
OLLAMA_PORT = 11434
# In Docker, Ollama runs on the host: OLLAMA_HOST=http://host.docker.internal:11434.
OLLAMA_HOST = os.getenv('OLLAMA_HOST', f'http://localhost:{OLLAMA_PORT}')
OLLAMA_MODEL = 'qwen2.5:7b-instruct-q4_K_M'
# Local models can be slow, especially on the first request while the model loads.
OLLAMA_TIMEOUT_SECONDS = 120

# Vertex AI
GOOGLE_CLOUD_PROJECT = os.getenv('GOOGLE_CLOUD_PROJECT', '')
GOOGLE_CLOUD_LOCATION = os.getenv('GOOGLE_CLOUD_LOCATION', 'global')
VERTEX_AI_MODEL = 'gemini-3.5-flash-lite'
VERTEX_AI_TIMEOUT_SECONDS = 120
LLM_MODEL = os.getenv('LLM_MODEL') or (VERTEX_AI_MODEL if LLM_PROVIDER == 'vertex_ai' else OLLAMA_MODEL)

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
# The ack deadline, in seconds: the subscription's (docker-compose's pubsub-init creates it with
# this) and the client's leases, extended by this much while a message is handled. A message not
# acked in time (e.g. the worker died) is redelivered once it runs out.
PUBSUB_ACK_DEADLINE_SECONDS = int(os.getenv('PUBSUB_ACK_DEADLINE_SECONDS', '120'))
PUBSUB_PUBLISH_TIMEOUT_SECONDS = 10
# POST /consumer/test/nack and /consumer/test/no-ack (the user asked, to try the retry and
# dead-letter settings locally): off unless set; docker-compose turns them on.
PUBSUB_TEST_ENDPOINTS_ENABLED = os.getenv('PUBSUB_TEST_ENDPOINTS_ENABLED', '').lower() in ('1', 'true', 'yes')
PUBSUB_TEST_NACK_DELAY_SECONDS = 5  # the nack test waits this long before nacking

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

VERTEX_AI_OPTIONS = {
    'max_output_tokens': 1024,
}
VERTEX_AI_STRUCTURED_OPTIONS = VERTEX_AI_OPTIONS
VERTEX_AI_THINKING_LEVEL = 'MINIMAL'
# How many rounds of tool calls the reply step may make before it must answer.
MAX_TOOL_ROUNDS = 3
# How many times a turn runs when the chat keeps changing while it's worked out (ChatSession.version:
# another message, the business answering in the chat): then it gives up (409 / the message is nacked).
TURN_ATTEMPTS_MAX = 3

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

# --- Sending replies on WhatsApp (configuration-service's internal send endpoint) -------------
# The access token never leaves configuration-service: replies to WhatsApp messages are sent with
# POST {CONFIGURATION_SERVICE_URL}/internal/whatsapp/{business_id}/send/ (X-Internal-Api-Key).
CONFIGURATION_SERVICE_URL = os.getenv('CONFIGURATION_SERVICE_URL', 'http://localhost:8000/api').rstrip('/')
INTERNAL_API_KEY = os.getenv('INTERNAL_API_KEY', 'dev-internal-api-key')  # must equal configuration-service's
WHATSAPP_SEND_TIMEOUT_SECONDS = 20

# --- Payment links (payment-ingester's create endpoint) ---------------------------------------
# When the chat flow saves an order / booking, it asks payment-ingester (POST /payments,
# X-Internal-Api-Key) for the Xendit payment link the customer pays with; the link goes to the
# customer in the confirmation message, and Xendit's webhook (payment-ingester → Pub/Sub →
# processing-service) updates the order / booking's status.
PAYMENT_INGESTER_URL = os.getenv('PAYMENT_INGESTER_URL', 'http://localhost:8001')
PAYMENT_CREATE_TIMEOUT_SECONDS = int(os.getenv('PAYMENT_CREATE_TIMEOUT_SECONDS', '30'))

# --- CORS (the frontend calls the Chat Sandbox endpoint from the browser) ------------------
CORS_ALLOWED_ORIGINS = [
    origin.strip() for origin in os.getenv('CORS_ALLOWED_ORIGINS', 'http://localhost:5173').split(',') if origin.strip()
]

# --- API docs (FastAPI) -------------------------------------------------------------------
API_TITLE = 'Messaging Service API'
API_VERSION = 'v1'
