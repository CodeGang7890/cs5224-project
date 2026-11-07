"""Messages sent close together get one reply (app/inbound.py, step 4): a turn answers every
customer message in the chat since the business's last one, and marks them all `replied`, so the
other messages' turns stop without an LLM call. On SQLite with the LLM mocked; "at the same time"
is a message handled from inside another turn's LLM call."""

from unittest.mock import MagicMock, patch

from datetime import timedelta

from app import config, llm
from app.chat_flow import dates, flow, order_flow
from app.chat_flow.constants import UNSUPPORTED_REPLY
from app.chat_flow.dates import parse_datetime
from app.chat_flow.validators import validate_chat_messages
from app.inbound import handle_inbound
from app.models import ChatSession, InboundMessage, OutboundMessage

from .chat_helpers import DatabaseTestCase, fake_ollama_chat, is_question_check, is_router

PAYLOAD = {
    'business_id': None,  # set in setUp
    'phone_number_id': '1359207187280395',
    'from': '+6591234567',
    'display_name': 'Alice',
    'type': 'text',
    'timestamp': '2026-10-07T09:45:59+00:00',
}


class BundlingTestCase(DatabaseTestCase):
    def setUp(self):
        super().setUp()
        self.cafe = self.make.business('Kopi Café')
        self.cake = self.make.product(self.cafe, 'Pandan Chiffon Cake', '25.00', total_quantity=5, information='Contains eggs.')
        self.ollama = MagicMock()
        patcher = patch('app.llm.get_client', return_value=self.ollama)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.answer = fake_ollama_chat('Sure!')
        self.ollama.chat.side_effect = self.answer
        payment = patch('app.payment_client.create_payment', return_value={
            'xendit_payment_id': 'pay_test', 'payment_url': 'https://pay.xendit.co/test',
        })  # payment-ingester isn't real in tests
        payment.start()
        self.addCleanup(payment.stop)
        sender = patch('app.whatsapp_sender.send_text', side_effect=lambda business_id, to, text: f'wamid.out.{text[:5]}')
        self.send_text = sender.start()
        self.addCleanup(sender.stop)

    def payload(self, message_id, text, **changes):
        return {**PAYLOAD, 'business_id': self.cafe.id, 'message_id': message_id, 'text': text, **changes}

    def handle(self, message_id, text, **changes):
        return handle_inbound(self.sessions, self.payload(message_id, text, **changes))

    def save_only(self, message_id, text, **changes):
        """The message saved (InboundMessage `received`), but its turn fails (the LLM is down): as
        if it had just arrived and its turn hadn't finished yet."""
        previous = self.ollama.chat.side_effect
        self.ollama.chat.side_effect = ConnectionError('Ollama is down')
        try:
            with self.assertRaises(llm.LLMUnavailableError):
                self.handle(message_id, text, **changes)
        finally:
            self.ollama.chat.side_effect = previous

    def statuses(self):
        return {r.message_id: r.status for r in self.all(InboundMessage)}

    def chat(self):
        session, = self.all(ChatSession)
        return [(m['sent_by'], m['message']) for m in session.chat_message_json]

    def router_calls(self):
        return [c.kwargs for c in self.ollama.chat.call_args_list if is_router(c.kwargs)]


