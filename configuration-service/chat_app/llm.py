"""Thin wrapper around the Ollama client, so views deal with simple, typed errors.

Temporary home for the chat feature from ../messaging-service until that service has its own
database. Everything is hardcoded here on purpose: edit these constants to change the model,
system prompt or sampling hyperparameters.
"""

import httpx
from ollama import Client, ResponseError

# --- Ollama (local LLM server) ------------------------------------------------------------
OLLAMA_HOST = 'http://localhost:11434'
OLLAMA_MODEL = 'qwen2.5:7b-instruct-q4_K_M'
# Local models can be slow, especially on the first request while the model loads.
OLLAMA_TIMEOUT_SECONDS = 120

SYSTEM_PROMPT = (
    'You are a helpful assistant for Ansera Business Admin. '
    'Answer clearly and concisely.'
)

# Sampling hyperparameters sent as Ollama `options` on every request.
# The seed is fixed (with the rest unchanged) so the same prompt gives the same reply, for testing.
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
    'num_ctx': 4096,  # context window (system prompt + user prompt + reply)
}

CHAT_PROMPT_MAX_LENGTH = 4000


class LLMError(Exception):
    """Ollama answered with an error (e.g. the model isn't pulled)."""


class LLMUnavailableError(LLMError):
    """Ollama couldn't be reached."""


class LLMTimeoutError(LLMError):
    """Ollama didn't answer within OLLAMA_TIMEOUT_SECONDS."""


_client: Client | None = None


def get_client() -> Client:
    """Shared Ollama client, created on first use."""
    global _client
    if _client is None:
        _client = Client(host=OLLAMA_HOST, timeout=OLLAMA_TIMEOUT_SECONDS)
    return _client


def generate_reply(prompt: str) -> str:
    """One-off chat: sends SYSTEM_PROMPT + the user's prompt, returns the model's reply."""
    messages = [
        {'role': 'system', 'content': SYSTEM_PROMPT},
        {'role': 'user', 'content': prompt},
    ]
    try:
        response = get_client().chat(model=OLLAMA_MODEL, messages=messages, options=OLLAMA_OPTIONS)
    except ConnectionError as exc:  # raised by ollama when the server can't be reached
        raise LLMUnavailableError(f'Could not connect to Ollama at {OLLAMA_HOST}.') from exc
    except httpx.TimeoutException as exc:
        raise LLMTimeoutError(
            f'Ollama did not respond within {OLLAMA_TIMEOUT_SECONDS} seconds.'
        ) from exc
    except ResponseError as exc:
        raise LLMError(f'Ollama error ({exc.status_code}): {exc.error}') from exc
    return response.message.content or ''
