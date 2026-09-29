import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import httpx
from ollama import ResponseError

from app import config, create_app


def fake_chat_response(content: str):
    """Shape of ollama's ChatResponse that the app reads: response.message.content."""
    return SimpleNamespace(message=SimpleNamespace(content=content))


class ChatRouteTests(unittest.TestCase):
    def setUp(self):
        self.client = create_app({'TESTING': True}).test_client()
        # Replace the Ollama client so tests never need a running model.
        self.ollama = MagicMock()
        patcher = patch('app.llm.get_client', return_value=self.ollama)
        patcher.start()
        self.addCleanup(patcher.stop)

    def post_chat(self, body):
        return self.client.post('/chat', json=body)

    # --- Success --------------------------------------------------------------------

    def test_returns_model_reply(self):
        self.ollama.chat.return_value = fake_chat_response('Hi there!')
        response = self.post_chat({'prompt': 'Hello'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {'reply': 'Hi there!', 'model': config.OLLAMA_MODEL})

    def test_sends_model_system_prompt_and_user_prompt(self):
        self.ollama.chat.return_value = fake_chat_response('ok')
        self.post_chat({'prompt': 'What is 2 + 2?'})
        self.ollama.chat.assert_called_once_with(
            model=config.OLLAMA_MODEL,
            messages=[
                {'role': 'system', 'content': config.SYSTEM_PROMPT},
                {'role': 'user', 'content': 'What is 2 + 2?'},
            ],
        )

    def test_each_request_is_independent(self):
        self.ollama.chat.return_value = fake_chat_response('ok')
        self.post_chat({'prompt': 'first'})
        self.post_chat({'prompt': 'second'})
        second_messages = self.ollama.chat.call_args.kwargs['messages']
        self.assertEqual([m['content'] for m in second_messages], [config.SYSTEM_PROMPT, 'second'])

    # --- Validation (422) -----------------------------------------------------------

    def test_invalid_requests_return_422(self):
        cases = {
            'missing prompt': {},
            'empty prompt': {'prompt': ''},
            'blank prompt': {'prompt': '   '},
            'too long': {'prompt': 'x' * (config.CHAT_PROMPT_MAX_LENGTH + 1)},
            'not a string': {'prompt': 123},
            'unknown field': {'prompt': 'hi', 'history': []},
        }
        for label, body in cases.items():
            with self.subTest(label):
                response = self.post_chat(body)
                self.assertEqual(response.status_code, 422)
                self.assertIn('json', response.get_json()['errors'])
        self.ollama.chat.assert_not_called()

    def test_non_json_body_returns_422(self):
        response = self.client.post('/chat', data='hello', content_type='text/plain')
        self.assertEqual(response.status_code, 422)
        self.ollama.chat.assert_not_called()

    def test_prompt_at_max_length_is_accepted(self):
        self.ollama.chat.return_value = fake_chat_response('ok')
        response = self.post_chat({'prompt': 'x' * config.CHAT_PROMPT_MAX_LENGTH})
        self.assertEqual(response.status_code, 200)

    def test_get_not_allowed(self):
        self.assertEqual(self.client.get('/chat').status_code, 405)

    # --- Ollama failures ------------------------------------------------------------

    def test_ollama_unreachable_returns_503(self):
        self.ollama.chat.side_effect = ConnectionError('Failed to connect to Ollama.')
        response = self.post_chat({'prompt': 'Hello'})
        self.assertEqual(response.status_code, 503)
        self.assertIn(config.OLLAMA_HOST, response.get_json()['message'])

    def test_ollama_timeout_returns_504(self):
        self.ollama.chat.side_effect = httpx.ReadTimeout('timed out')
        response = self.post_chat({'prompt': 'Hello'})
        self.assertEqual(response.status_code, 504)

    def test_ollama_error_returns_502(self):
        self.ollama.chat.side_effect = ResponseError("model 'qwen2.5:7b-instruct-q4_K_M' not found", 404)
        response = self.post_chat({'prompt': 'Hello'})
        self.assertEqual(response.status_code, 502)
        self.assertIn('not found', response.get_json()['message'])


class ApiDocsTests(unittest.TestCase):
    def setUp(self):
        self.client = create_app({'TESTING': True}).test_client()

    def test_swagger_ui_page(self):
        response = self.client.get('/docs')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'swagger-ui', response.data)

    def test_openapi_spec_documents_chat(self):
        spec = self.client.get('/openapi.json').get_json()
        self.assertEqual(spec['info']['title'], config.API_TITLE)
        chat = spec['paths']['/chat']['post']
        self.assertEqual(
            chat['requestBody']['content']['application/json']['schema']['$ref'],
            '#/components/schemas/ChatRequest',
        )
        self.assertTrue({'200', '422', '502', '503', '504'} <= set(chat['responses']))
        self.assertIn('/', spec['paths'])


if __name__ == '__main__':
    unittest.main()
