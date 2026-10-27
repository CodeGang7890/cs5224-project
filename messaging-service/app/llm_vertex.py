"""Gemini on Vertex AI: the backend of app/llm.py when LLM_PROVIDER=vertex_ai.

The same three calls as the Ollama backend, with the same errors (app/llm.py), using the google-genai
SDK as vertex-ai-demo does: `genai.Client(vertexai=True, project, location)`, authenticated with
Application Default Credentials (on Cloud Run, the service account; no API key).

- Messages: the system prompt becomes `system_instruction`; `user` stays `user` and `assistant`
  becomes `model` (Gemini's name); consecutive messages of one role are sent as one turn.
- Structured output: `response_mime_type='application/json'` with the JSON schema as
  `response_json_schema` (the chat flow's schemas use anyOf / null, which that field accepts).
- Tools: the toolbox's specs (Ollama's format) become function declarations. The model's function calls
  are run by the toolbox (read-only), and their results go back as function responses.
"""

import json
from functools import lru_cache

import httpx
from google import genai
from google.auth import exceptions as auth_exceptions
from google.genai import errors, types

from . import config
from .llm import LLMError, LLMTimeoutError, LLMUnavailableError

# Gemini's roles for the chat history's.
_ROLES = {'user': 'user', 'assistant': 'model'}
# HTTP statuses that mean "try again later" rather than a bad request.
_UNAVAILABLE_STATUSES = {429, 500, 502, 503, 504}


@lru_cache
def get_client() -> genai.Client:
    """Shared Vertex AI client, created on first use."""
    if not config.GOOGLE_CLOUD_PROJECT:
        raise LLMUnavailableError('Vertex AI is not configured: set GOOGLE_CLOUD_PROJECT.')
    return genai.Client(
        vertexai=True,
        project=config.GOOGLE_CLOUD_PROJECT,
        location=config.GOOGLE_CLOUD_LOCATION,
        http_options=types.HttpOptions(timeout=config.VERTEX_AI_TIMEOUT_SECONDS * 1000),  # milliseconds
    )


def generate_reply(prompt: str) -> str:
    """One-off chat: SYSTEM_PROMPT + the user's prompt, no options (like the Ollama backend)."""
    response = _generate(config.SYSTEM_PROMPT, _contents([{'role': 'user', 'content': prompt}]), options={})
    return _text(response)


def generate_structured(system_prompt: str, history: list[dict], schema: dict) -> dict:
    """A JSON object matching `schema`, about the conversation."""
    response = _generate(
        system_prompt,
        _contents(history),
        options=config.VERTEX_AI_STRUCTURED_OPTIONS,
        response_mime_type='application/json',
        response_json_schema=schema,
    )
    try:
        data = json.loads(_text(response))
    except json.JSONDecodeError as exc:
        raise LLMError('The model did not return valid JSON.') from exc
    if not isinstance(data, dict):
        raise LLMError('The model did not return a JSON object.')
    return data


def generate_chat_reply(system_prompt: str, history: list[dict], toolbox=None) -> str:
    """The assistant's next chat message. It may first call the toolbox's (read-only) tools."""
    contents = _contents(history)
    if contents and contents[-1].role == 'model':
        # Gemini 3.5 Flash-Lite requires the final input turn to be from the user. This happens
        # when the business's welcome message was sent immediately before the generated reply.
        sent_message = '\n'.join(part.text for part in contents[-1].parts if part.text)
        system_prompt += f'\n\nThe assistant already sent this message to the customer: {sent_message}'
        contents.pop()
    tools = _tools(toolbox.specs) if toolbox else None
    for _ in range(config.MAX_TOOL_ROUNDS):
        response = _generate(system_prompt, contents, options=config.VERTEX_AI_OPTIONS, tools=tools)
        calls = response.function_calls
        if not calls:
            return _text(response)
        contents.append(response.candidates[0].content)
        contents.append(types.Content(role='user', parts=[
            types.Part.from_function_response(name=call.name, response=_tool_result(toolbox.run(call.name, call.args)))
            for call in calls
        ]))
    # Out of tool rounds: answer with what it has. The tools stay declared (the history has calls to
    # them), but the model may not call any.
    response = _generate(
        system_prompt,
        contents,
        options=config.VERTEX_AI_OPTIONS,
        tools=tools,
        tool_config=types.ToolConfig(function_calling_config=types.FunctionCallingConfig(mode='NONE')) if tools else None,
    )
    return _text(response)


def _contents(history: list[dict]) -> list[types.Content]:
    """The chat history as Gemini contents: one turn per run of messages from the same side."""
    contents: list[types.Content] = []
    for message in history:
        text = message.get('content') or ''
        if not text:
            continue  # Gemini rejects empty parts
        role = _ROLES.get(message.get('role'), 'user')
        if contents and contents[-1].role == role:
            contents[-1].parts.append(types.Part(text=text))
        else:
            contents.append(types.Content(role=role, parts=[types.Part(text=text)]))
    return contents


def _tools(specs: list[dict]) -> list[types.Tool]:
    """The toolbox's specs ({type: function, function: {name, description, parameters}}) for Gemini.
    A tool without arguments is declared without parameters (an empty object schema isn't needed)."""
    declarations = []
    for spec in specs:
        function = spec['function']
        parameters = function.get('parameters') or {}
        declarations.append(types.FunctionDeclaration(
            name=function['name'],
            description=function.get('description', ''),
            parameters_json_schema=parameters if parameters.get('properties') else None,
        ))
    return [types.Tool(function_declarations=declarations)]


def _tool_result(text: str) -> dict:
    """A tool's JSON text as a function response, which must be an object: {"result": <the value>}."""
    try:
        return {'result': json.loads(text)}
    except json.JSONDecodeError:
        return {'result': text}


def _text(response) -> str:
    """The reply's text; empty when there is none (e.g. the answer was blocked)."""
    try:
        return response.text or ''
    except ValueError:
        return ''


def _generate(system_prompt: str, contents: list[types.Content], options: dict, **config_fields):
    """Calls the model, mapping failures to the LLMError types."""
    if config.LLM_MODEL.startswith('gemini-3'):
        config_fields['thinking_config'] = types.ThinkingConfig(thinking_level=config.VERTEX_AI_THINKING_LEVEL)
    generation_config = types.GenerateContentConfig(system_instruction=system_prompt, **options, **config_fields)
    try:
        return get_client().models.generate_content(model=config.LLM_MODEL, contents=contents, config=generation_config)
    except LLMError:
        raise
    except httpx.TimeoutException as exc:
        raise LLMTimeoutError(f'Vertex AI did not respond within {config.VERTEX_AI_TIMEOUT_SECONDS} seconds.') from exc
    except (httpx.TransportError, auth_exceptions.GoogleAuthError) as exc:
        raise LLMUnavailableError(f'Could not reach Vertex AI ({type(exc).__name__}).') from exc
    except errors.APIError as exc:
        if exc.code in _UNAVAILABLE_STATUSES:
            raise LLMUnavailableError(f'Vertex AI is unavailable ({exc.code}): {exc.message}') from exc
        raise LLMError(f'Vertex AI error ({exc.code}): {exc.message}') from exc