class BundlingTests(BundlingTestCase):
    def test_a_message_arriving_during_a_turn_is_answered_with_it(self):
        # m1's turn is running (its router call) when m2 comes in and is saved: m1's turn then runs
        # again on the chat as it is now, and its one reply answers both.
        arrived = []

        def chat(**kwargs):
            if is_router(kwargs) and not arrived:
                arrived.append(True)
                self.save_only('wamid.2', 'and a Kopi C please')
            return self.answer(**kwargs)

        self.ollama.chat.side_effect = chat
        result = self.handle('wamid.1', 'Hi! Do you have pandan chiffon cake?')
        self.assertEqual(result.outcome, 'replied')
        self.assertEqual(self.chat(), [
            ('customer', 'Hi! Do you have pandan chiffon cake?'), ('customer', 'and a Kopi C please'), ('business-automated', 'Sure!'),
        ])
        self.assertEqual(self.statuses(), {'wamid.1': 'replied', 'wamid.2': 'replied'})
        outbound, = self.all(OutboundMessage)  # one reply, sent once
        self.assertEqual((outbound.text, outbound.status), ('Sure!', 'sent'))
        self.send_text.assert_called_once()
        # The second attempt (after the chat changed) saw both messages.
        self.assertEqual(
            [m['content'] for m in self.router_calls()[-1]['messages'][1:]],
            ['Hi! Do you have pandan chiffon cake?', 'and a Kopi C please'],
        )

        # m2's own delivery (redelivered after its failed attempt, or still in flight): answered already.
        self.ollama.reset_mock()
        again = self.handle('wamid.2', 'and a Kopi C please')
        self.assertEqual((again.outcome, again.reason), ('skipped', 'already replied (a duplicate)'))
        self.ollama.chat.assert_not_called()
        self.assertEqual(len(self.all(OutboundMessage)), 1)

    def test_a_later_message_whose_turn_finishes_first_answers_both(self):
        # m2's whole turn runs (and replies to both) while m1's turn is in its router call: m1's
        # turn then stops before trying again, without another LLM call.
        def chat(**kwargs):
            if is_router(kwargs) and len(self.router_calls()) == 1:
                second = self.handle('wamid.2', 'and a Kopi C please')
                self.assertEqual(second.outcome, 'replied')
            return self.answer(**kwargs)

        self.ollama.chat.side_effect = chat
        first = self.handle('wamid.1', 'Hi! Do you have pandan chiffon cake?')
        self.assertEqual((first.outcome, first.reason), ('skipped', 'answered meanwhile (with another message, or a duplicate)'))
        self.assertEqual(self.statuses(), {'wamid.1': 'replied', 'wamid.2': 'replied'})
        self.assertEqual([m for m in self.chat() if m[0] != 'customer'], [('business-automated', 'Sure!')])
        self.assertEqual(len(self.all(OutboundMessage)), 1)
        self.assertEqual(len(self.router_calls()), 2)  # m1's first attempt and m2's turn: m1 didn't run again

    def test_messages_saved_earlier_are_answered_by_the_next_turn(self):
        # Two messages saved while their turns failed (e.g. the LLM was down): the next turn answers
        # them all, and the earlier ones' redeliveries are skipped.
        self.save_only('wamid.1', 'Do you have pandan chiffon cake?')
        self.save_only('wamid.2', 'Does it have eggs?')
        self.ollama.reset_mock()
        self.ollama.chat.side_effect = fake_ollama_chat(
            'Yes, it contains eggs.', intents=['question'], question_check={'kind': 'answered', 'question': 'Does it have eggs?'},
        )
        result = self.handle('wamid.3', 'thanks!')
        self.assertEqual(result.outcome, 'replied')
        self.assertEqual(self.statuses(), {'wamid.1': 'replied', 'wamid.2': 'replied', 'wamid.3': 'replied'})
        # The question check read all three (the cake is named in the first), not only "thanks!".
        check = next(c.kwargs for c in self.ollama.chat.call_args_list if is_question_check(c.kwargs))
        self.assertIn('## Details of Pandan Chiffon Cake\nContains eggs.', check['messages'][0]['content'])
        self.ollama.reset_mock()
        for message_id in ('wamid.1', 'wamid.2'):
            with self.subTest(message_id=message_id):
                self.assertEqual(self.handle(message_id, 'again').outcome, 'skipped')
        self.ollama.chat.assert_not_called()
        self.assertEqual(len(self.all(OutboundMessage)), 1)

    def test_the_welcome_message_goes_to_a_first_burst(self):
        # The business hasn't written yet: the turn answering the first two messages starts with the welcome.
        self.make.chat_config(self.cafe, welcome_message='Welcome to {business_name}!')
        self.save_only('wamid.1', 'hi')
        self.ollama.chat.side_effect = fake_ollama_chat(
            'Sure!', intents=['question'], question_check={'kind': 'answered', 'question': 'Do you have cake?'},
        )  # something to do: the welcome, then the reply (with no intent, the welcome would be all of it)
        self.handle('wamid.2', 'do you have cake?')
        self.assertEqual([m for m in self.chat() if m[0] != 'customer'][0], ('business-automated', 'Welcome to Kopi Café!'))
        self.assertEqual([o.text for o in self.all(OutboundMessage)], ['Welcome to Kopi Café!', 'Sure!'])
        self.handle('wamid.3', 'thanks')  # not again
        self.assertEqual(sum(1 for m in self.chat() if m[1] == 'Welcome to Kopi Café!'), 1)

    def test_only_this_chats_messages(self):
        # Another customer's waiting message isn't answered by this chat's turn.
        self.save_only('wamid.bob', 'hello from Bob')
        with self.sessions.begin() as db:
            bob = db.query(InboundMessage).one()
            bob_chat = bob.chat_session_id
        self.handle('wamid.alice', 'hello from Alice', **{'from': '+6598765432', 'display_name': 'Alice'})
        self.assertEqual(self.statuses(), {'wamid.bob': 'received', 'wamid.alice': 'replied'})
        self.assertEqual(self.get(ChatSession, bob_chat).chat_message_json[-1]['message'], 'hello from Bob')

    def test_a_photo_in_between_answers_only_itself(self):
        # The fixed "text only" reply doesn't answer a waiting text message: its turn still does.
        self.save_only('wamid.1', 'Do you have cake?')
        photo = self.handle('wamid.photo', None, type='image')
        self.assertEqual(photo.outcome, 'replied')
        self.assertEqual(self.statuses(), {'wamid.1': 'received', 'wamid.photo': 'replied'})
        self.assertEqual(self.handle('wamid.1', 'Do you have cake?').outcome, 'replied')  # its redelivery
        self.assertEqual(self.statuses(), {'wamid.1': 'replied', 'wamid.photo': 'replied'})

    def test_a_message_arriving_while_an_order_is_placed_gets_its_own_reply(self):
        # Once placed, the order's confirmation is saved even though the chat changed meanwhile:
        # the message that came in then wasn't seen by that turn, so it isn't marked replied.
        line = {'product_id': self.cake.id, 'name': 'Pandan Chiffon Cake', 'unit_price': '25.00', 'quantity': 1}
        self.make.session(self.cafe, phone_number='+6591234567', is_sandbox=False, chat_state_id='confirmation',
                          chat_state_data={'items': [line], 'details': {'name': 'Alice', 'email': 'alice@example.com'}})
        self.ollama.chat.side_effect = fake_ollama_chat('OK!', [{'decision': 'confirm'}], intents=['order'])
        real = flow.payments.store_payment_for_placed

        def placed_then_message(*args, **kwargs):  # after the order is saved, before the reply is
            self.save_only('wamid.2', 'can I also get a Kopi C?')
            self.ollama.chat.side_effect = fake_ollama_chat('OK!', [{'decision': 'confirm'}], intents=['order'])
            return real(*args, **kwargs)

        with patch('app.chat_flow.flow.payments.store_payment_for_placed', side_effect=placed_then_message), \
                self.assertLogs('app.chat_flow.flow', level='WARNING'):
            result = self.handle('wamid.1', 'CONFIRM')
        self.assertEqual(result.outcome, 'replied')
        self.assertIn('is confirmed', result.reply)
        self.assertIn('https://pay.xendit.co/test', result.reply)  # the payment link (faked)
        self.assertEqual(self.statuses(), {'wamid.1': 'replied', 'wamid.2': 'received'})  # not answered yet
        # Its own delivery answers it.
        self.assertEqual(self.handle('wamid.2', 'can I also get a Kopi C?').outcome, 'replied')
        self.assertEqual(self.statuses(), {'wamid.1': 'replied', 'wamid.2': 'replied'})

    def test_a_photo_during_a_burst_doesnt_hide_the_waiting_messages(self):
        # Two texts wait (their turns failed / still running) when a photo comes in and gets its fixed
        # reply at once. The texts' turn still reads them as the end of the conversation, after the
        # photo exchange, and its question check gets both.
        self.save_only('wamid.1', 'Do you have pandan chiffon cake?', timestamp='2026-10-07T09:46:01+00:00')
        self.save_only('wamid.2', 'Does it have eggs?', timestamp='2026-10-07T09:46:03+00:00')
        self.handle('wamid.photo', None, type='image', timestamp='2026-10-07T09:46:05+00:00')
        self.assertEqual([m for m, _ in [(x[1], 0) for x in self.chat()]],
                         ['Do you have pandan chiffon cake?', 'Does it have eggs?', '[Photo]', UNSUPPORTED_REPLY])  # as saved
        self.ollama.reset_mock()
        self.ollama.chat.side_effect = fake_ollama_chat(
            'Yes, it contains eggs.', intents=['question'], question_check={'kind': 'answered', 'question': 'Does it have eggs?'},
        )
        result = self.handle('wamid.1', 'Do you have pandan chiffon cake?')  # its redelivery
        self.assertEqual(result.outcome, 'replied')
        history = [(m['role'], m['content']) for m in self.router_calls()[-1]['messages'][1:]]
        self.assertEqual(history, [
            ('user', '[Photo]'), ('assistant', UNSUPPORTED_REPLY),
            ('user', 'Do you have pandan chiffon cake?'), ('user', 'Does it have eggs?'),
        ])
        check = next(c.kwargs for c in self.ollama.chat.call_args_list if is_question_check(c.kwargs))
        self.assertIn('## Details of Pandan Chiffon Cake\nContains eggs.', check['messages'][0]['content'])  # both texts
        self.assertEqual(self.statuses(), {'wamid.1': 'replied', 'wamid.2': 'replied', 'wamid.photo': 'replied'})

    def test_a_single_message_is_unchanged(self):
        result = self.handle('wamid.1', 'Hi!')
        self.assertEqual((result.outcome, result.reply), ('replied', 'Sure!'))
        self.assertEqual(self.statuses(), {'wamid.1': 'replied'})
        self.assertEqual(len(self.router_calls()), 1)


