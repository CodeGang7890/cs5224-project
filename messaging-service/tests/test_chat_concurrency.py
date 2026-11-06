"""ChatSession.version: every change adds 1, and a turn whose chat changed while the LLM was
answering (another message, the business answering in the chat) runs again (app/chat_flow/flow.py)."""

from app import config
from app.chat_flow import flow, order_flow
from app.chat_flow.constants import SENT_BY_BUSINESS_MANUAL
from app.models import ChatSession, OrderItem

from .chat_helpers import ApiTestCase, fake_ollama_chat, is_router
from .test_chat_flow import FlowApiMixin

OWNER_MESSAGE = 'Hi, the owner here: we close at 5pm today.'


def is_reply(call_kwargs: dict) -> bool:
    return not call_kwargs.get('format')


class ChatVersionCase(FlowApiMixin, ApiTestCase):
    """A sandbox chat, logged in, the LLM mocked; the owner can write in the chat during an LLM call."""

    def setUp(self):
        super().setUp()
        self.cafe = self.make.business('Kopi Café', 'Tiong Bahru')
        self.user = self.make.user(self.cafe, username='cafe')
        self.kopi = self.make.product(self.cafe, 'Kopi C', '1.80', total_quantity=10)
        self.session = self.make.session(self.cafe, is_sandbox=True)
        self.mock_llm()
        self.login(self.user)

    def owner_writes(self, message=OWNER_MESSAGE):
        """What configuration-service does when the business answers in the chat (a save: +1)."""
        flow.append_chat_message(self.sessions, self.session.id, message, SENT_BY_BUSINESS_MANUAL)

    def send_while_changing(self, message, *extractions, change_on, changes=1, reply='OK!', **fake):
        """Sends a message; the chat changes (the owner writes) during the first `changes` LLM calls
        that `change_on` matches. The extractions are shared by every attempt."""
        answer = fake_ollama_chat(reply, extractions, **fake)
        left = [changes]

        def chat(**kwargs):
            if left[0] and change_on(kwargs):
                left[0] -= 1
                self.owner_writes()
            return answer(**kwargs)

        self.ollama.reset_mock()
        self.ollama.chat.side_effect = chat
        response = self.client.post(self.messages_url(), json={'message': message})
        self.session = self.get(ChatSession, self.session.id)
        return response

    def senders(self):
        return [(item['sent_by'], item['message']) for item in self.session.chat_message_json]


class ChatVersionTests(ChatVersionCase):
    def test_a_new_chat_starts_at_version_0_and_every_change_adds_1(self):
        self.assertEqual(self.session.version, 0)
        self.owner_writes()
        self.assertEqual(self.get(ChatSession, self.session.id).version, 1)
        self.save_state(step='product_selection')
        self.assertEqual(self.session.version, 2)

    def test_a_turn_adds_1_for_the_message_and_1_for_the_reply_and_state(self):
        response = self.send('I want a Kopi C', {'items': [{'product_id': self.kopi.pk, 'quantity': 1}], 'done_choosing': False},
                             intents=['order'])
        self.assertEqual(response.status_code, 200, response.json())
        self.assertEqual(response.json()['debug']['attempts'], 1)
        self.assertEqual(self.session.version, 2)
        self.assertEqual(self.session.chat_state_id, 'product_selection')

    def test_a_change_during_the_reply_runs_the_whole_turn_again(self):
        response = self.send_while_changing(
            'I want a Kopi C',
            {'items': [{'product_id': self.kopi.pk, 'quantity': 1}], 'done_choosing': False},
            {'items': [{'product_id': self.kopi.pk, 'quantity': 1}], 'done_choosing': False},
            change_on=is_reply, intents=['order'],
        )
        self.assertEqual(response.status_code, 200, response.json())
        self.assertEqual(response.json()['debug']['attempts'], 2)
        # Each attempt routed the message; the second one saw the owner's message.
        routes = [c.kwargs for c in self.ollama.chat.call_args_list if is_router(c.kwargs)]
        self.assertEqual(len(routes), 2)
        replies = [c.kwargs for c in self.ollama.chat.call_args_list if is_reply(c.kwargs)]
        self.assertNotIn(OWNER_MESSAGE, [m['content'] for m in replies[0]['messages']])
        self.assertIn(OWNER_MESSAGE, [m['content'] for m in replies[1]['messages']])
        # One reply, after the owner's message; the state is the second attempt's.
        self.assertEqual(self.senders(), [
            ('customer', 'I want a Kopi C'), ('business-manual', OWNER_MESSAGE), ('business-automated', 'OK!'),
        ])
        self.assertEqual(self.session.chat_state_id, 'product_selection')
        self.assertEqual(self.session.version, 3)  # message, owner, reply

    def test_nothing_of_the_first_attempt_is_saved(self):
        # The first attempt chose a product, but the chat changed: its state isn't saved, and the
        # second attempt (which finds nothing to order) decides.
        response = self.send_while_changing(
            'I want a Kopi C', {'items': [{'product_id': self.kopi.pk, 'quantity': 1}], 'done_choosing': False},
            change_on=is_reply, intents=['order'],
        )
        self.assertEqual(response.json()['debug']['attempts'], 2)
        self.assertNotIn('items', self.session.chat_state_data)
        self.assertEqual([sender for sender, _ in self.senders()], ['customer', 'business-manual', 'business-automated'])

    def test_a_chat_that_keeps_changing_gives_up_with_409(self):
        response = self.send_while_changing('Hello', change_on=is_router, changes=config.TURN_ATTEMPTS_MAX)
        self.assertEqual(response.status_code, 409, response.json())
        self.assertIn('kept changing', response.json()['detail'])
        self.assertEqual(len([c for c in self.ollama.chat.call_args_list if is_router(c.kwargs)]), config.TURN_ATTEMPTS_MAX)
        # The customer message is kept; nothing was replied.
        self.assertEqual(self.senders(), [('customer', 'Hello')] + [('business-manual', OWNER_MESSAGE)] * config.TURN_ATTEMPTS_MAX)

    def test_a_chat_that_settles_before_the_last_attempt_is_answered(self):
        response = self.send_while_changing('Hello', change_on=is_router, changes=config.TURN_ATTEMPTS_MAX - 1)
        self.assertEqual(response.status_code, 200, response.json())
        self.assertEqual(response.json()['debug']['attempts'], config.TURN_ATTEMPTS_MAX)
        self.assertEqual(self.senders()[-1], ('business-automated', 'OK!'))

    def test_save_turn_refuses_a_changed_chat(self):
        with self.assertRaises(order_flow.ChatChanged):
            flow.save_turn(self.sessions, self.session.id, None, ['Hi'], version=self.session.version + 1)
        self.assertEqual(self.get(ChatSession, self.session.id).chat_message_json, [])


