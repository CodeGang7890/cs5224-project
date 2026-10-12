"""Answering WhatsApp messages from Pub/Sub with the chat flow (app/inbound.py), on SQLite with the
LLM mocked (the Pub/Sub side is in test_consumer.py)."""

import json
from unittest.mock import MagicMock, patch

from app import llm
from app.consumer import ConsumerStats, handle
from app.inbound import handle_inbound
from app.models import ChatSession, InboundMessage, Product

from .chat_helpers import DatabaseTestCase, fake_ollama_chat

PAYLOAD = {
    'business_id': None,  # set in setUp
    'phone_number_id': '1359207187280395',
    'message_id': 'wamid.1',
    'from': '+6591234567',
    'display_name': 'Alice',
    'type': 'text',
    'text': 'Hi! Do you have pandan chiffon cake?',
    'timestamp': '2026-10-07T09:45:59+00:00',
}


class InboundTests(DatabaseTestCase):
    def setUp(self):
        super().setUp()
        self.cafe = self.make.business('Kopi Café')
        self.make.product(self.cafe, 'Pandan Chiffon Cake', '25.00', total_quantity=5)
        self.payload = {**PAYLOAD, 'business_id': self.cafe.id}
        self.ollama = MagicMock()
        patcher = patch('app.llm.get_client', return_value=self.ollama)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.ollama.chat.side_effect = fake_ollama_chat('Yes, we do! A whole cake is $25.')

    def answer(self, **changes):
        with self.assertLogs('app.inbound', level='INFO') as logs:
            result = handle_inbound(self.sessions, {**self.payload, **changes})
        return result, logs.output

    def test_a_new_customer_gets_a_chat_and_a_reply(self):
        result, logs = self.answer()
        self.assertEqual((result.outcome, result.reply), ('replied', 'Yes, we do! A whole cake is $25.'))
        session, = self.all(ChatSession)
        self.assertEqual(
            (session.business_id, session.phone_number, session.is_sandbox, session.display_name, session.chat_state_id),
            (self.cafe.id, '+6591234567', False, 'Alice', 'start'),
        )
        self.assertEqual(
            [(m['sent_by'], m['message']) for m in session.chat_message_json],
            [('customer', 'Hi! Do you have pandan chiffon cake?'), ('business-automated', 'Yes, we do! A whole cake is $25.')],
        )
        record, = self.all(InboundMessage)
        self.assertEqual((record.message_id, record.status, record.chat_session_id), ('wamid.1', 'replied', session.id))
        self.assertIsNotNone(record.replied_time)
        self.assertIn('TODO: send to +6591234567 on WhatsApp', logs[-1])

    def test_an_existing_chat_is_used(self):
        existing = self.make.session(self.cafe, phone_number='+6591234567', is_sandbox=False, display_name='Al')
        self.make.session(self.cafe, phone_number='+6591234567', is_sandbox=True)  # a sandbox chat: not this one
        result, _ = self.answer()
        self.assertEqual(result.chat_session_id, existing.id)
        self.assertEqual(len(self.all(ChatSession)), 2)
        self.assertEqual(self.get(ChatSession, existing.id).display_name, 'Al')

    def test_a_duplicate_is_answered_once(self):
        self.answer()
        calls = self.ollama.chat.call_count
        result = handle_inbound(self.sessions, self.payload)
        self.assertEqual((result.outcome, result.reason), ('skipped', 'already replied (a duplicate)'))
        self.assertEqual(self.ollama.chat.call_count, calls)  # no LLM call
        self.assertEqual(len(self.all(ChatSession)[0].chat_message_json), 2)

    def test_redelivered_after_a_failure_the_message_is_not_saved_twice(self):
        self.ollama.chat.side_effect = ConnectionError('Ollama is down')
        with self.assertRaises(llm.LLMUnavailableError):
            handle_inbound(self.sessions, self.payload)
        self.assertEqual(self.all(InboundMessage)[0].status, 'received')
        self.ollama.chat.side_effect = fake_ollama_chat('Yes, we do!')
        result, _ = self.answer()
        self.assertEqual(result.outcome, 'replied')
        messages = self.all(ChatSession)[0].chat_message_json
        self.assertEqual([m['sent_by'] for m in messages], ['customer', 'business-automated'])
        self.assertEqual(self.all(InboundMessage)[0].status, 'replied')

    def test_not_text_or_an_unknown_business_is_skipped(self):
        for changes, reason in (
            ({'type': 'image', 'text': None}, 'not a text message (image)'),
            ({'text': '   '}, 'not a text message (text)'),
            ({'business_id': 999}, 'no business 999'),
        ):
            with self.subTest(changes=changes):
                result = handle_inbound(self.sessions, {**self.payload, **changes})
                self.assertEqual((result.outcome, result.reason), ('skipped', reason))
        self.assertEqual((self.all(ChatSession), self.all(InboundMessage)), ([], []))
        self.ollama.chat.assert_not_called()

    def test_an_order_from_whatsapp(self):
        cake, = self.all(Product, Product.name == 'Pandan Chiffon Cake')
        self.ollama.chat.side_effect = fake_ollama_chat(
            'Got it!', [{'items': [{'product_id': cake.id, 'quantity': 1}], 'done_choosing': False}], intents=['order']
        )
        result, _ = self.answer(text='1 pandan chiffon cake please')
        self.assertEqual(result.outcome, 'replied')
        session = self.all(ChatSession)[0]
        self.assertEqual(session.chat_state_id, 'product_selection')
        self.assertEqual(session.chat_state_data['items'][0]['name'], 'Pandan Chiffon Cake')


class ConsumerToChatFlowTests(DatabaseTestCase):
    """A pulled Pub/Sub message, through the consumer's callback, to a saved reply."""

    def test_end_to_end(self):
        cafe = self.make.business('Kopi Café')

        class Pulled:
            data = json.dumps({**PAYLOAD, 'business_id': cafe.id}).encode()
            message_id = 'pubsub-1'
            acked = nacked = False

            def ack(self):
                self.acked = True

            def nack(self):
                self.nacked = True

        pulled, stats, ollama = Pulled(), ConsumerStats(), MagicMock()
        ollama.chat.side_effect = fake_ollama_chat('Hello!')
        with patch('app.llm.get_client', return_value=ollama), self.assertLogs('app', level='INFO'):
            handle(pulled, stats, self.sessions)
        self.assertTrue(pulled.acked)
        self.assertEqual(stats.handled, 1)
        self.assertEqual(self.all(ChatSession)[0].chat_message_json[-1]['message'], 'Hello!')
