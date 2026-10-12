import json
import unittest
from unittest.mock import patch

import httpx

from app import config
from app.whatsapp_sender import SendError, send_text


@patch.object(config, 'CONFIGURATION_SERVICE_URL', 'http://configuration.example/api')
@patch.object(config, 'INTERNAL_API_KEY', 'test-key')
class SendTextTests(unittest.TestCase):
    def send(self, status=200, body=None, error=None):
        self.requests = []

        def handler(request):
            self.requests.append(request)
            if error is not None:
                raise error
            return httpx.Response(status, json=body if body is not None else {'message_id': 'wamid.out1'})

        return send_text(5, '+6591234567', 'Hello!', transport=httpx.MockTransport(handler))

    def test_calls_the_internal_send_endpoint(self):
        self.assertEqual(self.send(), 'wamid.out1')
        request = self.requests[0]
        self.assertEqual((request.method, str(request.url)), ('POST', 'http://configuration.example/api/internal/whatsapp/5/send/'))
        self.assertEqual(request.headers['X-Internal-Api-Key'], 'test-key')
        self.assertEqual(json.loads(request.content), {'to': '+6591234567', 'text': 'Hello!'})

    def test_failures(self):
        for kwargs in ({'status': 503, 'body': {'detail': 'Could not reach Meta'}}, {'status': 404, 'body': {'detail': 'x'}},
                       {'body': {}}, {'error': httpx.ConnectError('down')}):
            with self.subTest(**{k: str(v) for k, v in kwargs.items()}), self.assertRaises(SendError):
                self.send(**kwargs)
