"""Thin wrapper around the Ollama client, so callers deal with simple, typed errors.

- generate_reply: the one-off chat (POST /api/chat/), moved from ../messaging-service.
- generate_structured / generate_chat_reply: the two kinds of call the chat flow (flow.py) makes.

Everything is hardcoded here on purpose: edit these constants to change the model, system prompt
or sampling hyperparameters. The prompts for customer chats live in prompts.py.
"""

import json

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

# The extraction step (generate_structured) wants the most likely answer, not a creative one.
STRUCTURED_OPTIONS = {**OLLAMA_OPTIONS, 'temperature': 0.0}

# How many rounds of tool calls the reply step may make before it must answer.
MAX_TOOL_ROUNDS = 3


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
    return _chat(messages).content or ''


def generate_structured(system_prompt: str, history: list[dict], schema: dict) -> dict:
    """Asks for a JSON object matching `schema` (Ollama structured output), about the conversation.

    `history` is the chat as `{role: user|assistant, content}` messages, oldest first.
    """
    messages = [{'role': 'system', 'content': system_prompt}, *history]
    message = _chat(messages, format=schema, options=STRUCTURED_OPTIONS)
    try:
        data = json.loads(message.content or '')
    except json.JSONDecodeError as exc:
        raise LLMError('The model did not return valid JSON.') from exc
    if not isinstance(data, dict):
        raise LLMError('The model did not return a JSON object.')
    return data


def generate_chat_reply(system_prompt: str, history: list[dict], toolbox=None) -> str:
    """The assistant's next chat message. It may first call the toolbox's (read-only) tools."""
    messages = [{'role': 'system', 'content': system_prompt}, *history]
    for _ in range(MAX_TOOL_ROUNDS):
        message = _chat(messages, tools=toolbox.specs if toolbox else None)
        tool_calls = getattr(message, 'tool_calls', None)
        if not tool_calls:
            return message.content or ''
        messages.append(message)
        for call in tool_calls:
            messages.append({
                'role': 'tool',
                'tool_name': call.function.name,
                'content': toolbox.run(call.function.name, call.function.arguments),
            })
    # Out of tool rounds: answer with what it has.
    return _chat(messages).content or ''


def _chat(messages: list, **kwargs):
    """Sends the messages to Ollama and returns the reply message, mapping failures to LLMError types."""
    kwargs.setdefault('options', OLLAMA_OPTIONS)
    try:
        response = get_client().chat(model=OLLAMA_MODEL, messages=messages, **kwargs)
    except ConnectionError as exc:  # raised by ollama when the server can't be reached
        raise LLMUnavailableError(f'Could not connect to Ollama at {OLLAMA_HOST}.') from exc
    except httpx.TimeoutException as exc:
        raise LLMTimeoutError(
            f'Ollama did not respond within {OLLAMA_TIMEOUT_SECONDS} seconds.'
        ) from exc
    except ResponseError as exc:
        raise LLMError(f'Ollama error ({exc.status_code}): {exc.error}') from exc
    return response.message
