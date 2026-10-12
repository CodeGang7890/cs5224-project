"""Ported from configuration-service's chat_app/tests/test_api.py: the customer message endpoint
(CustomerMessageView) and the sandbox message endpoint (SandboxChatMessageView). Plus the exact
bodies Django returns (checked against configuration-service with its test client): SimpleJWT's
401s, the 400 / 403 / 404 details, DRF's validation errors and the LLM errors (502 / 503 / 504)."""

import time
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import httpx
import jwt
from ollama import ResponseError

from app import config
from app.chat_flow.validators import validate_chat_messages
from app.models import ChatSession

from .chat_helpers import TEST_SIGNING_KEY, ApiTestCase, access_token, fake_ollama_chat
from .test_chat_validators import VALID_MESSAGES

SANDBOX_KEYS = {'message', 'sent_by', 'message_time', 'messages', 'debug'}
DEBUG_KEYS = {
    'before', 'after', 'route', 'steps', 'stop_reason', 'finished', 'confirmation', 'order_id', 'booking_id', 'missing',
    'issues', 'question_check', 'order_status', 'welcome_message', 'reply_kind', 'reply_system_prompt', 'tool_calls',
}


class CustomerMessageAPITests(ApiTestCase):
    url = '/api/chat/sessions/messages/'

    def setUp(self):
        super().setUp()
        self.cafe = self.make.business('Kopi Café', description='Local kopi and toast.', location='Tiong Bahru')
        self.florist = self.make.business('Florist')
        self.created = datetime.now(UTC) - timedelta(days=1)
        self.session = self.make.session(
            self.cafe,
            phone_number='+6591234567',
            is_sandbox=False,
            last_chat_time=self.created,  # and created_time
            chat_message_json=list(VALID_MESSAGES),
            chat_state_id='product_selection',
        )
        # Replace the Ollama client so tests never need a running model.
        self.ollama = MagicMock()
        self.ollama.chat.side_effect = fake_ollama_chat('Yes, we are open until 6pm!')
        patcher = patch('app.llm.get_client', return_value=self.ollama)
        patcher.start()
        self.addCleanup(patcher.stop)

    def send(self, **overrides):
        body = {'business_id': self.cafe.pk, 'phone_number': '+6591234567', 'message': 'Are you open today?'}
        return self.client.post(self.url, json={**body, **overrides})

    def refreshed(self):
        return self.get(ChatSession, self.session.id)

    def test_appends_both_messages_and_returns_reply(self):
        response = self.send()
        self.assertEqual(response.status_code, 200)
        reply = response.json()
        self.assertEqual(set(reply), {'message', 'sent_by', 'message_time', 'messages'})
        self.assertEqual(reply.pop('messages'), [reply])  # no welcome message: just the reply
        self.assertEqual(reply['message'], 'Yes, we are open until 6pm!')
        self.assertEqual(reply['sent_by'], 'business-automated')

        self.session = self.refreshed()
        messages = self.session.chat_message_json
        self.assertEqual(messages[:len(VALID_MESSAGES)], VALID_MESSAGES)  # history kept
        customer, bot = messages[len(VALID_MESSAGES):]
        self.assertEqual((customer['message'], customer['sent_by']), ('Are you open today?', 'customer'))
        self.assertEqual(bot, reply)
        validate_chat_messages(messages)  # stored in the agreed format, in time order

        self.assertGreater(self.session.last_chat_time, self.created)
        self.assertEqual(self.session.last_chat_time.isoformat(), bot['message_time'])
        self.assertEqual(self.session.created_time, self.created)
        self.assertEqual(self.session.chat_state_id, 'product_selection')  # nothing chosen yet: still there

    def test_llm_gets_business_system_prompt_and_conversation(self):
        self.send(message='  Do you have kaya toast?  ')
        reply_call = self.ollama.chat.call_args.kwargs  # the reply is the last call
        messages = reply_call['messages']
        self.assertEqual(messages[0]['role'], 'system')
        for part in ('Kopi Café', 'Local kopi and toast.', 'Tiong Bahru', 'Product selection'):
            self.assertIn(part, messages[0]['content'])
        # The whole conversation: the customer is `user`, the business (bot or person) `assistant`.
        self.assertEqual(
            [m['role'] for m in messages[1:]], ['user', 'assistant', 'assistant', 'user']
        )
        self.assertEqual(messages[-1], {'role': 'user', 'content': 'Do you have kaya toast?'})
        self.assertEqual(reply_call['options'], config.OLLAMA_OPTIONS)
        self.assertNotIn('format', reply_call)

    def test_no_login_needed(self):
        # The customer isn't a logged-in user (it will be a webhook).
        self.assertEqual(self.send().status_code, 200)

    def test_unknown_session_returns_404(self):
        self.make.session(self.florist, phone_number='+6591234567', is_sandbox=True)
        cases = {
            'unknown phone number': {'phone_number': '+6599999999'},
            'another business': {'business_id': self.florist.pk},
            'unknown business': {'business_id': 99999},
        }
        for label, overrides in cases.items():
            with self.subTest(label):
                response = self.send(**overrides)
                self.assertEqual(response.status_code, 404)
                self.assertEqual(response.json(), {'detail': 'No chat session found for this phone number at this business.'})
        self.ollama.chat.assert_not_called()

    def test_invalid_input_returns_400(self):
        cases = {
            'missing business_id': ({'business_id': None}, 'business_id'),
            'business_id not a number': ({'business_id': 'abc'}, 'business_id'),
            'invalid phone number': ({'phone_number': '91234567'}, 'phone_number'),
            'blank message': ({'message': '   '}, 'message'),
            'message too long': ({'message': 'x' * 4097}, 'message'),
        }
        for label, (overrides, field) in cases.items():
            with self.subTest(label):
                response = self.send(**overrides)
                self.assertEqual(response.status_code, 400)
                self.assertIn(field, response.json())
        self.ollama.chat.assert_not_called()
        self.assertEqual(self.refreshed().chat_message_json, VALID_MESSAGES)

    def test_llm_failure_keeps_customer_message(self):
        self.ollama.chat.side_effect = ConnectionError('Failed to connect to Ollama.')
        response = self.send()
        self.assertEqual(response.status_code, 503)
        self.session = self.refreshed()
        self.assertEqual(len(self.session.chat_message_json), len(VALID_MESSAGES) + 1)
        self.assertEqual(self.session.chat_message_json[-1]['sent_by'], 'customer')
        self.assertGreater(self.session.last_chat_time, self.created)

    # --- Not in Django's tests: the exact bodies Django returns -----------------------------

    def test_validation_error_bodies(self):
        cases = {
            'null business_id': ({'business_id': None}, {'business_id': ['This field may not be null.']}),
            'business_id not a number': ({'business_id': 'abc'}, {'business_id': ['A valid integer is required.']}),
            'business_id zero': ({'business_id': 0}, {'business_id': ['Ensure this value is greater than or equal to 1.']}),
            'business_id a fraction': ({'business_id': 1.5}, {'business_id': ['A valid integer is required.']}),
            'business_id a bool': ({'business_id': True}, {'business_id': ['A valid integer is required.']}),
            'invalid phone number': (
                {'phone_number': '91234567'}, {'phone_number': ['Enter the phone number in international format, e.g. +6591234567.']},
            ),
            'phone number too long': ({'phone_number': '+65912345678901234'}, {'phone_number': [
                'Enter the phone number in international format, e.g. +6591234567.', 'Ensure this field has no more than 16 characters.',
            ]}),
            'blank message': ({'message': '   '}, {'message': ['This field may not be blank.']}),
            'message too long': ({'message': 'x' * 4097}, {'message': ['Ensure this field has no more than 4096 characters.']}),
        }
        for label, (overrides, body) in cases.items():
            with self.subTest(label):
                response = self.send(**overrides)
                self.assertEqual((response.status_code, response.json()), (400, body))
        response = self.client.post(self.url, json={})
        self.assertEqual((response.status_code, response.json()), (400, {
            'business_id': ['This field is required.'], 'phone_number': ['This field is required.'], 'message': ['This field is required.'],
        }))
        self.ollama.chat.assert_not_called()

    def test_llm_error_mapping(self):
        cases = {
            'unreachable': (ConnectionError('x'), 503, f'Could not connect to Ollama at {config.OLLAMA_HOST}.'),
            'timeout': (httpx.ReadTimeout('t'), 504, f'Ollama did not respond within {config.OLLAMA_TIMEOUT_SECONDS} seconds.'),
            'model error': (ResponseError('model "x" not found', 404), 502, 'Ollama error (404): model "x" not found'),
        }
        for label, (exc, status_code, detail) in cases.items():
            with self.subTest(label):
                self.ollama.chat.side_effect = exc
                response = self.send()
                self.assertEqual((response.status_code, response.json()), (status_code, {'detail': detail}))
        # Each failed turn kept its customer message.
        self.assertEqual([m['sent_by'] for m in self.refreshed().chat_message_json[len(VALID_MESSAGES):]], ['customer'] * 3)