class SentOrderTests(BundlingTestCase):
    """Each WhatsApp message is put in the chat in the order it was sent (Meta's timestamp), among
    the messages not answered yet: flow.add_message's sent_time."""

    def times(self):
        session, = self.all(ChatSession)
        validate_chat_messages(session.chat_message_json)  # still chronological
        return [(m['message'], m['message_time']) for m in session.chat_message_json]

    def test_a_message_that_comes_in_later_but_was_sent_first_goes_first(self):
        self.save_only('wamid.2', 'make it 3', timestamp='2026-10-07T09:46:05+00:00')
        self.save_only('wamid.1', '2 kopi please', timestamp='2026-10-07T09:46:01+00:00')
        self.assertEqual(self.times(), [
            ('2 kopi please', '2026-10-07T09:46:01+00:00'), ('make it 3', '2026-10-07T09:46:05+00:00'),
        ])
        self.handle('wamid.3', 'thanks', timestamp='2026-10-07T09:46:09+00:00')
        history = [m['content'] for m in self.router_calls()[-1]['messages'][1:]]
        self.assertEqual(history, ['2 kopi please', 'make it 3', 'thanks'])  # the turn reads them in that order

    def test_the_same_second_keeps_the_order_they_came_in(self):
        self.save_only('wamid.1', 'first in', timestamp='2026-10-07T09:46:01+00:00')
        self.save_only('wamid.2', 'second in', timestamp='2026-10-07T09:46:01+00:00')
        self.assertEqual([m for m, _ in self.times()], ['first in', 'second in'])

    def test_never_before_a_message_already_answered(self):
        self.handle('wamid.1', 'hi', timestamp='2026-10-07T09:46:01+00:00')  # answered: 'Sure!' after it
        reply_time = self.times()[-1][1]
        self.save_only('wamid.0', 'sent before the reply, came in after it', timestamp='2026-10-07T09:46:00+00:00')
        self.assertEqual([m for m, _ in self.times()], ['hi', 'Sure!', 'sent before the reply, came in after it'])
        self.assertEqual(self.times()[-1][1], reply_time)  # not earlier than the reply

    def test_a_time_in_the_future_is_now(self):
        self.save_only('wamid.1', 'from the future', timestamp='2999-01-01T00:00:00+00:00')
        moment = parse_datetime(self.times()[0][1])
        self.assertLessEqual(moment, dates.now())
        self.handle('wamid.2', 'and now', timestamp=None)  # now: after it; the reply after both
        self.assertEqual([m for m, _ in self.times()], ['from the future', 'and now', 'Sure!'])

    def test_never_before_a_business_message_from_a_clock_ahead(self):
        # configuration-service (another clock) wrote a moment "in the future": what comes after it,
        # with a WhatsApp time or now, is never timestamped before it.
        ahead = (dates.now() + timedelta(minutes=5)).isoformat()
        self.make.session(self.cafe, phone_number='+6591234567', is_sandbox=False, chat_message_json=[
            {'message': 'Hi, the owner here.', 'sent_by': 'business-manual', 'message_time': ahead},
        ])
        self.save_only('wamid.1', 'hello', timestamp=dates.now().isoformat())
        self.handle('wamid.2', 'anyone?', timestamp=None)
        self.assertEqual([m for m, _ in self.times()], ['Hi, the owner here.', 'hello', 'anyone?', 'Sure!'])
        self.assertTrue(all(t >= ahead for _, t in self.times()[1:]))

    def test_an_unreadable_stored_time_just_appends(self):
        self.make.session(self.cafe, phone_number='+6591234567', is_sandbox=False, chat_message_json=[
            {'message': 'old', 'sent_by': 'customer', 'message_time': 'not a time'},
        ])
        self.save_only('wamid.1', 'hello', timestamp='2026-10-07T09:46:01+00:00')
        session, = self.all(ChatSession)
        self.assertEqual([m['message'] for m in session.chat_message_json], ['old', 'hello'])
        self.assertIsNotNone(parse_datetime(session.chat_message_json[-1]['message_time']))

    def test_no_or_a_bad_timestamp_is_now(self):
        self.save_only('wamid.1', 'no time', timestamp=None)
        self.save_only('wamid.2', 'bad time', timestamp='yesterday')
        self.save_only('wamid.3', 'naive time', timestamp='2026-10-07T09:46:01')
        self.assertEqual([m for m, _ in self.times()], ['no time', 'bad time', 'naive time'])


