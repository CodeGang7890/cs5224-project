import json
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from auth_app.models import BusinessUser
from configuration_app.models import BusinessConfiguration

from . import llm
from .models import ChatConfiguration, ChatSession
from .tests import VALID_CONFIG, VALID_MESSAGES, config
from .validators import validate_chat_messages


class ChatViewTests(APITestCase):
    url = reverse('chat_app:chat')

    def test_returns_mocked_llm_reply(self):
        # Replace the Ollama client so the test never needs a running model.
        ollama = MagicMock()
        ollama.chat.return_value = SimpleNamespace(message=SimpleNamespace(content='Hi there!'))
        with patch('chat_app.llm.get_client', return_value=ollama):
            response = self.client.post(self.url, {'prompt': 'Hello'}, format='json')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {'reply': 'Hi there!', 'model': llm.OLLAMA_MODEL, 'options': llm.OLLAMA_OPTIONS},
        )


class ChatConfigurationAPITests(APITestCase):
    url = reverse('chat_app:chat-configuration')

    @classmethod
    def setUpTestData(cls):
        cls.cafe = BusinessConfiguration.objects.create(business_name='Café', location='Singapore')
        cls.florist = BusinessConfiguration.objects.create(business_name='Florist', location='Singapore')
        cls.cafe_user = BusinessUser.objects.create_user(username='cafe', password='123', business=cls.cafe)
        cls.florist_user = BusinessUser.objects.create_user(
            username='florist', password='123', business=cls.florist
        )
        cls.no_business_user = BusinessUser.objects.create_user(username='nobiz', password='123')
        cls.florist_config = ChatConfiguration.objects.create(business=cls.florist, config_json=VALID_CONFIG)

    def put_config(self, config_json):
        return self.client.put(self.url, {'config_json': config_json}, format='json')

    # --- Authentication / business --------------------------------------------------

    def test_requires_authentication(self):
        for method in ('get', 'put'):
            with self.subTest(method=method):
                response = getattr(self.client, method)(self.url, {'config_json': VALID_CONFIG}, format='json')
                self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_user_without_business_gets_403(self):
        self.client.force_authenticate(self.no_business_user)
        self.assertEqual(self.client.get(self.url).status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.put_config(VALID_CONFIG).status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(ChatConfiguration.objects.count(), 1)

    def test_patch_and_delete_not_allowed(self):
        self.client.force_authenticate(self.florist_user)
        self.assertEqual(self.client.patch(self.url, {}, format='json').status_code, 405)
        self.assertEqual(self.client.delete(self.url).status_code, 405)

    # --- GET ------------------------------------------------------------------------

    def test_get_returns_own_business_configuration(self):
        self.client.force_authenticate(self.florist_user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            set(response.json()), {'id', 'business', 'config_json', 'last_updated'}
        )
        self.assertEqual(response.json()['id'], self.florist_config.pk)
        self.assertEqual(response.json()['business'], self.florist.pk)
        self.assertEqual(response.json()['config_json'], VALID_CONFIG)

    def test_get_without_configuration_returns_404(self):
        # The café has no configuration; it must not see the florist's.
        self.client.force_authenticate(self.cafe_user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    # --- PUT ------------------------------------------------------------------------

    def test_put_replaces_config_json(self):
        self.client.force_authenticate(self.florist_user)
        before = self.florist_config.last_updated
        new_config = config(b0={'position_x': 150}, b2={'block_type': 'DETAILS_COLLECTION_BLOCK'})
        response = self.put_config(new_config)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()['config_json'], new_config)
        self.florist_config.refresh_from_db()
        self.assertEqual(self.florist_config.config_json, new_config)
        self.assertGreater(self.florist_config.last_updated, before)
        self.assertEqual(ChatConfiguration.objects.count(), 1)

    def test_put_creates_configuration_if_missing(self):
        self.client.force_authenticate(self.cafe_user)
        response = self.put_config(VALID_CONFIG)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.json()['business'], self.cafe.pk)
        self.assertEqual(self.cafe.chat_configuration.config_json, VALID_CONFIG)
        # A second PUT updates the same row.
        self.assertEqual(self.put_config(VALID_CONFIG).status_code, status.HTTP_200_OK)
        self.assertEqual(ChatConfiguration.objects.filter(business=self.cafe).count(), 1)

    def test_put_ignores_read_only_fields(self):
        self.client.force_authenticate(self.florist_user)
        response = self.client.put(
            self.url,
            {'config_json': VALID_CONFIG, 'business': self.cafe.pk, 'id': 999, 'last_updated': '2000-01-01T00:00:00Z'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()['business'], self.florist.pk)
        self.assertEqual(response.json()['id'], self.florist_config.pk)
        self.assertFalse(ChatConfiguration.objects.filter(business=self.cafe).exists())

    def test_put_rejects_invalid_config_json(self):
        self.client.force_authenticate(self.florist_user)
        cases = {
            'not a list': {'id': 1},
            'empty list (no START_BLOCK)': [],
            'two START_BLOCKs': config(b1={'block_type': 'START_BLOCK'}),
            'unknown block type': config(b1={'block_type': 'PAYMENT_BLOCK'}),
            'duplicate id': config(b2={'id': 1}),
            'dangling next_block_id': config(b2={'next_block_id': 99}),
            'missing field': [{k: v for k, v in block.items() if k != 'position_x'} for block in VALID_CONFIG],
            'non-numeric position': config(b0={'position_y': 'top'}),
        }
        for label, bad_config in cases.items():
            with self.subTest(label):
                response = self.put_config(bad_config)
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn('config_json', response.json())
        self.florist_config.refresh_from_db()
        self.assertEqual(self.florist_config.config_json, VALID_CONFIG)

    def test_put_lists_every_error(self):
        self.client.force_authenticate(self.florist_user)
        response = self.put_config(config(b1={'block_type': 'X'}, b2={'id': 1}))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(len(response.json()['config_json']), 3)  # block_type, duplicate id, dangling next id

    def test_put_requires_config_json(self):
        self.client.force_authenticate(self.florist_user)
        for body in ({}, {'config_json': None}):
            with self.subTest(body=body):
                response = self.client.put(self.url, body, format='json')
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn('config_json', response.json())


class ChatSessionCreateAPITests(APITestCase):
    url = reverse('chat_app:chat-session-list')

    @classmethod
    def setUpTestData(cls):
        cls.cafe = BusinessConfiguration.objects.create(business_name='Café', location='Singapore')
        cls.florist = BusinessConfiguration.objects.create(business_name='Florist', location='Singapore')
        cls.cafe_user = BusinessUser.objects.create_user(username='cafe', password='123', business=cls.cafe)
        cls.florist_user = BusinessUser.objects.create_user(
            username='florist', password='123', business=cls.florist
        )
        cls.no_business_user = BusinessUser.objects.create_user(username='nobiz', password='123')
        # Start block has a string id and isn't first in the list.
        cls.cafe_config = ChatConfiguration.objects.create(
            business=cls.cafe,
            config_json=[
                {'id': 'end', 'next_block_id': None, 'block_type': 'CONFIRMATION_BLOCK', 'position_x': 400, 'position_y': 0},
                {'id': 'start', 'next_block_id': 'end', 'block_type': 'START_BLOCK', 'position_x': 0, 'position_y': 0},
            ],
        )

    def create(self, body):
        return self.client.post(self.url, body, format='json')

    def test_requires_authentication(self):
        response = self.create({'phone_number': '+6591234567'})
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertFalse(ChatSession.objects.exists())

    def test_user_without_business_gets_403(self):
        self.client.force_authenticate(self.no_business_user)
        response = self.create({'phone_number': '+6591234567'})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_creates_session_with_backend_defaults(self):
        self.client.force_authenticate(self.cafe_user)
        response = self.create({'phone_number': '+6591234567', 'display_name': 'Alice Tan'})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        body = response.json()
        self.assertEqual(
            set(body),
            {'id', 'business', 'phone_number', 'display_name', 'created_time', 'last_chat_time',
             'chat_message_json', 'chat_state_id', 'chat_state_data', 'is_sandbox'},
        )
        self.assertIs(body['is_sandbox'], False)
        self.assertEqual(body['chat_state_data'], {})
        self.assertEqual(body['business'], self.cafe.pk)
        self.assertEqual(body['phone_number'], '+6591234567')
        self.assertEqual(body['display_name'], 'Alice Tan')
        self.assertEqual(body['chat_message_json'], [])
        self.assertEqual(body['chat_state_id'], 'start')
        self.assertEqual(body['last_chat_time'], body['created_time'])

        session = ChatSession.objects.get(pk=body['id'])
        self.assertEqual(session.business, self.cafe)
        self.assertEqual(session.last_chat_time, session.created_time)
        self.assertEqual(session.chat_state_id, 'start')
        session.full_clean()  # what the API saved passes model validation

    def test_display_name_is_optional(self):
        self.client.force_authenticate(self.cafe_user)
        response = self.create({'phone_number': '+6591234567'})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.json()['display_name'], '')

    def test_backend_fields_cannot_be_set(self):
        self.client.force_authenticate(self.cafe_user)
        response = self.create({
            'phone_number': '+6591234567',
            'business': self.florist.pk,
            'created_time': '2000-01-01T00:00:00Z',
            'last_chat_time': '2000-01-01T00:00:00Z',
            'chat_message_json': [{'message': 'hi', 'sent_by': 'customer', 'message_time': '2000-01-01T00:00:00Z'}],
            'chat_state_id': 'end',
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        body = response.json()
        self.assertEqual(body['business'], self.cafe.pk)
        self.assertNotEqual(body['created_time'][:4], '2000')
        self.assertEqual(body['last_chat_time'], body['created_time'])
        self.assertEqual(body['chat_message_json'], [])
        self.assertEqual(body['chat_state_id'], 'start')

    def test_invalid_input_returns_400(self):
        self.client.force_authenticate(self.cafe_user)
        cases = {
            'missing phone number': ({}, 'phone_number'),
            'blank phone number': ({'phone_number': ''}, 'phone_number'),
            'not international format': ({'phone_number': '91234567'}, 'phone_number'),
            'spaces': ({'phone_number': '+65 9123 4567'}, 'phone_number'),
            'name too long': ({'phone_number': '+6591234567', 'display_name': 'x' * 151}, 'display_name'),
        }
        for label, (body, field) in cases.items():
            with self.subTest(label):
                response = self.create(body)
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn(field, response.json())
        self.assertFalse(ChatSession.objects.exists())

    def test_duplicate_phone_number_in_same_business_returns_400(self):
        self.client.force_authenticate(self.cafe_user)
        self.assertEqual(self.create({'phone_number': '+6591234567'}).status_code, status.HTTP_201_CREATED)
        response = self.create({'phone_number': '+6591234567', 'display_name': 'Someone else'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('phone_number', response.json())
        self.assertEqual(ChatSession.objects.count(), 1)

    def test_same_phone_number_in_another_business_is_allowed(self):
        ChatConfiguration.objects.create(business=self.florist, config_json=VALID_CONFIG)
        ChatSession.objects.create(business=self.cafe, phone_number='+6591234567', chat_state_id='start')
        self.client.force_authenticate(self.florist_user)
        response = self.create({'phone_number': '+6591234567'})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.json()['chat_state_id'], 1)  # VALID_CONFIG's START_BLOCK

    def test_business_without_chat_configuration_returns_400(self):
        self.client.force_authenticate(self.florist_user)
        response = self.create({'phone_number': '+6591234567'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('no chat configuration', response.json()['non_field_errors'][0])
        self.assertFalse(ChatSession.objects.exists())


def fake_chat_response(content: str):
    """Shape of ollama's ChatResponse that the app reads: response.message.content."""
    return SimpleNamespace(message=SimpleNamespace(content=content))


def fake_ollama_chat(reply: str, extractions=()):
    """A `side_effect` for the mocked ollama `chat`, for the chat flow (flow.py).

    Structured calls (with `format`, the extraction step) return the next of `extractions` as JSON
    (`{}`, i.e. nothing found, once they run out). Other calls (the reply) return `reply`.
    """
    queue = list(extractions)

    def chat(**kwargs):
        if kwargs.get('format'):
            return fake_chat_response(json.dumps(queue.pop(0) if queue else {}))
        return fake_chat_response(reply)

    return chat


class ChatSessionListAPITests(APITestCase):
    url = reverse('chat_app:chat-session-list')

    @classmethod
    def setUpTestData(cls):
        cls.cafe = BusinessConfiguration.objects.create(business_name='Café', location='Singapore')
        cls.florist = BusinessConfiguration.objects.create(business_name='Florist', location='Singapore')
        cls.cafe_user = BusinessUser.objects.create_user(username='cafe', password='123', business=cls.cafe)
        cls.no_business_user = BusinessUser.objects.create_user(username='nobiz', password='123')
        now = timezone.now()
        cls.older = ChatSession.objects.create(
            business=cls.cafe, phone_number='+6591111111', last_chat_time=now - timedelta(hours=2)
        )
        cls.newer = ChatSession.objects.create(
            business=cls.cafe, phone_number='+6592222222', display_name='Alice',
            last_chat_time=now, chat_message_json=VALID_MESSAGES,
        )
        cls.florist_session = ChatSession.objects.create(business=cls.florist, phone_number='+6591111111')
        cls.cafe_sandbox = ChatSession.objects.create(business=cls.cafe, is_sandbox=True, last_chat_time=now)

    def test_requires_authentication(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_user_without_business_gets_403(self):
        self.client.force_authenticate(self.no_business_user)
        self.assertEqual(self.client.get(self.url).status_code, status.HTTP_403_FORBIDDEN)

    def test_lists_own_business_sessions_most_recent_first(self):
        self.client.force_authenticate(self.cafe_user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = response.json()
        self.assertEqual(body['count'], 2)
        self.assertEqual([s['id'] for s in body['results']], [self.newer.pk, self.older.pk])
        self.assertTrue(all(s['business'] == self.cafe.pk for s in body['results']))
        self.assertEqual(body['results'][0]['chat_message_json'], VALID_MESSAGES)
        self.assertEqual(body['results'][0]['display_name'], 'Alice')

    def test_sandbox_sessions_not_listed(self):
        self.client.force_authenticate(self.cafe_user)
        ids = [s['id'] for s in self.client.get(self.url).json()['results']]
        self.assertNotIn(self.cafe_sandbox.pk, ids)

    def test_filter_by_phone_number(self):
        self.client.force_authenticate(self.cafe_user)
        response = self.client.get(self.url, {'phone_number': '+6591111111'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Only the café's session: the florist's session with the same number isn't included.
        self.assertEqual([s['id'] for s in response.json()['results']], [self.older.pk])
        response = self.client.get(self.url, {'phone_number': '+6599999999'})
        self.assertEqual(response.json()['count'], 0)

    def test_empty_list(self):
        empty = BusinessConfiguration.objects.create(business_name='Empty', location='Singapore')
        user = BusinessUser.objects.create_user(username='empty', password='123', business=empty)
        self.client.force_authenticate(user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.json(),
            {
                'count': 0, 'total_pages': 1, 'current_page': 1, 'page_size': 20,
                'has_next': False, 'has_previous': False, 'next': None, 'previous': None, 'results': [],
            },
        )


class CustomerMessageAPITests(APITestCase):
    url = reverse('chat_app:customer-message')

    @classmethod
    def setUpTestData(cls):
        cls.cafe = BusinessConfiguration.objects.create(
            business_name='Kopi Café', description='Local kopi and toast.', location='Tiong Bahru'
        )
        cls.florist = BusinessConfiguration.objects.create(business_name='Florist', location='Singapore')
        ChatConfiguration.objects.create(business=cls.cafe, config_json=VALID_CONFIG)

    def setUp(self):
        self.created = timezone.now() - timedelta(days=1)
        self.session = ChatSession.objects.create(
            business=self.cafe,
            phone_number='+6591234567',
            created_time=self.created,
            last_chat_time=self.created,
            chat_message_json=list(VALID_MESSAGES),
            chat_state_id=2,
        )
        # Replace the Ollama client so tests never need a running model.
        self.ollama = MagicMock()
        self.ollama.chat.side_effect = fake_ollama_chat('Yes, we are open until 6pm!')
        patcher = patch('chat_app.llm.get_client', return_value=self.ollama)
        patcher.start()
        self.addCleanup(patcher.stop)

    def send(self, **overrides):
        body = {'business_id': self.cafe.pk, 'phone_number': '+6591234567', 'message': 'Are you open today?'}
        return self.client.post(self.url, {**body, **overrides}, format='json')

    def test_appends_both_messages_and_returns_reply(self):
        response = self.send()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        reply = response.json()
        self.assertEqual(set(reply), {'message', 'sent_by', 'message_time'})
        self.assertEqual(reply['message'], 'Yes, we are open until 6pm!')
        self.assertEqual(reply['sent_by'], 'business-automated')

        self.session.refresh_from_db()
        messages = self.session.chat_message_json
        self.assertEqual(messages[:len(VALID_MESSAGES)], VALID_MESSAGES)  # history kept
        customer, bot = messages[len(VALID_MESSAGES):]
        self.assertEqual((customer['message'], customer['sent_by']), ('Are you open today?', 'customer'))
        self.assertEqual(bot, reply)
        validate_chat_messages(messages)  # stored in the agreed format, in time order

        self.assertGreater(self.session.last_chat_time, self.created)
        self.assertEqual(self.session.last_chat_time.isoformat(), bot['message_time'])
        self.assertEqual(self.session.created_time, self.created)
        self.assertEqual(self.session.chat_state_id, 2)  # nothing chosen yet, so still at product selection

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
        self.assertEqual(reply_call['options'], llm.OLLAMA_OPTIONS)
        self.assertNotIn('format', reply_call)

    def test_no_login_needed(self):
        # The customer isn't a logged-in user (it will be a webhook).
        self.assertEqual(self.send().status_code, status.HTTP_200_OK)

    def test_unknown_session_returns_404(self):
        ChatSession.objects.create(business=self.florist, phone_number='+6591234567', is_sandbox=True)
        cases = {
            'unknown phone number': {'phone_number': '+6599999999'},
            'another business': {'business_id': self.florist.pk},
            'unknown business': {'business_id': 99999},
        }
        for label, overrides in cases.items():
            with self.subTest(label):
                self.assertEqual(self.send(**overrides).status_code, status.HTTP_404_NOT_FOUND)
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
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn(field, response.json())
        self.ollama.chat.assert_not_called()
        self.session.refresh_from_db()
        self.assertEqual(self.session.chat_message_json, VALID_MESSAGES)

    def test_llm_failure_keeps_customer_message(self):
        self.ollama.chat.side_effect = ConnectionError('Failed to connect to Ollama.')
        response = self.send()
        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.session.refresh_from_db()
        self.assertEqual(len(self.session.chat_message_json), len(VALID_MESSAGES) + 1)
        self.assertEqual(self.session.chat_message_json[-1]['sent_by'], 'customer')
        self.assertGreater(self.session.last_chat_time, self.created)


class SandboxChatSessionAPITests(APITestCase):
    list_url = reverse('chat_app:sandbox-session-list')

    @staticmethod
    def detail_url(session):
        return reverse('chat_app:sandbox-session-detail', args=[session.pk])

    @classmethod
    def setUpTestData(cls):
        cls.cafe = BusinessConfiguration.objects.create(business_name='Café', location='Singapore')
        cls.florist = BusinessConfiguration.objects.create(business_name='Florist', location='Singapore')
        cls.cafe_user = BusinessUser.objects.create_user(username='cafe', password='123', business=cls.cafe)
        cls.florist_user = BusinessUser.objects.create_user(
            username='florist', password='123', business=cls.florist
        )
        cls.no_business_user = BusinessUser.objects.create_user(username='nobiz', password='123')
        ChatConfiguration.objects.create(business=cls.cafe, config_json=VALID_CONFIG)

    def setUp(self):
        now = timezone.now()
        self.cafe_sandbox_old = ChatSession.objects.create(
            business=self.cafe, is_sandbox=True, display_name='Old test', last_chat_time=now - timedelta(hours=1)
        )
        self.cafe_sandbox_new = ChatSession.objects.create(
            business=self.cafe, is_sandbox=True, chat_message_json=list(VALID_MESSAGES), last_chat_time=now
        )
        self.cafe_real = ChatSession.objects.create(business=self.cafe, phone_number='+6591234567')
        self.florist_sandbox = ChatSession.objects.create(business=self.florist, is_sandbox=True)

    def login(self, user):
        self.client.force_authenticate(user)

    # --- Authentication / business --------------------------------------------------

    def test_requires_authentication(self):
        for method, url in [
            ('get', self.list_url),
            ('post', self.list_url),
            ('delete', self.detail_url(self.cafe_sandbox_old)),
        ]:
            with self.subTest(method=method):
                self.assertEqual(getattr(self.client, method)(url).status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(ChatSession.objects.count(), 4)

    def test_user_without_business_gets_403(self):
        self.login(self.no_business_user)
        self.assertEqual(self.client.get(self.list_url).status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.post(self.list_url, {}, format='json').status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(
            self.client.delete(self.detail_url(self.cafe_sandbox_old)).status_code, status.HTTP_403_FORBIDDEN
        )
        self.assertEqual(ChatSession.objects.count(), 4)

    # --- GET (list) -----------------------------------------------------------------

    def test_lists_only_own_sandbox_sessions(self):
        self.login(self.cafe_user)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = response.json()
        self.assertEqual(body['count'], 2)  # not the real session, not the florist's sandbox
        self.assertEqual([s['id'] for s in body['results']], [self.cafe_sandbox_new.pk, self.cafe_sandbox_old.pk])
        self.assertTrue(all(s['is_sandbox'] for s in body['results']))
        self.assertEqual(body['results'][0]['chat_message_json'], VALID_MESSAGES)

    # --- POST (create) --------------------------------------------------------------

    def test_creates_sandbox_session(self):
        self.login(self.cafe_user)
        response = self.client.post(self.list_url, {'display_name': 'sandbox_user'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        body = response.json()
        self.assertIs(body['is_sandbox'], True)
        self.assertEqual(body['business'], self.cafe.pk)
        self.assertEqual(body['display_name'], 'sandbox_user')
        self.assertEqual(body['phone_number'], '')
        self.assertEqual(body['chat_message_json'], [])
        self.assertEqual(body['chat_state_id'], 1)  # VALID_CONFIG's START_BLOCK
        self.assertEqual(body['last_chat_time'], body['created_time'])
        ChatSession.objects.get(pk=body['id']).full_clean()

    def test_create_with_empty_body_and_multiple_sessions(self):
        self.login(self.cafe_user)
        for _ in range(2):
            self.assertEqual(self.client.post(self.list_url, {}, format='json').status_code, status.HTTP_201_CREATED)
        self.assertEqual(ChatSession.objects.filter(business=self.cafe, is_sandbox=True).count(), 4)

    def test_create_with_phone_number_used_by_real_session(self):
        self.login(self.cafe_user)
        response = self.client.post(self.list_url, {'phone_number': '+6591234567'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.json()['phone_number'], '+6591234567')

    def test_create_ignores_backend_fields(self):
        self.login(self.cafe_user)
        response = self.client.post(
            self.list_url,
            {'is_sandbox': False, 'business': self.florist.pk, 'chat_state_id': 3, 'chat_message_json': VALID_MESSAGES},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        body = response.json()
        self.assertIs(body['is_sandbox'], True)
        self.assertEqual(body['business'], self.cafe.pk)
        self.assertEqual(body['chat_state_id'], 1)
        self.assertEqual(body['chat_message_json'], [])

    def test_create_invalid_input_returns_400(self):
        self.login(self.cafe_user)
        for body, field in [({'phone_number': '000'}, 'phone_number'), ({'display_name': 'x' * 151}, 'display_name')]:
            with self.subTest(body=body):
                response = self.client.post(self.list_url, body, format='json')
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn(field, response.json())

    def test_create_without_chat_configuration_returns_400(self):
        self.login(self.florist_user)
        response = self.client.post(self.list_url, {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('non_field_errors', response.json())

    # --- DELETE ---------------------------------------------------------------------

    def test_deletes_own_sandbox_session(self):
        self.login(self.cafe_user)
        response = self.client.delete(self.detail_url(self.cafe_sandbox_new))
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(ChatSession.objects.filter(pk=self.cafe_sandbox_new.pk).exists())
        self.assertEqual(ChatSession.objects.count(), 3)

    def test_cannot_delete_real_session(self):
        self.login(self.cafe_user)
        response = self.client.delete(self.detail_url(self.cafe_real))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('only sandbox chat sessions', response.json()['detail'])
        self.assertTrue(ChatSession.objects.filter(pk=self.cafe_real.pk).exists())

    def test_cannot_delete_other_business_session(self):
        self.login(self.cafe_user)
        response = self.client.delete(self.detail_url(self.florist_sandbox))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(ChatSession.objects.filter(pk=self.florist_sandbox.pk).exists())

    def test_other_business_real_session_is_403_not_400(self):
        florist_real = ChatSession.objects.create(business=self.florist, phone_number='+6598765432')
        self.login(self.cafe_user)
        self.assertEqual(self.client.delete(self.detail_url(florist_real)).status_code, status.HTTP_403_FORBIDDEN)

    def test_unknown_session_returns_404(self):
        self.login(self.cafe_user)
        response = self.client.delete(reverse('chat_app:sandbox-session-detail', args=[99999]))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_delete_twice_returns_404(self):
        self.login(self.cafe_user)
        self.client.delete(self.detail_url(self.cafe_sandbox_old))
        self.assertEqual(self.client.delete(self.detail_url(self.cafe_sandbox_old)).status_code, status.HTTP_404_NOT_FOUND)

    def test_get_and_put_on_detail_not_allowed(self):
        self.login(self.cafe_user)
        self.assertEqual(self.client.get(self.detail_url(self.cafe_sandbox_old)).status_code, 405)
        self.assertEqual(self.client.put(self.detail_url(self.cafe_sandbox_old), {}).status_code, 405)


class SandboxChatMessageAPITests(APITestCase):
    @staticmethod
    def url(session):
        return reverse('chat_app:sandbox-session-messages', args=[session.pk])

    @classmethod
    def setUpTestData(cls):
        cls.cafe = BusinessConfiguration.objects.create(business_name='Kopi Café', location='Tiong Bahru')
        cls.florist = BusinessConfiguration.objects.create(business_name='Florist', location='Singapore')
        cls.cafe_user = BusinessUser.objects.create_user(username='cafe', password='123', business=cls.cafe)
        cls.no_business_user = BusinessUser.objects.create_user(username='nobiz', password='123')
        ChatConfiguration.objects.create(business=cls.cafe, config_json=VALID_CONFIG)

    def setUp(self):
        self.sandbox = ChatSession.objects.create(business=self.cafe, is_sandbox=True, chat_state_id=1)
        self.other_sandbox = ChatSession.objects.create(business=self.cafe, is_sandbox=True)
        self.ollama = MagicMock()
        self.ollama.chat.side_effect = fake_ollama_chat('Hello from the café!')
        patcher = patch('chat_app.llm.get_client', return_value=self.ollama)
        patcher.start()
        self.addCleanup(patcher.stop)

    def send(self, session, message='Hi there'):
        return self.client.post(self.url(session), {'message': message}, format='json')

    def test_requires_authentication(self):
        self.assertEqual(self.send(self.sandbox).status_code, status.HTTP_401_UNAUTHORIZED)
        self.ollama.chat.assert_not_called()

    def test_user_without_business_gets_403(self):
        self.client.force_authenticate(self.no_business_user)
        self.assertEqual(self.send(self.sandbox).status_code, status.HTTP_403_FORBIDDEN)

    def test_appends_messages_and_returns_reply(self):
        self.client.force_authenticate(self.cafe_user)
        response = self.send(self.sandbox, '  Are you open?  ')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()['message'], 'Hello from the café!')
        self.assertEqual(response.json()['sent_by'], 'business-automated')
        self.sandbox.refresh_from_db()
        self.assertEqual(
            [(m['sent_by'], m['message']) for m in self.sandbox.chat_message_json],
            [('customer', 'Are you open?'), ('business-automated', 'Hello from the café!')],
        )
        validate_chat_messages(self.sandbox.chat_message_json)
        self.assertEqual(self.sandbox.chat_state_id, 1)  # only asked a question: still at the start
        self.assertIn('Kopi Café', self.ollama.chat.call_args.kwargs['messages'][0]['content'])

    def test_sessions_are_independent(self):
        self.client.force_authenticate(self.cafe_user)
        self.send(self.sandbox, 'first chat')
        self.send(self.other_sandbox, 'second chat')
        self.sandbox.refresh_from_db()
        self.other_sandbox.refresh_from_db()
        self.assertEqual(self.sandbox.chat_message_json[0]['message'], 'first chat')
        self.assertEqual(self.other_sandbox.chat_message_json[0]['message'], 'second chat')
        self.assertEqual(len(self.sandbox.chat_message_json), 2)

    def test_real_session_returns_400(self):
        real = ChatSession.objects.create(business=self.cafe, phone_number='+6591234567')
        self.client.force_authenticate(self.cafe_user)
        self.assertEqual(self.send(real).status_code, status.HTTP_400_BAD_REQUEST)
        real.refresh_from_db()
        self.assertEqual(real.chat_message_json, [])

    def test_other_business_session_returns_403(self):
        florist_sandbox = ChatSession.objects.create(business=self.florist, is_sandbox=True)
        self.client.force_authenticate(self.cafe_user)
        self.assertEqual(self.send(florist_sandbox).status_code, status.HTTP_403_FORBIDDEN)
        florist_sandbox.refresh_from_db()
        self.assertEqual(florist_sandbox.chat_message_json, [])

    def test_unknown_session_returns_404(self):
        self.client.force_authenticate(self.cafe_user)
        response = self.client.post(
            reverse('chat_app:sandbox-session-messages', args=[99999]), {'message': 'hi'}, format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_invalid_message_returns_400(self):
        self.client.force_authenticate(self.cafe_user)
        for message in ('', '   ', 'x' * 4097):
            with self.subTest(length=len(message)):
                response = self.send(self.sandbox, message)
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn('message', response.json())
        self.ollama.chat.assert_not_called()

    def test_llm_failure_keeps_message(self):
        self.ollama.chat.side_effect = ConnectionError('down')
        self.client.force_authenticate(self.cafe_user)
        self.assertEqual(self.send(self.sandbox).status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.sandbox.refresh_from_db()
        self.assertEqual([m['sent_by'] for m in self.sandbox.chat_message_json], ['customer'])


class ChatSessionListFilteringAPITests(APITestCase):
    """Filtering, sorting and pagination of GET /api/chat/sessions/, on the sample fixtures.

    kopi_owner's business (1) has 11 real sessions (pks 1–3, 9–16) and 2 sandbox ones (7–8).
    """

    url = reverse('chat_app:chat-session-list')
    fixtures = [
        'sample_business_configurations',
        'sample_business_users',
        'sample_chat_configurations',
        'sample_chat_sessions',
    ]
    # Business 1's real sessions, most recent chat first (the default order).
    ALL = [16, 15, 14, 13, 12, 11, 10, 9, 3, 2, 1]

    def setUp(self):
        self.client.force_authenticate(BusinessUser.objects.get(username='kopi_owner'))

    def ids(self, params=None):
        response = self.client.get(self.url, params or {})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.content)
        return [s['id'] for s in response.json()['results']]

    # --- Scope / default ------------------------------------------------------------

    def test_default_lists_own_real_sessions_most_recent_first(self):
        # No sandbox sessions (7, 8) and no other businesses' sessions (4, 5, 6).
        self.assertEqual(self.ids(), self.ALL)

    def test_other_business_sees_only_its_own(self):
        self.client.force_authenticate(BusinessUser.objects.get(username='bloom_owner'))
        self.assertEqual(self.ids(), [5, 4])

    def test_sandbox_filter(self):
        self.assertEqual(self.ids({'sandbox': 'exclude'}), self.ALL)
        self.assertEqual(self.ids({'sandbox': 'only'}), [8, 7])
        # Sandbox chats 8 (6 Sep 15:30) and 7 (5 Sep 10:01) slot in by last chat time.
        self.assertEqual(self.ids({'sandbox': 'include'}), [16, 15, 14, 13, 12, 11, 8, 10, 7, 9, 3, 2, 1])

    def test_sandbox_filter_combines_with_others(self):
        self.assertEqual(self.ids({'sandbox': 'include', 'chat_state_id': 1}), [13, 12, 8, 3])
        self.assertEqual(self.ids({'sandbox': 'only', 'search': 'sandbox'}), [7])
        body = self.client.get(self.url, {'sandbox': 'include', 'page_size': 5}).json()
        self.assertEqual((body['count'], body['total_pages']), (13, 3))

    def test_invalid_sandbox_value_returns_400(self):
        response = self.client.get(self.url, {'sandbox': 'yes'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('sandbox', response.json())

    # --- Pagination -----------------------------------------------------------------

    def test_first_page(self):
        body = self.client.get(self.url, {'page_size': 4}).json()
        self.assertEqual([s['id'] for s in body['results']], self.ALL[:4])
        self.assertEqual(body['count'], 11)
        self.assertEqual(body['total_pages'], 3)
        self.assertEqual(body['current_page'], 1)
        self.assertEqual(body['page_size'], 4)
        self.assertIs(body['has_next'], True)
        self.assertIs(body['has_previous'], False)
        self.assertIn('page=2', body['next'])
        self.assertIsNone(body['previous'])

    def test_middle_and_last_page(self):
        middle = self.client.get(self.url, {'page_size': 4, 'page': 2}).json()
        self.assertEqual([s['id'] for s in middle['results']], self.ALL[4:8])
        self.assertEqual((middle['current_page'], middle['has_next'], middle['has_previous']), (2, True, True))

        last = self.client.get(self.url, {'page_size': 4, 'page': 3}).json()
        self.assertEqual([s['id'] for s in last['results']], self.ALL[8:])
        self.assertEqual((last['current_page'], last['has_next'], last['has_previous']), (3, False, True))
        self.assertIsNone(last['next'])

    def test_pages_cover_every_session_once(self):
        seen = []
        for page in (1, 2, 3):
            seen += self.ids({'page_size': 4, 'page': page})
        self.assertEqual(seen, self.ALL)

    def test_default_page_size_is_20(self):
        body = self.client.get(self.url).json()
        self.assertEqual((body['page_size'], body['total_pages'], body['has_next']), (20, 1, False))

    def test_page_size_is_capped_at_100(self):
        self.assertEqual(self.client.get(self.url, {'page_size': 1000}).json()['page_size'], 100)

    def test_invalid_page_size_falls_back_to_default(self):
        for bad in ('0', '-5', 'abc'):
            with self.subTest(page_size=bad):
                self.assertEqual(self.client.get(self.url, {'page_size': bad}).json()['page_size'], 20)

    def test_page_out_of_range_returns_404(self):
        for bad in ('4', '0', 'abc'):
            with self.subTest(page=bad):
                response = self.client.get(self.url, {'page_size': 4, 'page': bad})
                self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_pagination_applies_after_filters(self):
        body = self.client.get(self.url, {'chat_state_id': 1, 'page_size': 2}).json()
        self.assertEqual((body['count'], body['total_pages'], body['has_next']), (3, 2, True))
        self.assertEqual([s['id'] for s in body['results']], [13, 12])

    # --- Filters --------------------------------------------------------------------

    def test_filter_by_exact_phone_number(self):
        self.assertEqual(self.ids({'phone_number': '+6591234567'}), [1])
        self.assertEqual(self.ids({'phone_number': '+659123'}), [])  # exact, not partial

    def test_filter_by_display_name(self):
        self.assertEqual(self.ids({'display_name': 'tan'}), [16, 1])  # Lina Tan, Alice Tan

    def test_search_name_or_phone(self):
        self.assertEqual(self.ids({'search': 'TAN'}), [16, 1])
        self.assertEqual(self.ids({'search': '9111000'}), [16, 15, 14, 13, 12, 11, 10, 9])

    def test_filter_by_chat_state_id(self):
        self.assertEqual(self.ids({'chat_state_id': 1}), [13, 12, 3])
        self.assertEqual(self.ids({'chat_state_id': 4}), [14, 9, 1])
        self.assertEqual(self.ids({'chat_state_id': 'unknown'}), [])

    def test_filter_by_has_messages(self):
        self.assertEqual(self.ids({'has_messages': 'false'}), [13])
        self.assertEqual(self.ids({'has_messages': 'true'}), [s for s in self.ALL if s != 13])

    def test_filter_by_last_chat_time_range(self):
        self.assertEqual(self.ids({'last_chat_time_after': '2026-09-08T00:00:00+08:00'}), [16, 15, 14, 13, 12])
        self.assertEqual(
            self.ids({
                'last_chat_time_after': '2026-09-05T00:00:00+08:00',
                'last_chat_time_before': '2026-09-07T23:59:59+08:00',
            }),
            [11, 10, 9],
        )

    def test_filter_by_created_time_range(self):
        self.assertEqual(self.ids({'created_time_before': '2026-09-03T23:59:59+08:00'}), [3, 2, 1])

    def test_filters_combine(self):
        self.assertEqual(self.ids({'chat_state_id': 2, 'last_chat_time_after': '2026-09-06T00:00:00+08:00'}), [15, 10])

    def test_invalid_filter_values_return_400(self):
        for params, field in (
            ({'last_chat_time_after': 'yesterday'}, 'last_chat_time'),
            ({'created_time_before': '2026-13-01'}, 'created_time'),
            ({'has_messages': 'maybe'}, 'has_messages'),
        ):
            with self.subTest(params=params):
                response = self.client.get(self.url, params)
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn(field, response.json())

    def test_unknown_parameters_are_ignored(self):
        self.assertEqual(self.ids({'colour': 'blue'}), self.ALL)

    # --- Sorting --------------------------------------------------------------------

    def test_order_by_display_name(self):
        # Blank names first; ties (13 and 3) are broken by newest id.
        self.assertEqual(self.ids({'ordering': 'display_name'}), [13, 3, 1, 2, 9, 10, 11, 12, 14, 15, 16])
        self.assertEqual(self.ids({'ordering': '-display_name'})[:3], [16, 15, 14])

    def test_order_by_last_chat_time_ascending(self):
        self.assertEqual(self.ids({'ordering': 'last_chat_time'}), list(reversed(self.ALL)))

    def test_order_by_multiple_fields(self):
        # +6581112222 (3) sorts before +6591110001 (9) and +6591110002 (10).
        self.assertEqual(self.ids({'ordering': 'phone_number,-created_time'})[:3], [3, 9, 10])

    def test_invalid_ordering_returns_400(self):
        for bad in ('chat_message_json', 'password', '-colour'):
            with self.subTest(ordering=bad):
                response = self.client.get(self.url, {'ordering': bad})
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn('ordering', response.json())

    def test_sorting_filtering_and_pagination_together(self):
        body = self.client.get(
            self.url, {'search': '9111000', 'ordering': 'display_name', 'page_size': 3, 'page': 2}
        ).json()
        # Names: '' (13), Farah (9), Gabriel (10) | Hui Min (11), Irfan (12), Jasmine (14) | Kumar, Lina
        self.assertEqual([s['id'] for s in body['results']], [11, 12, 14])
        self.assertEqual((body['count'], body['total_pages'], body['has_next'], body['has_previous']), (8, 3, True, True))
