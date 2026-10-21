"""Helpers for the chat flow tests: a throwaway SQLite database with configuration-service's tables
(create_all of app/models.py: tests only, the real schema is Django's), factories for its rows, a
login token, and the fake LLM (ported from configuration-service's chat_app/tests/test_api.py).
"""

import copy
import json
import shutil
import tempfile
import unittest
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import jwt
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker

from app import config, create_app
from app.chat_api import get_sessions
from app.chat_flow.schedule import UNAVAILABLE_WEEK
from app.chat_flow.validators import default_detail_fields
from app.models import (
    FAQ,
    Base,
    BusinessConfiguration,
    BusinessUser,
    ChatConfiguration,
    ChatSession,
    OrderItem,
    Product,
    ScheduleItem,
    Service,
    ServiceProvider,
    UnansweredQuestion,
    WeeklyAvailability,
    service_service_providers,
)

TEST_SIGNING_KEY = 'test-jwt-signing-key-at-least-32-bytes-long'


def test_database() -> tuple[sessionmaker, callable]:
    """A new SQLite database file (one connection per session, like PostgreSQL) and a cleanup."""
    folder = tempfile.mkdtemp()
    engine = create_engine(f'sqlite:///{Path(folder) / "test.sqlite3"}', connect_args={'check_same_thread': False})

    # pysqlite's own transaction handling breaks SAVEPOINTs (begin_nested): let SQLAlchemy BEGIN.
    @event.listens_for(engine, 'connect')
    def _connect(dbapi_connection, record):
        dbapi_connection.isolation_level = None

    @event.listens_for(engine, 'begin')
    def _begin(connection):
        connection.exec_driver_sql('BEGIN')

    Base.metadata.create_all(engine)

    def cleanup():
        engine.dispose()
        shutil.rmtree(folder, ignore_errors=True)

    return sessionmaker(engine, expire_on_commit=False), cleanup


def access_token(user_id: int, key: str = TEST_SIGNING_KEY, **claims) -> str:
    """An access token like configuration-service's SimpleJWT ones (user_id as a string)."""
    now = int(datetime.now(UTC).timestamp())
    payload = {'token_type': 'access', 'exp': now + 900, 'iat': now, 'jti': 'test', 'user_id': str(user_id), **claims}
    return jwt.encode(payload, key, algorithm='HS256')


class Factory:
    """Creates rows (each in its own transaction), with Django's defaults."""

    def __init__(self, sessions: sessionmaker):
        self.sessions = sessions

    def add(self, *rows):
        with self.sessions.begin() as db:
            db.add_all(rows)
        return rows[0] if len(rows) == 1 else rows

    def business(self, business_name='Kopi Café', location='Singapore', description='', **fields):
        return self.add(BusinessConfiguration(business_name=business_name, location=location, description=description, **fields))

    def user(self, business=None, username='owner', is_active=True):
        return self.add(BusinessUser(username=username, is_active=is_active, business_id=business.id if business else None))

    def session(self, business, phone_number='', is_sandbox=True, chat_state_id='start', chat_state_data=None,
                chat_message_json=None, display_name='', last_chat_time=None):
        now = last_chat_time or datetime.now(UTC)
        return self.add(ChatSession(
            business_id=business.id, phone_number=phone_number, is_sandbox=is_sandbox, display_name=display_name,
            chat_state_id=chat_state_id, chat_state_data=copy.deepcopy(chat_state_data or {}),
            chat_message_json=copy.deepcopy(chat_message_json or []), created_time=now, last_chat_time=now,
        ))

    def chat_config(self, business, product_detail_fields=None, schedule_detail_fields=None, welcome_message='',
                    reply_style='friendly', custom_style=''):
        return self.add(ChatConfiguration(
            business_id=business.id,
            product_detail_fields=product_detail_fields or default_detail_fields(),
            schedule_detail_fields=schedule_detail_fields or default_detail_fields(),
            welcome_message=welcome_message, reply_style=reply_style, custom_style=custom_style,
        ))

    def product(self, business, name, price='1.80', total_quantity=100, description='', information='', is_active=True):
        return self.add(Product(
            business_id=business.id, name=name, price=Decimal(price), total_quantity=total_quantity,
            description=description, information=information, is_active=is_active,
        ))

    def faq(self, business, question, answer):
        return self.add(FAQ(business_id=business.id, question=question, answer=answer))

    def provider(self, business, name, is_active=True, description=''):
        return self.add(ServiceProvider(business_id=business.id, name=name, is_active=is_active, description=description))

    def service(self, business, name, providers=(), price='180.00', duration_minutes=60, buffer_minutes=0,
                start_interval_minutes=15, description='', information='', is_active=True):
        service = self.add(Service(
            business_id=business.id, name=name, price=Decimal(price), duration_minutes=duration_minutes,
            buffer_minutes=buffer_minutes, start_interval_minutes=start_interval_minutes, description=description,
            information=information, is_active=is_active,
        ))
        with self.sessions.begin() as db:
            for provider in providers:
                db.execute(service_service_providers.insert().values(service_id=service.id, serviceprovider_id=provider.id))
        return service

    def week(self, provider, monday: date, availability=UNAVAILABLE_WEEK):
        return self.add(WeeklyAvailability(service_provider_id=provider.id, week=monday, availability=availability))

    def order(self, business, order_data, order_status='pending_payment', chat_session=None, is_sandbox=False,
              created_time=None, payment_reference='0' * 32):
        now = created_time or datetime.now(UTC)
        return self.add(OrderItem(
            business_id=business.id, chat_session_id=chat_session.id if chat_session else None, is_sandbox=is_sandbox,
            order_data=copy.deepcopy(order_data), order_status=order_status, payment_reference=payment_reference,
            created_time=now, updated_time=now,
        ))

    def booking(self, business, service, provider, start_time, end_time, blocked_until, schedule_data,
                order_status='pending_payment', chat_session=None, is_sandbox=False, created_time=None):
        now = created_time or datetime.now(UTC)
        return self.add(ScheduleItem(
            business_id=business.id, chat_session_id=chat_session.id if chat_session else None, is_sandbox=is_sandbox,
            service_id=service.id if service else None, service_provider_id=provider.id if provider else None,
            start_time=start_time, end_time=end_time, blocked_until=blocked_until,
            schedule_data=copy.deepcopy(schedule_data), order_status=order_status, payment_reference='1' * 32,
            created_time=now, updated_time=now,
        ))


