"""Thin wrapper around the Ollama client, so routes deal with simple, typed errors."""

import httpx
from ollama import Client, ResponseError

from . import config


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
        _client = Client(host=config.OLLAMA_HOST, timeout=config.OLLAMA_TIMEOUT_SECONDS)
    return _client


def generate_reply(prompt: str) -> str:
    """One-off chat: sends SYSTEM_PROMPT + the user's prompt, returns the model's reply."""
    messages = [
        {'role': 'system', 'content': config.SYSTEM_PROMPT},
        {'role': 'user', 'content': prompt},
    ]
    try:
        response = get_client().chat(model=config.OLLAMA_MODEL, messages=messages)
    except ConnectionError as exc:  # raised by ollama when the server can't be reached
        raise LLMUnavailableError(f'Could not connect to Ollama at {config.OLLAMA_HOST}.') from exc
    except httpx.TimeoutException as exc:
        raise LLMTimeoutError(
            f'Ollama did not respond within {config.OLLAMA_TIMEOUT_SECONDS} seconds.'
        ) from exc
    except ResponseError as exc:
        raise LLMError(f'Ollama error ({exc.status_code}): {exc.error}') from exc
    return response.message.content or ''
