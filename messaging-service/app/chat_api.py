"""The chat endpoints that need the LLM, moved here from configuration-service's chat_app (the user
asked; removed there since). Same paths, status codes and bodies
(DRF's: app/drf.py), so callers only change the host:

- POST /api/chat/sandbox-sessions/{pk}/messages/: the Chat Sandbox (login required). Sends a message
  in one of your business's sandbox chats and returns the reply plus `debug`.
- POST /api/chat/sessions/messages/: a customer message (public, like a webhook): the reply.

Both run one turn of the chat flow (app/chat_flow/flow.py). Listing chats, sandbox sessions,
the chat settings and answering questions stay in configuration-service.
"""

from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker
from starlette.concurrency import run_in_threadpool

from . import llm
from .auth import authenticate
from .chat_flow import flow
from .chat_flow.validators import CHAT_MESSAGE_MAX_LENGTH
from .db import get_sessionmaker
from .drf import NO_BUSINESS_MESSAGE, OTHER_BUSINESS_MESSAGE, char_field, error, integer_field, json_object, regex_validator, validated
from .models import ChatSession

router = APIRouter(prefix='/api/chat', tags=['chat flow'])

NO_CHAT_SESSION_MESSAGE = 'No chat session found for this phone number at this business.'
NOT_SANDBOX_MESSAGE = 'This is a real customer chat session; only sandbox chat sessions can be used here.'
# chat_app.models
PHONE_NUMBER_MAX_LENGTH = 16
phone_number_validator = regex_validator(r'^\+[1-9]\d{6,14}$', 'Enter the phone number in international format, e.g. +6591234567.')


def get_sessions() -> sessionmaker:
    """The database sessions (a dependency, so tests can use their own)."""
    return get_sessionmaker()


class ChatMessage(BaseModel):
    message: str
    sent_by: str = Field(examples=['business-automated'])
    message_time: str = Field(description='ISO 8601 with a timezone.')


class CustomerMessageResponse(ChatMessage):
    messages: list[ChatMessage] = Field(
        description=(
            "Every message the assistant sent this turn, oldest first: on a chat's first message, the welcome "
            'message (if the business has one), then the reply (unless the welcome was the whole reply).'
        ),
    )


class SandboxMessageResponse(CustomerMessageResponse):
    debug: dict[str, Any] = Field(description="What happened inside the turn (not stored): see configuration-service's docs.")


def _message_body(description: str) -> dict:
    return {'requestBody': {'required': True, 'content': {'application/json': {'schema': {
        'type': 'object', 'required': ['message'],
        'properties': {'message': {'type': 'string', 'maxLength': CHAT_MESSAGE_MAX_LENGTH, 'description': description}},
    }}}}}


def _run_turn(sessions: sessionmaker, session_id: int, message: str) -> flow.TurnResult:
    """One turn of the chat flow; LLM failures → 502 / 503 / 504 (the customer message is kept)."""
    try:
        return flow.handle_customer_message(sessions, session_id, message)
    except llm.LLMUnavailableError as exc:
        raise error(503, str(exc)) from exc
    except llm.LLMTimeoutError as exc:
        raise error(504, str(exc)) from exc
    except llm.LLMError as exc:
        raise error(502, str(exc)) from exc


def _own_sandbox_session(request: Request, sessions: sessionmaker, pk: str) -> ChatSession:
    """The logged-in user's business's sandbox session `pk` (get_own_sandbox_session): 401 without
    a login, 403 without a business, 404 if it doesn't exist, 403 if it's another business's, 400
    if it's a real customer session."""
    user = authenticate(request, sessions)
    if user.business_id is None:
        raise error(403, NO_BUSINESS_MESSAGE)
    session = None
    if pk.isdigit():
        with sessions() as db:
            session = db.get(ChatSession, int(pk))
    if session is None:
        raise error(404, 'No chat session with this ID.')
    if session.business_id != user.business_id:
        raise error(403, OTHER_BUSINESS_MESSAGE)
    if not session.is_sandbox:
        raise error(400, NOT_SANDBOX_MESSAGE)
    return session