class LastAttemptTests(BundlingTestCase):
    def test_answered_meanwhile_on_the_last_attempt_is_skipped_not_a_conflict(self):
        # Every attempt finds the chat changed; by the last one, another turn has answered the message.
        self.save_only('wamid.1', 'hello')
        attempts = []

        def changed(sessions, session_id, message, on_saved=None):
            attempts.append(1)
            if len(attempts) == config.TURN_ATTEMPTS_MAX:
                with self.sessions.begin() as db:
                    db.query(InboundMessage).one().status = 'replied'
            raise order_flow.ChatChanged(session_id, 1, 2)

        with patch('app.chat_flow.flow._run_turn', side_effect=changed), self.assertLogs('app.chat_flow.flow', level='INFO'):
            result = self.handle('wamid.1', 'hello')
        self.assertEqual(len(attempts), config.TURN_ATTEMPTS_MAX)
        self.assertEqual((result.outcome, result.reason), ('skipped', 'answered meanwhile (with another message, or a duplicate)'))

    def test_still_a_conflict_if_nobody_answered_it(self):
        self.save_only('wamid.1', 'hello')
        with patch('app.chat_flow.flow._run_turn', side_effect=order_flow.ChatChanged(1, 1, 2)), \
                self.assertLogs('app.chat_flow.flow', level='INFO'), self.assertRaises(flow.ChatConflictError):
            self.handle('wamid.1', 'hello')