class DatabaseTestCase(unittest.TestCase):
    """A fresh database per test (`self.sessions`, `self.make`), and `get(Model, id)` / `all(Model)`."""

    def setUp(self):
        super().setUp()
        self.sessions, cleanup = test_database()
        self.addCleanup(cleanup)
        self.make = Factory(self.sessions)

    def get(self, model, pk):
        with self.sessions() as db:
            return db.get(model, pk)

    def all(self, model, *where):
        with self.sessions() as db:
            return list(db.scalars(select(model).where(*where).order_by(model.id)))


class ApiTestCase(DatabaseTestCase):
    """DatabaseTestCase + `self.client` (the app, on this database) and `self.login(user)`.

    payment-ingester's create-payment endpoint is not real in tests: `self.create_payment_stub`
    stands in for it (a fake link per item id); tests that need a failure re-patch
    `app.payment_client.create_payment` (or set the stub's side_effect to raise)."""

    def setUp(self):
        super().setUp()
        patcher = patch.object(config, 'JWT_SIGNING_KEY', TEST_SIGNING_KEY)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.create_payment_stub = MagicMock(
            side_effect=lambda kind, item_id, amount, payment_reference, customer, description=None: {
                'xendit_payment_id': f'pay_test_{item_id}',
                'payment_url': f'https://pay.xendit.co/test/{item_id}',
            }
        )
        payment_patcher = patch('app.payment_client.create_payment', self.create_payment_stub)
        payment_patcher.start()
        self.addCleanup(payment_patcher.stop)
        self.app = create_app()
        self.app.dependency_overrides[get_sessions] = lambda: self.sessions
        self.client = TestClient(self.app)

    def login(self, user):
        self.client.headers['Authorization'] = f'Bearer {access_token(user.id)}'


# --- The fake LLM (chat_app/tests/test_api.py) --------------------------------------------------

def fake_chat_response(content: str):
    """Shape of ollama's ChatResponse that the app reads: response.message.content."""
    return SimpleNamespace(message=SimpleNamespace(content=content))


NO_QUESTION = {'kind': 'none', 'question': None}
NO_INTENTS = {'intents': []}  # the router found nothing to do (e.g. a greeting)
ANY_ORDERS = {'kind': 'any', 'numbers': []}  # the order status extraction: "my orders"


def is_question_check(call_kwargs: dict) -> bool:
    """Whether a mocked ollama `chat` call is the flow's question check (flow.check_customer_question)."""
    properties = (call_kwargs.get('format') or {}).get('properties', {})
    return 'kind' in properties and 'question' in properties


