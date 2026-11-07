"""Answering WhatsApp messages from Pub/Sub with the chat flow (app/inbound.py), on SQLite with the
LLM mocked (the Pub/Sub side is in test_consumer.py)."""

import json
from unittest.mock import MagicMock, patch

from app import llm
from app.consumer import ConsumerStats, handle
from app.inbound import UNSUPPORTED_REPLY, handle_inbound
from app.models import ChatSession, InboundMessage, OutboundMessage, Product

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
        sender = patch('app.whatsapp_sender.send_text', return_value='wamid.out1')
        self.send_text = sender.start()
        self.addCleanup(sender.stop)

    def answer(self, **changes):
        with self.assertLogs('app.outbox', level='INFO') as logs:
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
        self.assertEqual(session.version, 2)  # created at 0, the message, the reply
        record, = self.all(InboundMessage)
        self.assertEqual((record.message_id, record.status, record.chat_session_id), ('wamid.1', 'replied', session.id))
        self.assertIsNotNone(record.replied_time)
        self.send_text.assert_called_once_with(self.cafe.id, '+6591234567', 'Yes, we do! A whole cake is $25.')
        self.assertIn('sent to +6591234567 on WhatsApp (wamid.out1)', logs[-1])
        # The reply went through the outbox, saved with the chat.
        sent, = self.all(OutboundMessage)
        self.assertEqual(
            (sent.chat_session_id, sent.inbound_message_id, sent.text, sent.status, sent.attempts, sent.meta_message_id),
            (session.id, record.id, 'Yes, we do! A whole cake is $25.', 'sent', 1, 'wamid.out1'),
        )
        self.assertIsNotNone(sent.sent_time)

    def test_a_failed_send_stays_in_the_outbox_to_retry(self):
        from app.whatsapp_sender import SendError

        self.send_text.side_effect = SendError('Not sent (503): Could not reach Meta')
        with self.assertLogs('app.outbox', level='WARNING') as logs:
            result = handle_inbound(self.sessions, self.payload)
        self.assertEqual(result.outcome, 'replied')  # acked: the reply is safe in the outbox
        self.assertIn('not sent to +6591234567 (attempt 1 of 5)', logs.output[-1])
        self.assertEqual(self.all(InboundMessage)[0].status, 'replied')
        self.assertEqual(self.all(ChatSession)[0].chat_message_json[-1]['sent_by'], 'business-automated')
        pending, = self.all(OutboundMessage)
        self.assertEqual((pending.status, pending.attempts, pending.sent_time), ('pending', 1, None))
        self.assertIn('Not sent (503)', pending.last_error)
        self.assertGreater(pending.next_attempt_time, pending.created_time)

    def test_answered_by_another_worker_meanwhile_nothing_more_is_saved_or_sent(self):
        # While this worker's LLM answers, another worker (a duplicate delivery) answers the message.
        fake = fake_ollama_chat('Yes, we do!')

        def chat(**kwargs):
            with self.sessions.begin() as db:
                record = db.query(InboundMessage).one()
                record.status, record.replied_time = 'replied', record.received_time
            return fake(**kwargs)

        self.ollama.chat.side_effect = chat
        result = handle_inbound(self.sessions, self.payload)
        self.assertEqual((result.outcome, result.reason), ('skipped', 'answered by another worker meanwhile (a duplicate)'))
        self.assertEqual([m['sent_by'] for m in self.all(ChatSession)[0].chat_message_json], ['customer'])
        self.assertEqual(self.all(OutboundMessage), [])
        self.send_text.assert_not_called()

    def test_a_placed_order_is_confirmed_even_if_answered_meanwhile(self):
        # The turn placed an order (saved already) when it finds the message answered by another
        # worker: its confirmation (with the payment link) must still be sent.
        from app.chat_flow import flow

        real = flow.handle_customer_message

        def placed_meanwhile(sessions, session_id, message, save_message=True, on_saved=None):
            def answered_first(db, session, messages, placed):
                record = db.query(InboundMessage).one()
                record.status, record.replied_time = 'replied', record.received_time
                on_saved(db, session, messages, True)
            return real(sessions, session_id, message, save_message=save_message, on_saved=answered_first)

        with patch('app.inbound.flow.handle_customer_message', side_effect=placed_meanwhile), \
                self.assertLogs('app.inbound', level='WARNING') as logs:
            result = handle_inbound(self.sessions, self.payload)
        self.assertEqual(result.outcome, 'replied')
        self.assertIn("sending this turn's confirmation too", logs.output[0])
        self.assertEqual([item.status for item in self.all(OutboundMessage)], ['sent'])

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

    def test_an_empty_text_or_an_unknown_business_is_skipped(self):
        for changes, reason in (
            ({'text': '   '}, 'an empty text message'),
            ({'business_id': 999}, 'no business 999'),
            ({'type': 'image', 'text': None, 'business_id': 999}, 'no business 999'),
        ):
            with self.subTest(changes=changes):
                result = handle_inbound(self.sessions, {**self.payload, **changes})
                self.assertEqual((result.outcome, result.reason), ('skipped', reason))
        self.assertEqual((self.all(ChatSession), self.all(InboundMessage), self.all(OutboundMessage)), ([], [], []))
        self.ollama.chat.assert_not_called()
        self.send_text.assert_not_called()

    def test_a_photo_is_saved_and_answered_that_only_text_is_read(self):
        result, logs = self.answer(type='image', text=None)
        self.assertEqual((result.outcome, result.reason, result.reply), ('replied', 'not a text message (image)', UNSUPPORTED_REPLY))
        self.ollama.chat.assert_not_called()  # no LLM: a fixed reply
        session, = self.all(ChatSession)
        self.assertEqual(
            [(m['sent_by'], m['message']) for m in session.chat_message_json],
            [('customer', '[Photo]'), ('business-automated', UNSUPPORTED_REPLY)],
        )
        self.assertEqual((session.display_name, session.chat_state_id), ('Alice', 'start'))
        record, = self.all(InboundMessage)
        self.assertEqual((record.message_id, record.status, record.chat_session_id), ('wamid.1', 'replied', session.id))
        self.assertIsNotNone(record.replied_time)
        sent, = self.all(OutboundMessage)
        self.assertEqual(
            (sent.inbound_message_id, sent.text, sent.status, sent.meta_message_id), (record.id, UNSUPPORTED_REPLY, 'sent', 'wamid.out1'),
        )
        self.send_text.assert_called_once_with(self.cafe.id, '+6591234567', UNSUPPORTED_REPLY)
        self.assertIn('sent to +6591234567 on WhatsApp (wamid.out1)', logs[-1])

    def test_every_kind_that_isnt_text_gets_a_placeholder(self):
        for number, (message_type, placeholder) in enumerate((
            ('document', '[Document]'), ('audio', '[Voice message]'), ('video', '[Video]'), ('sticker', '[Sticker]'),
            ('location', '[Location]'), ('contacts', '[Contact]'), ('reaction', '[Reaction]'), ('system', '[System notice]'),
            ('unsupported', '[Message]'),
        )):
            with self.subTest(message_type=message_type):
                self.answer(type=message_type, text=None, message_id=f'wamid.{message_type}', **{'from': f'+659000000{number}'})
                session = self.all(ChatSession, ChatSession.phone_number == f'+659000000{number}')[0]
                self.assertEqual([m['message'] for m in session.chat_message_json], [placeholder, UNSUPPORTED_REPLY])

    def test_a_photo_in_an_existing_chat_leaves_its_step_alone(self):
        existing = self.make.session(self.cafe, phone_number='+6591234567', is_sandbox=False)
        with self.sessions.begin() as db:
            chat = db.get(ChatSession, existing.id)
            chat.chat_state_id, chat.chat_state_data = 'product_selection', {'items': [{'product_id': 1}]}
        self.answer(type='image', text=None)
        chat = self.get(ChatSession, existing.id)
        self.assertEqual((chat.chat_state_id, chat.chat_state_data), ('product_selection', {'items': [{'product_id': 1}]}))
        self.assertEqual(len(chat.chat_message_json), 2)

    def test_a_duplicate_photo_is_answered_once(self):
        self.answer(type='image', text=None)
        result = handle_inbound(self.sessions, {**self.payload, 'type': 'image', 'text': None})
        self.assertEqual((result.outcome, result.reason), ('skipped', 'already replied (a duplicate)'))
        self.assertEqual(len(self.all(ChatSession)[0].chat_message_json), 2)
        self.assertEqual(len(self.all(OutboundMessage)), 1)
        self.send_text.assert_called_once()

    def test_a_failed_send_of_the_photo_reply_stays_in_the_outbox(self):
        from app.whatsapp_sender import SendError

        self.send_text.side_effect = SendError('Not sent (503): Could not reach Meta')
        with self.assertLogs('app.outbox', level='WARNING'):
            result = handle_inbound(self.sessions, {**self.payload, 'type': 'image', 'text': None})
        self.assertEqual(result.outcome, 'replied')  # acked: the reply is safe in the outbox
        pending, = self.all(OutboundMessage)
        self.assertEqual((pending.text, pending.status, pending.attempts), (UNSUPPORTED_REPLY, 'pending', 1))
        self.assertEqual(self.all(InboundMessage)[0].status, 'replied')

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
        with patch('app.llm.get_client', return_value=ollama), patch('app.whatsapp_sender.send_text', return_value='w1'), \
                self.assertLogs('app', level='INFO') as logs:
            handle(pulled, stats, self.sessions)
        self.assertTrue(pulled.acked)
        self.assertEqual(stats.handled, 1)
        session = self.all(ChatSession)[0]
        self.assertEqual(session.chat_message_json[-1]['message'], 'Hello!')
        # Latency: every line knows the message; the end-to-end one includes sending the reply.
        latency_lines = [line for line in logs.output if '[LATENCY]' in line]
        self.assertTrue(all(f'channel=whatsapp business={cafe.id} msg=wamid.1' in line for line in latency_lines))
        tags = [line.split('app.latency:', 1)[1].split(' ', 1)[0] for line in latency_lines]
        self.assertEqual(tags[-4:], ['[LATENCY][TURN]', '[LATENCY][SEND]', '[LATENCY][E2E]', '[LATENCY][SUMMARY]'])
        self.assertIn(f'chat={session.pk}', latency_lines[-3])
        self.assertIn('outcome=replied', latency_lines[-2])
        self.assertIn(' send=', latency_lines[-1])


class SaveTurnPlacedTests(DatabaseTestCase):
    """flow.save_turn tells its hook whether the turn placed an order / booking, not only tried."""

    def test_placed_is_passed_through(self):
        from app.chat_flow import flow

        cafe = self.make.business('Kopi Café')
        session = self.make.session(cafe, phone_number='+6591234567', is_sandbox=False)
        calls = []
        for placed in (False, True):
            with self.subTest(placed=placed):
                version = self.get(ChatSession, session.id).version
                flow.save_turn(
                    self.sessions, session.id, None, ['Hello!'], version, check=False,
                    on_saved=lambda db, s, messages, placed: calls.append(placed), placed=placed,
                )
        self.assertEqual(calls, [False, True])