class SandboxChatMessageAPITests(ApiTestCase):
    @staticmethod
    def url(session):
        return f'/api/chat/sandbox-sessions/{session.pk}/messages/'

    def setUp(self):
        super().setUp()
        self.cafe = self.make.business('Kopi Café', location='Tiong Bahru')
        self.florist = self.make.business('Florist')
        self.cafe_user = self.make.user(self.cafe, username='cafe')
        self.no_business_user = self.make.user(username='nobiz')
        self.sandbox = self.make.session(self.cafe, is_sandbox=True)
        self.other_sandbox = self.make.session(self.cafe, is_sandbox=True)
        self.ollama = MagicMock()
        self.ollama.chat.side_effect = fake_ollama_chat('Hello from the café!')
        patcher = patch('app.llm.get_client', return_value=self.ollama)
        patcher.start()
        self.addCleanup(patcher.stop)

    def send(self, session, message='Hi there'):
        return self.client.post(self.url(session), json={'message': message})

    def refreshed(self, session):
        return self.get(ChatSession, session.id)

    def test_requires_authentication(self):
        self.assertEqual(self.send(self.sandbox).status_code, 401)
        self.ollama.chat.assert_not_called()

    def test_user_without_business_gets_403(self):
        self.login(self.no_business_user)
        self.assertEqual(self.send(self.sandbox).status_code, 403)

    def test_appends_messages_and_returns_reply(self):
        self.login(self.cafe_user)
        response = self.send(self.sandbox, '  Are you open?  ')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['message'], 'Hello from the café!')
        self.assertEqual(response.json()['sent_by'], 'business-automated')
        self.sandbox = self.refreshed(self.sandbox)
        self.assertEqual(
            [(m['sent_by'], m['message']) for m in self.sandbox.chat_message_json],
            [('customer', 'Are you open?'), ('business-automated', 'Hello from the café!')],
        )
        validate_chat_messages(self.sandbox.chat_message_json)
        self.assertEqual(self.sandbox.chat_state_id, 'start')  # no wish to order: still at the start
        self.assertIn('Kopi Café', self.ollama.chat.call_args.kwargs['messages'][0]['content'])

    def test_sessions_are_independent(self):
        self.login(self.cafe_user)
        self.send(self.sandbox, 'first chat')
        self.send(self.other_sandbox, 'second chat')
        self.sandbox = self.refreshed(self.sandbox)
        self.other_sandbox = self.refreshed(self.other_sandbox)
        self.assertEqual(self.sandbox.chat_message_json[0]['message'], 'first chat')
        self.assertEqual(self.other_sandbox.chat_message_json[0]['message'], 'second chat')
        self.assertEqual(len(self.sandbox.chat_message_json), 2)

    def test_real_session_returns_400(self):
        real = self.make.session(self.cafe, phone_number='+6591234567', is_sandbox=False)
        self.login(self.cafe_user)
        self.assertEqual(self.send(real).status_code, 400)
        self.assertEqual(self.refreshed(real).chat_message_json, [])

    def test_other_business_session_returns_403(self):
        florist_sandbox = self.make.session(self.florist, is_sandbox=True)
        self.login(self.cafe_user)
        self.assertEqual(self.send(florist_sandbox).status_code, 403)
        self.assertEqual(self.refreshed(florist_sandbox).chat_message_json, [])

    def test_unknown_session_returns_404(self):
        self.login(self.cafe_user)
        response = self.client.post('/api/chat/sandbox-sessions/99999/messages/', json={'message': 'hi'})
        self.assertEqual(response.status_code, 404)

    def test_invalid_message_returns_400(self):
        self.login(self.cafe_user)
        for message in ('', '   ', 'x' * 4097):
            with self.subTest(length=len(message)):
                response = self.send(self.sandbox, message)
                self.assertEqual(response.status_code, 400)
                self.assertIn('message', response.json())
        self.ollama.chat.assert_not_called()

    def test_llm_failure_keeps_message(self):
        self.ollama.chat.side_effect = ConnectionError('down')
        self.login(self.cafe_user)
        self.assertEqual(self.send(self.sandbox).status_code, 503)
        self.assertEqual([m['sent_by'] for m in self.refreshed(self.sandbox).chat_message_json], ['customer'])

    # --- Not in Django's tests: the exact bodies Django returns -----------------------------

    def test_response_shape(self):
        self.login(self.cafe_user)
        body = self.send(self.sandbox).json()
        self.assertEqual(set(body), SANDBOX_KEYS)
        self.assertEqual(body['messages'], [{k: body[k] for k in ('message', 'sent_by', 'message_time')}])
        self.assertEqual(set(body['debug']), DEBUG_KEYS)
        self.assertEqual(body['debug']['reply_kind'], 'llm')

    def test_error_bodies(self):
        real = self.make.session(self.cafe, phone_number='+6591234567', is_sandbox=False)
        florist_sandbox = self.make.session(self.florist, is_sandbox=True)
        self.login(self.no_business_user)
        response = self.send(self.sandbox)
        self.assertEqual((response.status_code, response.json()), (403, {'detail': 'Your account is not linked to a business.'}))
        self.login(self.cafe_user)
        cases = {
            'real session': (real, 400, 'This is a real customer chat session; only sandbox chat sessions can be used here.'),
            "another business's": (florist_sandbox, 403, 'You do not have access to this business.'),
            'unknown': (SimpleNamespace(pk=99999), 404, 'No chat session with this ID.'),
        }
        for label, (session, status_code, detail) in cases.items():
            with self.subTest(label):
                response = self.send(session)
                self.assertEqual((response.status_code, response.json()), (status_code, {'detail': detail}))
        # The session is checked before the body.
        response = self.client.post(self.url(florist_sandbox), json={})
        self.assertEqual((response.status_code, response.json()), (403, {'detail': 'You do not have access to this business.'}))
        self.ollama.chat.assert_not_called()

    def test_validation_error_bodies(self):
        self.login(self.cafe_user)
        cases = {
            'empty': ({'message': ''}, {'message': ['This field may not be blank.']}),
            'blank': ({'message': '  '}, {'message': ['This field may not be blank.']}),
            'too long': ({'message': 'x' * 4097}, {'message': ['Ensure this field has no more than 4096 characters.']}),
            'missing': ({}, {'message': ['This field is required.']}),
            'null': ({'message': None}, {'message': ['This field may not be null.']}),
            'a list': ({'message': ['a']}, {'message': ['Not a valid string.']}),
            'a bool': ({'message': True}, {'message': ['Not a valid string.']}),
            'not an object': ([1], {'non_field_errors': ['Invalid data. Expected a dictionary, but got list.']}),
        }
        for label, (data, body) in cases.items():
            with self.subTest(label):
                response = self.client.post(self.url(self.sandbox), json=data)
                self.assertEqual((response.status_code, response.json()), (400, body))
        response = self.client.post(self.url(self.sandbox), content='{bad', headers={'Content-Type': 'application/json'})
        self.assertEqual((response.status_code, response.json()), (
            400, {'detail': 'JSON parse error - Expecting property name enclosed in double quotes: line 1 column 2 (char 1)'},
        ))
        self.ollama.chat.assert_not_called()
        self.assertEqual(self.refreshed(self.sandbox).chat_message_json, [])

    def test_a_number_is_a_valid_message(self):
        # DRF's CharField turns numbers into strings.
        self.login(self.cafe_user)
        self.assertEqual(self.send(self.sandbox, 5).status_code, 200)
        self.assertEqual(self.refreshed(self.sandbox).chat_message_json[0]['message'], '5')

    def test_llm_error_mapping(self):
        self.login(self.cafe_user)
        cases = {
            'unreachable': (ConnectionError('x'), 503, f'Could not connect to Ollama at {config.OLLAMA_HOST}.'),
            'timeout': (httpx.ReadTimeout('t'), 504, f'Ollama did not respond within {config.OLLAMA_TIMEOUT_SECONDS} seconds.'),
            'model error': (ResponseError('model "x" not found', 404), 502, 'Ollama error (404): model "x" not found'),
            'not JSON': (lambda **kwargs: SimpleNamespace(message=SimpleNamespace(content='not json')), 502, 'The model did not return valid JSON.'),
        }
        for label, (side_effect, status_code, detail) in cases.items():
            with self.subTest(label):
                self.ollama.chat.side_effect = side_effect
                response = self.send(self.sandbox)
                self.assertEqual((response.status_code, response.json()), (status_code, {'detail': detail}))
        self.assertEqual([m['sent_by'] for m in self.refreshed(self.sandbox).chat_message_json], ['customer'] * 4)