def is_order_status_check(call_kwargs: dict) -> bool:
    """Whether a mocked ollama `chat` call is the order status extraction (flow.check_order_status)."""
    return 'numbers' in (call_kwargs.get('format') or {}).get('properties', {})


def is_router(call_kwargs: dict) -> bool:
    """Whether a mocked ollama `chat` call is the router (router.route_message)."""
    return 'intents' in (call_kwargs.get('format') or {}).get('properties', {})


def _route(intents) -> dict:
    return intents if isinstance(intents, dict) else {'intents': list(intents)}


def fake_ollama_chat(reply: str, extractions=(), question_check=NO_QUESTION, intents=NO_INTENTS, order_status=ANY_ORDERS):
    """A `side_effect` for the mocked ollama `chat`, for the chat flow.

    The router returns `intents` (a list of intents, or the whole JSON; default: none). The
    question check returns `question_check` (default: no question), the order status extraction
    `order_status` (default: any orders, no numbers). Other structured calls (with `format`, the
    order steps' extractions) return the next of `extractions` as JSON (`{}`, i.e. nothing found,
    once they run out). Other calls (the reply) return `reply`.
    """
    queue = list(extractions)

    def chat(**kwargs):
        if is_router(kwargs):
            return fake_chat_response(json.dumps(_route(intents)))
        if is_question_check(kwargs):
            return fake_chat_response(json.dumps(question_check))
        if is_order_status_check(kwargs):
            return fake_chat_response(json.dumps(order_status))
        if kwargs.get('format'):
            return fake_chat_response(json.dumps(queue.pop(0) if queue else {}))
        return fake_chat_response(reply)

    return chat


def with_question_check(responses, question_check=NO_QUESTION, intents=NO_INTENTS):
    """A `side_effect` that answers the router with `intents`, the question check with
    `question_check`, and every other call with the next of `responses` (for tests that script the
    calls one by one, e.g. tool calls)."""
    responses = iter(responses)

    def chat(**kwargs):
        if is_router(kwargs):
            return fake_chat_response(json.dumps(_route(intents)))
        if is_question_check(kwargs):
            return fake_chat_response(json.dumps(question_check))
        return next(responses)

    return chat


class FlowTestMixin:
    """Sends sandbox messages with the LLM mocked (call mock_llm(); set `self.session`, logged in)."""

    def mock_llm(self):
        self.ollama = MagicMock()
        patcher = patch('app.llm.get_client', return_value=self.ollama)
        patcher.start()
        self.addCleanup(patcher.stop)

    def send(self, message, *extractions, reply='OK!', intents=(), question_check=None, order_status=None):
        """Sends a customer message. The router finds `intents` (or returns that dict); the order
        steps' extraction calls return `extractions`, in order; the order status extraction
        returns `order_status` (default: any orders, no numbers). Refreshes `self.session`."""
        self.ollama.reset_mock()
        kwargs = {'question_check': question_check} if question_check else {}
        if order_status is not None:
            kwargs['order_status'] = order_status
        intents = intents if isinstance(intents, dict) else list(intents)  # a dict: the router's whole JSON
        self.ollama.chat.side_effect = fake_ollama_chat(reply, extractions, intents=intents, **kwargs)
        response = self.client.post(f'/api/chat/sandbox-sessions/{self.session.id}/messages/', json={'message': message})
        self.session = self.get(ChatSession, self.session.id)
        return response

    def calls(self, structured: bool):
        """The order steps' extractions (structured) or the reply calls; the router, the question
        check and the order status extraction are left out."""
        return [
            c.kwargs for c in self.ollama.chat.call_args_list
            if bool(c.kwargs.get('format')) == structured and not is_question_check(c.kwargs) and not is_router(c.kwargs)
            and not is_order_status_check(c.kwargs)
        ]

    def router_call(self):
        return next(c.kwargs for c in self.ollama.chat.call_args_list if is_router(c.kwargs))

    def reply_prompt(self) -> str:
        return self.calls(structured=False)[-1]['messages'][0]['content']


__all__ = [
    'ANY_ORDERS', 'NO_INTENTS', 'NO_QUESTION', 'ApiTestCase', 'DatabaseTestCase', 'Factory', 'FlowTestMixin',
    'UnansweredQuestion', 'access_token', 'fake_chat_response', 'fake_ollama_chat', 'is_order_status_check',
    'is_question_check', 'is_router', 'test_database', 'with_question_check',
]
