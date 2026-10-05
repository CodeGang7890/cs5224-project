"""Service settings. Edit these constants to change ports, the model or the system prompt."""

# --- This service -------------------------------------------------------------------------
# 8000 is used by configuration-service (Django), so this service runs on 8001.
PORT = 8001

# --- Ollama (local LLM server) ------------------------------------------------------------
OLLAMA_PORT = 11434
OLLAMA_HOST = f'http://localhost:{OLLAMA_PORT}'
OLLAMA_MODEL = 'qwen2.5:7b-instruct-q4_K_M'
# Local models can be slow, especially on the first request while the model loads.
OLLAMA_TIMEOUT_SECONDS = 120

SYSTEM_PROMPT = (
    'You are a helpful assistant for Ansera Business Admin. '
    'Answer clearly and concisely.'
)

# --- /chat --------------------------------------------------------------------------------
CHAT_PROMPT_MAX_LENGTH = 4000

# --- API docs (FastAPI) -------------------------------------------------------------------
API_TITLE = 'Messaging Service API'
API_VERSION = 'v1'
