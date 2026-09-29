from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from auth_app.models import BusinessUser
from configuration_app.models import BusinessConfiguration

from . import llm
from .models import ChatConfiguration
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