class ChatVersionOrderTests(ChatVersionCase):
    """Placing an order: the version is checked when it's placed; after that the turn can't run again."""

    def setUp(self):
        super().setUp()
        with self.sessions.begin() as db:
            session = db.get(ChatSession, self.session.id)
            session.chat_state_id = 'confirmation'  # with the summary already shown
            session.chat_state_data = {
                'items': [{'product_id': self.kopi.pk, 'name': 'Kopi C', 'unit_price': '1.80', 'quantity': 3}],
                'details': {'name': 'Alice', 'email': 'alice@example.com'},
            }
        self.session = self.get(ChatSession, self.session.id)

    def test_a_change_before_the_order_is_placed_runs_the_turn_again(self):
        response = self.send_while_changing(
            'Yes', {'decision': 'confirm'}, {'decision': 'confirm'}, change_on=lambda kwargs: bool(kwargs.get('format')) and not is_router(kwargs),
        )
        self.assertEqual(response.status_code, 200, response.json())
        self.assertEqual(response.json()['debug']['attempts'], 2)
        order, = self.all(OrderItem)  # placed once
        self.assertEqual(self.session.chat_state_data, {'last_order_id': order.pk})
        self.assertEqual([sender for sender, _ in self.senders()], ['customer', 'business-manual', 'business-automated'])

    def test_placing_an_order_adds_1_and_the_reply_1_more(self):
        # commit_turn() returns the chat's new version, so the reply's save sees no change.
        with self.assertNoLogs('app.chat_flow.flow', level='WARNING'):
            response = self.send('Yes', {'decision': 'confirm'})
        self.assertEqual(response.json()['debug']['attempts'], 1)
        self.assertEqual(len(self.all(OrderItem)), 1)
        self.assertEqual(self.session.version, 4)  # the setUp's state, the message, the order + state, the reply

    def test_a_change_after_the_order_is_placed_still_saves_the_reply(self):
        # The question makes an LLM aside after the confirmation: the owner writes meanwhile.
        with self.assertLogs('app.chat_flow.flow', level='WARNING') as logs:
            response = self.send_while_changing(
                'Yes, and do you have oat milk?', {'decision': 'confirm'}, change_on=is_reply,
                intents=['question'], question_check={'kind': 'answered', 'question': 'Do you have oat milk?'},
            )
        self.assertEqual(response.status_code, 200, response.json())
        self.assertEqual(response.json()['debug']['attempts'], 1)
        order, = self.all(OrderItem)
        self.assertEqual(response.json()['debug']['order_id'], order.pk)
        self.assertIn('saving it anyway', logs.output[0])
        self.assertEqual([sender for sender, _ in self.senders()], ['customer', 'business-manual', 'business-automated'])
        self.assertIn(f'Your order #{order.pk}', self.senders()[-1][1])