def token_not_valid(message: str) -> dict:
    return {
        'detail': 'Given token not valid for any token type', 'code': 'token_not_valid',
        'messages': [{'token_class': 'AccessToken', 'token_type': 'access', 'message': message}],
    }


class SandboxChatMessageAuthTests(ApiTestCase):
    """Not in Django's tests: the 401s of SimpleJWT's JWTAuthentication (bodies checked against
    configuration-service), which app/auth.py reproduces."""

    def setUp(self):
        super().setUp()
        self.cafe = self.make.business('Kopi Café')
        self.user = self.make.user(self.cafe, username='cafe')
        self.sandbox = self.make.session(self.cafe, is_sandbox=True)
        self.ollama = MagicMock()
        self.ollama.chat.side_effect = fake_ollama_chat('Hello!')
        patcher = patch('app.llm.get_client', return_value=self.ollama)
        patcher.start()
        self.addCleanup(patcher.stop)

    def send(self, authorization=None):
        headers = {'Authorization': authorization} if authorization is not None else {}
        return self.client.post(f'/api/chat/sandbox-sessions/{self.sandbox.pk}/messages/', json={'message': 'hi'}, headers=headers)

    def assert401(self, response, body):
        self.assertEqual((response.status_code, response.json()), (401, body))
        self.assertEqual(response.headers['WWW-Authenticate'], 'Bearer realm="api"')

    def encode(self, payload, key=TEST_SIGNING_KEY):
        return 'Bearer ' + jwt.encode(payload, key, algorithm='HS256')

    def payload(self, **claims):
        now = int(time.time())
        return {'token_type': 'access', 'exp': now + 900, 'iat': now, 'jti': 'test', 'user_id': str(self.user.id), **claims}

    def test_a_valid_token(self):
        self.assertEqual(self.send(f'Bearer {access_token(self.user.id)}').status_code, 200)
        self.assertEqual(self.send(self.encode(self.payload(user_id=self.user.id))).status_code, 200)  # an int user_id too

    def test_missing_header(self):
        self.assert401(self.send(), {'detail': 'Authentication credentials were not provided.'})
        self.ollama.chat.assert_not_called()

    def test_bad_authorization_header(self):
        for header in ('Bearer', 'Bearer a b'):
            with self.subTest(header=header):
                self.assert401(self.send(header), {
                    'detail': 'Authorization header must contain two space-delimited values', 'code': 'bad_authorization_header',
                })

    def test_invalid_tokens(self):
        cases = {
            'garbage': ('Bearer garbage', 'Token is invalid'),
            'expired': (self.encode(self.payload(exp=int(time.time()) - 10)), 'Token is expired'),
            'wrong key': (self.encode(self.payload(), key='another-key-another-key-another-key-123'), 'Token is invalid'),
            'refresh token': (self.encode(self.payload(token_type='refresh')), 'Token has wrong type'),
        }
        for label, (header, message) in cases.items():
            with self.subTest(label):
                self.assert401(self.send(header), token_not_valid(message))
        self.ollama.chat.assert_not_called()

    def test_tokens_missing_a_claim(self):
        # SimpleJWT's Token.verify(): check_exp(), then the id (jti), then verify_token_type().
        without = lambda claim: self.encode({k: v for k, v in self.payload().items() if k != claim})  # noqa: E731
        for claim, message in (('token_type', 'Token has no type'), ('exp', "Token has no 'exp' claim"), ('jti', 'Token has no id')):
            with self.subTest(claim):
                self.assert401(self.send(without(claim)), token_not_valid(message))

    def test_no_user_id(self):
        payload = {k: v for k, v in self.payload().items() if k != 'user_id'}
        self.assert401(self.send(self.encode(payload)), {
            'detail': 'Token contained no recognizable user identification', 'code': 'token_not_valid',
        })

    def test_unknown_user(self):
        self.assert401(self.send(f'Bearer {access_token(99999)}'), {'detail': 'User not found', 'code': 'user_not_found'})

    def test_inactive_user(self):
        inactive = self.make.user(self.cafe, username='inactive', is_active=False)
        self.assert401(self.send(f'Bearer {access_token(inactive.id)}'), {'detail': 'User is inactive', 'code': 'user_inactive'})
        self.ollama.chat.assert_not_called()
