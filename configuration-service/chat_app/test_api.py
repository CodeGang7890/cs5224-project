from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.urls import reverse
from rest_framework.test import APITestCase

from . import llm


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