@router.post(
    '/sandbox-sessions/{pk}/messages/',
    summary='Send a message in a sandbox chat and get the reply',
    response_model=SandboxMessageResponse,
    openapi_extra=_message_body(f'Your message, as the pretend customer (max {CHAT_MESSAGE_MAX_LENGTH} characters).'),
    responses={
        400: {'description': 'Invalid message, or the session is a real customer session.'},
        401: {'description': 'Not logged in (configuration-service access token).'},
        403: {'description': "Another business's session, or your account has no business."},
        404: {'description': 'No chat session with this ID.'},
        502: {'description': 'Ollama returned an error (e.g. the model is not pulled).'},
        503: {'description': 'Ollama is not reachable.'},
        504: {'description': 'Ollama took too long to answer.'},
    },
)
async def sandbox_message(pk: str, request: Request, sessions: sessionmaker = Depends(get_sessions)) -> dict:
    """Appends the message (`sent_by: customer`), runs the chat flow (`chat_state_id` /
    `chat_state_data`), asks the LLM for a reply, appends it (`sent_by: business-automated`) and
    returns it, plus `debug`: what happened inside the turn, for the Chat Sandbox's debug panel. The
    message is kept if the LLM fails. Log in with configuration-service (`Authorization: Bearer`).
    """
    session = await run_in_threadpool(_own_sandbox_session, request, sessions, pk)
    data = await json_object(request)
    body = validated({'message': char_field(data, 'message', CHAT_MESSAGE_MAX_LENGTH)})
    result = await run_in_threadpool(_run_turn, sessions, session.id, body['message'])
    return {**result.reply, 'messages': result.messages, 'debug': result.debug}


@router.post(
    '/sessions/messages/',
    summary='Send a customer message and get the reply',
    response_model=CustomerMessageResponse,
    openapi_extra={'requestBody': {'required': True, 'content': {'application/json': {'schema': {
        'type': 'object', 'required': ['business_id', 'phone_number', 'message'],
        'properties': {
            'business_id': {'type': 'integer', 'minimum': 1},
            'phone_number': {'type': 'string', 'maxLength': PHONE_NUMBER_MAX_LENGTH, 'examples': ['+6591234567']},
            'message': {'type': 'string', 'maxLength': CHAT_MESSAGE_MAX_LENGTH},
        },
    }}}}},
    responses={
        400: {'description': 'Invalid business ID, phone number or message.'},
        404: {'description': 'No chat session for this phone number at this business.'},
        502: {'description': 'Ollama returned an error (e.g. the model is not pulled).'},
        503: {'description': 'Ollama is not reachable.'},
        504: {'description': 'Ollama took too long to answer.'},
    },
)
async def customer_message(request: Request, sessions: sessionmaker = Depends(get_sessions)) -> dict:
    """Finds the chat session for `business_id` + `phone_number` (a real one), appends the message
    (`sent_by: customer`), runs the chat flow, appends the reply (`sent_by: business-automated`)
    and returns it. Public, like a webhook. The customer message is kept even if the LLM fails.
    """
    data = await json_object(request)
    body = validated({
        'business_id': integer_field(data, 'business_id', min_value=1),
        'phone_number': char_field(data, 'phone_number', PHONE_NUMBER_MAX_LENGTH, [phone_number_validator]),
        'message': char_field(data, 'message', CHAT_MESSAGE_MAX_LENGTH),
    })

    def find_session() -> ChatSession | None:
        with sessions() as db:
            return db.scalars(
                select(ChatSession)
                .where(
                    ChatSession.business_id == body['business_id'],
                    ChatSession.phone_number == body['phone_number'],
                    ChatSession.is_sandbox.is_(False),
                )
                .order_by(ChatSession.id)
            ).first()

    session = await run_in_threadpool(find_session)
    if session is None:
        raise error(404, NO_CHAT_SESSION_MESSAGE)
    result = await run_in_threadpool(_run_turn, sessions, session.id, body['message'])
    return {**result.reply, 'messages': result.messages}