class ConversationTests(DatabaseTestCase):
    def test_a_non_text_exchange_among_waiting_messages_goes_before_them(self):
        def m(sent_by, message):
            return {'sent_by': sent_by, 'message': message, 'message_time': '2026-10-07T09:00:00+00:00'}

        chat = [m('customer', 'hi'), m('business-automated', 'Hello!'), m('customer', 'a'), m('customer', '[Photo]'),
                m('business-automated', UNSUPPORTED_REPLY), m('customer', 'b')]
        self.assertEqual([x['message'] for x in flow.conversation(chat)],
                         ['hi', 'Hello!', '[Photo]', UNSUPPORTED_REPLY, 'a', 'b'])
        self.assertEqual(flow.pending_text(chat), 'a\nb')
        # An answered one earlier (before the business's last real message) stays where it is.
        earlier = [m('customer', '[Photo]'), m('business-automated', UNSUPPORTED_REPLY), m('customer', 'hi'),
                   m('business-automated', 'Hello!'), m('customer', 'c')]
        self.assertEqual(flow.conversation(earlier), earlier)
        # A photo on its own: nothing waiting.
        alone = [m('customer', '[Photo]'), m('business-automated', UNSUPPORTED_REPLY)]
        self.assertEqual((flow.conversation(alone), flow.pending_text(alone)), (alone, ''))


class PendingTextTests(DatabaseTestCase):
    def test_the_customer_messages_since_the_business_last_wrote(self):
        def m(sent_by, message):
            return {'sent_by': sent_by, 'message': message, 'message_time': '2026-10-07T09:00:00+00:00'}

        self.assertEqual(flow.pending_text([]), '')
        self.assertEqual(flow.pending_text([m('customer', 'a')]), 'a')
        self.assertEqual(flow.pending_text([m('customer', 'a'), m('business-automated', 'b'), m('customer', 'c'), m('customer', 'd')]), 'c\nd')
        self.assertEqual(flow.pending_text([m('customer', 'a'), m('business-manual', 'b')]), '')
