"""Thin wrapper around the Ollama client, so callers deal with simple, typed errors.

- generate_reply: the one-off chat (POST /chat).
- generate_structured / generate_chat_reply: the two kinds of call the chat flow (app/chat_flow)
  makes, as in configuration-service's chat_app/llm.py (same model and options: config.py).
"""

import json

import httpx
from ollama import Client, ResponseError

from . import config


class LLMError(Exception):
    """Ollama answered with an error (e.g. the model isn't pulled)."""


class LLMUnavailableError(LLMError):
    """Ollama couldn't be reached."""


class LLMTimeoutError(LLMError):
    """Ollama didn't answer within OLLAMA_TIMEOUT_SECONDS."""


def _vertex_ai():
    if config.LLM_PROVIDER != 'vertex_ai':
        return None
    from . import llm_vertex
    return llm_vertex


_client: Client | None = None


def get_client() -> Client:
    """Shared Ollama client, created on first use."""
    global _client
    if _client is None:
        _client = Client(host=config.OLLAMA_HOST, timeout=config.OLLAMA_TIMEOUT_SECONDS)
    return _client


def generate_reply(prompt: str) -> str:
    """One-off chat: sends SYSTEM_PROMPT + the user's prompt, returns the model's reply."""
    if vertex_ai := _vertex_ai():
        return vertex_ai.generate_reply(prompt)
    messages = [
        {'role': 'system', 'content': config.SYSTEM_PROMPT},
        {'role': 'user', 'content': prompt},
    ]
    return _chat(messages, options=None).content or ''


def generate_structured(system_prompt: str, history: list[dict], schema: dict) -> dict:
    """Asks for a JSON object matching `schema` (Ollama structured output), about the conversation.

    `history` is the chat as `{role: user|assistant, content}` messages, oldest first.
    """
    if vertex_ai := _vertex_ai():
        return vertex_ai.generate_structured(system_prompt, history, schema)
    messages = [{'role': 'system', 'content': system_prompt}, *history]
    message = _chat(messages, format=schema, options=config.STRUCTURED_OPTIONS)
    try:
        data = json.loads(message.content or '')
    except json.JSONDecodeError as exc:
        raise LLMError('The model did not return valid JSON.') from exc
    if not isinstance(data, dict):
        raise LLMError('The model did not return a JSON object.')
    return data


def generate_chat_reply(system_prompt: str, history: list[dict], toolbox=None) -> str:
    """The assistant's next chat message. It may first call the toolbox's (read-only) tools."""
    if vertex_ai := _vertex_ai():
        return vertex_ai.generate_chat_reply(system_prompt, history, toolbox)
    messages = [{'role': 'system', 'content': system_prompt}, *history]
    for _ in range(config.MAX_TOOL_ROUNDS):
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
    """Sends the messages to Ollama and returns the reply message, mapping failures to LLMError
    types. The chat flow's calls use config.OLLAMA_OPTIONS unless given others; `options=None`
    (POST /chat) sends none, as before."""
    kwargs.setdefault('options', config.OLLAMA_OPTIONS)
    if kwargs['options'] is None:
        del kwargs['options']
    try:
        response = get_client().chat(model=config.LLM_MODEL, messages=messages, **kwargs)
    except ConnectionError as exc:  # raised by ollama when the server can't be reached
        raise LLMUnavailableError(f'Could not connect to Ollama at {config.OLLAMA_HOST}.') from exc
    except httpx.TimeoutException as exc:
        raise LLMTimeoutError(
            f'Ollama did not respond within {config.OLLAMA_TIMEOUT_SECONDS} seconds.'
        ) from exc
    except ResponseError as exc:
        raise LLMError(f'Ollama error ({exc.status_code}): {exc.error}') from exc
    return response.message
