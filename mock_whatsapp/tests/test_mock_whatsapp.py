import hashlib
import hmac
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

from app import config, create_app, db, meta

KOPI = {
    'business_id': 1, 'name': 'Kopi & Co. Café', 'waba_id': '200000000000001', 'phone_number_id': '100000000000001',
    'display_phone_number': '+65 8832 3212', 'access_token': 'dev-access-token-1', 'app_secret': 'dev-app-secret-1',
    'verify_token': 'dev-verify-token-1',
}


class MockTestCase(unittest.TestCase):
    def setUp(self):
        folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, folder, ignore_errors=True)
        (folder / 'businesses.json').write_text(json.dumps([KOPI]))
        for name, value in (('DB_PATH', folder / 'db.sqlite3'), ('BUSINESSES_FILE', folder / 'businesses.json'),
                            ('INGESTER_URL', 'http://ingester.example')):
            patcher = patch.object(config, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.client = TestClient(create_app())


class WebhookTests(unittest.TestCase):
    def test_payload_in_metas_format(self):
        payload = meta.webhook_payload(KOPI, '6591234567', 'Alice Tan', 'wamid.X', 'Hi!', timestamp=1760000000)
        self.assertEqual(payload, {
            'object': 'whatsapp_business_account',
            'entry': [{'id': '200000000000001', 'changes': [{'field': 'messages', 'value': {
                'messaging_product': 'whatsapp',
                'metadata': {'display_phone_number': '6588323212', 'phone_number_id': '100000000000001'},
                'contacts': [{'profile': {'name': 'Alice Tan'}, 'wa_id': '6591234567'}],
                'messages': [{'from': '6591234567', 'id': 'wamid.X', 'timestamp': '1760000000', 'type': 'text', 'text': {'body': 'Hi!'}}],
            }}]}],
        })
        self.assertTrue(meta.new_wamid().startswith('wamid.'))

    def test_signed_over_the_exact_bytes_sent(self):
        requests = []

        def handler(request):
            requests.append(request)
            return httpx.Response(200, json={'published': 1})

        payload = meta.webhook_payload(KOPI, '6591234567', 'Alice', 'wamid.X', 'Hi!')
        with patch.object(config, 'INGESTER_URL', 'http://ingester.example'):
            meta.send_to_webhook(KOPI, payload, transport=httpx.MockTransport(handler))
        request = requests[0]
        self.assertEqual(str(request.url), 'http://ingester.example/webhook/1')
        expected = 'sha256=' + hmac.new(b'dev-app-secret-1', request.content, hashlib.sha256).hexdigest()
        self.assertEqual(request.headers['X-Hub-Signature-256'], expected)
        self.assertEqual(json.loads(request.content), payload)

    def test_a_refused_webhook_is_an_error(self):
        transport = httpx.MockTransport(lambda request: httpx.Response(401, json={'code': 401}))
        with self.assertRaises(meta.WebhookError):
            meta.send_to_webhook(KOPI, {}, transport=transport)


class SendTests(MockTestCase):
    def test_a_message_is_sent_to_the_webhook_and_stored(self):
        with patch('app.meta.send_to_webhook') as send:
            response = self.client.post('/api/messages', json={'wa_id': '6591234567', 'phone_number_id': '100000000000001', 'text': ' Hi! '})
        self.assertEqual(response.status_code, 200)
        self.assertEqual((response.json()['status'], response.json()['text'], response.json()['from_customer']), ('sent', 'Hi!', True))
        business, payload = send.call_args.args
        self.assertEqual(business['business_id'], 1)
        self.assertEqual(payload['entry'][0]['changes'][0]['value']['contacts'][0]['profile']['name'], 'Alice Tan')

    def test_a_failed_webhook_marks_the_message_failed(self):
        with patch('app.meta.send_to_webhook', side_effect=meta.WebhookError('The webhook answered 503')):
            body = self.client.post('/api/messages', json={'wa_id': '6591234567', 'phone_number_id': '100000000000001', 'text': 'Hi'}).json()
        self.assertEqual((body['status'], body['error']), ('failed', 'The webhook answered 503'))

    def test_new_customers(self):
        alice = self.client.post('/api/customers', json={'name': 'Cara', 'wa_id': '+65 9000 0001'}).json()
        self.assertEqual(alice['wa_id'], '6590000001')
        random = self.client.post('/api/customers', json={'name': 'Dan'}).json()
        self.assertRegex(random['wa_id'], r'^65[89]\d{7}$')
        self.assertEqual(self.client.post('/api/customers', json={'name': 'X', 'wa_id': '+65 9000 0001'}).status_code, 400)


class GraphApiTests(MockTestCase):
    def send(self, body=None, token='dev-access-token-1', proof=None, phone_number_id='100000000000001'):
        params = {} if proof is None else {'appsecret_proof': proof}
        return self.client.post(
            f'/v25.0/{phone_number_id}/messages', params=params, headers={'Authorization': f'Bearer {token}'},
            json=body if body is not None else {
                'messaging_product': 'whatsapp', 'recipient_type': 'individual', 'to': '6591234567',
                'type': 'text', 'text': {'preview_url': False, 'body': 'Yes, we do!'},
            },
        )

    def test_a_reply_is_stored_and_answered_like_meta(self):
        proof = hmac.new(b'dev-app-secret-1', b'dev-access-token-1', hashlib.sha256).hexdigest()
        response = self.send(proof=proof)
        self.assertEqual(response.status_code, 200)
        wamid = response.json()['messages'][0]['id']
        self.assertEqual(response.json()['contacts'], [{'input': '6591234567', 'wa_id': '6591234567'}])
        reply, = db.messages('6591234567', '100000000000001')
        self.assertEqual((reply['wamid'], reply['text'], reply['from_customer'], reply['status']), (wamid, 'Yes, we do!', False, 'received'))
        # The page's poll gets it.
        self.assertEqual(self.client.get('/api/messages', params={'as': '6591234567', 'chat': '100000000000001'}).json()[0]['id'], reply['id'])

    def test_a_reply_to_a_new_number_creates_the_customer(self):
        self.assertEqual(self.send({**self.body(), 'to': '6580000000'}).status_code, 200)
        self.assertIsNotNone(db.customer('6580000000'))

    @staticmethod
    def body():
        return {'messaging_product': 'whatsapp', 'to': '6591234567', 'type': 'text', 'text': {'body': 'Hi'}}

    def test_errors_like_meta(self):
        cases = [
            (self.send(token='wrong'), 401, 190),
            (self.send(proof='wrong'), 400, 100),
            (self.send(phone_number_id='999'), 400, 100),
            (self.send({**self.body(), 'type': 'image'}), 400, 100),
        ]
        for response, status, code in cases:
            with self.subTest(status=status, code=code):
                self.assertEqual((response.status_code, response.json()['error']['code']), (status, code))
        self.assertEqual(db.messages('6591234567', '100000000000001'), [])

    def test_phone_number_details(self):
        response = self.client.get('/v25.0/100000000000001', params={'fields': 'display_phone_number,verified_name'},
                                   headers={'Authorization': 'Bearer dev-access-token-1'})
        self.assertEqual(response.json(), {'display_phone_number': '+65 8832 3212', 'verified_name': 'Kopi & Co. Café', 'id': '100000000000001'})


class PageTests(MockTestCase):
    def test_the_page_lists_the_customers_and_businesses(self):
        db.add_message('wamid.1', '6591234567', '100000000000001', True, 'Hello there', 'sent')
        page = self.client.get('/?as=6591234567&chat=100000000000001')
        self.assertEqual(page.status_code, 200)
        for text in ('Alice Tan · +65 9123 4567', 'Kopi &amp; Co. Café', 'Hello there', '+65 8832 3212'):
            self.assertIn(text, page.text)


class SampleCustomerTests(MockTestCase):
    def test_five_sample_customers_and_added_to_an_existing_database(self):
        self.assertEqual([c['name'] for c in db.customers()], ['Alice Tan', 'Ben Lim', 'Chloe Ng', 'Daniel Koh', 'Emily Wong'])
        with db.connect() as connection:
            connection.execute("DELETE FROM customers WHERE name IN ('Chloe Ng', 'Daniel Koh', 'Emily Wong')")
        db.add_customer('Mine', '6590000001')
        db.init()  # a database from before: the missing samples are added, yours kept
        self.assertEqual(
            {c['name'] for c in db.customers()}, {'Alice Tan', 'Ben Lim', 'Chloe Ng', 'Daniel Koh', 'Emily Wong', 'Mine'}
        )


if __name__ == '__main__':
    unittest.main()
