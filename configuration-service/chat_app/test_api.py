from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from auth_app.models import BusinessUser
from configuration_app.models import BusinessConfiguration

from . import llm
from .models import ChatConfiguration, ChatSession
from .tests import VALID_CONFIG, config


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
             'chat_message_json', 'chat_state_id'},
        )
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

    def test_get_not_allowed(self):
        self.client.force_authenticate(self.cafe_user)
        self.assertEqual(self.client.get(self.url).status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
