from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from auth_app.models import BusinessUser
from configuration_app.models import BusinessConfiguration
from product_app.models import FAQ, Product

from .flow import check_confirmation, check_details_collection, check_product_selection, check_start
from .models import ChatConfiguration, ChatSession
from .test_api import fake_chat_response, fake_ollama_chat
from .validators import validate_chat_messages, validate_chat_state_data

FULL_CONFIG = [
    {'id': 1, 'next_block_id': 2, 'block_type': 'START_BLOCK', 'position_x': 0, 'position_y': 0},
    {'id': 2, 'next_block_id': 'details', 'block_type': 'PRODUCT_SELECTION_BLOCK', 'position_x': 0, 'position_y': 0},
    {'id': 'details', 'next_block_id': 4, 'block_type': 'DETAILS_COLLECTION_BLOCK', 'position_x': 0, 'position_y': 0},
    {'id': 4, 'next_block_id': None, 'block_type': 'CONFIRMATION_BLOCK', 'position_x': 0, 'position_y': 0},
]

PRODUCTS = [
    {'id': 1, 'name': 'Kopi C', 'description': '', 'price': '1.80', 'quantity_available': 200},
    {'id': 2, 'name': 'Kaya Toast Set', 'description': '', 'price': '5.50', 'quantity_available': 3},
]


class ChatFlowAPITests(APITestCase):
    """The chat flow end to end, through the sandbox message API, with the LLM mocked."""

    @classmethod
    def setUpTestData(cls):
        cls.cafe = BusinessConfiguration.objects.create(business_name='Kopi Café', location='Tiong Bahru')
        cls.florist = BusinessConfiguration.objects.create(business_name='Florist', location='Singapore')
        cls.user = BusinessUser.objects.create_user(username='cafe', password='123', business=cls.cafe)
        cls.chat_config = ChatConfiguration.objects.create(business=cls.cafe, config_json=FULL_CONFIG)
        cls.kopi = Product.objects.create(business=cls.cafe, name='Kopi C', price='1.80', quantity_available=200)
        cls.toast = Product.objects.create(business=cls.cafe, name='Kaya Toast Set', price='5.50', quantity_available=3)
        Product.objects.create(business=cls.cafe, name='Old Special', price='9.00', is_active=False)
        Product.objects.create(business=cls.florist, name='Rose Bouquet', price='68.00', quantity_available=5)
        FAQ.objects.create(business=cls.cafe, question='Opening hours?', answer='8am to 7pm daily.')

    def setUp(self):
        self.session = ChatSession.objects.create(business=self.cafe, is_sandbox=True, chat_state_id=1)
        self.ollama = MagicMock()
        patcher = patch('chat_app.llm.get_client', return_value=self.ollama)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.client.force_authenticate(self.user)

    def send(self, message, *extractions, reply='OK!'):
        """Sends a customer message; the LLM's extraction calls return `extractions`, in order."""
        self.ollama.reset_mock()
        self.ollama.chat.side_effect = fake_ollama_chat(reply, extractions)
        response = self.client.post(
            reverse('chat_app:sandbox-session-messages', args=[self.session.pk]), {'message': message}, format='json'
        )
        self.session.refresh_from_db()
        return response

    def calls(self, structured: bool):
        return [c.kwargs for c in self.ollama.chat.call_args_list if bool(c.kwargs.get('format')) == structured]

    def reply_prompt(self) -> str:
        return self.calls(structured=False)[-1]['messages'][0]['content']

    def test_full_conversation_from_start_to_done(self):
        # 1. Only a question: stays at the start.
        self.assertEqual(self.send('Hi, what do you sell?', {'wants_to_order': False}).status_code, 200)
        self.assertEqual(self.session.chat_state_id, 1)
        self.assertEqual(self.session.chat_state_data, {})
        self.assertIn('Kopi C, $1.80', self.reply_prompt())  # catalog in the start prompt
        self.assertNotIn('Old Special', self.reply_prompt())  # inactive products aren't offered
        self.assertNotIn('Rose Bouquet', self.reply_prompt())  # nor another business's

        # 2. Wants to order and picks a product in one message: start → product selection → details.
        response = self.send(
            "I'd like 2 Kopi C",
            {'wants_to_order': True},
            {'items': [{'product_id': self.kopi.pk, 'quantity': 2}]},
            {'name': None, 'email': None},
        )
        self.assertEqual(self.session.chat_state_id, 'details')
        self.assertEqual(
            self.session.chat_state_data,
            {'items': [{'product_id': self.kopi.pk, 'name': 'Kopi C', 'unit_price': '1.80', 'quantity': 2}]},
        )
        self.assertEqual(len(self.calls(structured=True)), 3)
        prompt = self.reply_prompt()
        self.assertIn('Current step: Details collection', prompt)
        self.assertIn('just completed: Start, Product selection', prompt)
        self.assertIn('2 × Kopi C ($1.80 each). Total: $3.60', prompt)
        self.assertIn('- name\n- email address', prompt)
        # The sandbox reply also says what happened inside the turn, for the debug panel.
        debug = response.json()['debug']
        self.assertEqual(debug['before'], {'chat_state_id': 1, 'chat_state_data': {}})
        self.assertEqual(debug['after']['chat_state_id'], 'details')
        self.assertEqual(debug['after']['block_type'], 'DETAILS_COLLECTION_BLOCK')
        self.assertEqual(
            [(step['block_id'], step['complete']) for step in debug['steps']], [(1, True), (2, True), ('details', False)]
        )
        self.assertEqual(debug['steps'][1]['extracted'], {'items': [{'product_id': self.kopi.pk, 'quantity': 2}]})
        self.assertIn('Products on sale', debug['steps'][1]['system_prompt'])
        self.assertEqual(debug['steps'][2]['missing'], ['name', 'email address'])
        self.assertEqual(debug['stop_reason'], 'This block is not complete yet: waiting for the customer.')
        self.assertEqual(debug['reply_system_prompt'], prompt)
        self.assertEqual(debug['tool_calls'], [])

        # 3. Only the name: still at details, asks for the email. The name fills in display_name.
        self.send("I'm Alice", {'name': 'Alice', 'email': None})
        self.assertEqual(self.session.chat_state_id, 'details')
        self.assertEqual(self.session.chat_state_data['details'], {'name': 'Alice'})
        self.assertEqual(self.session.display_name, 'Alice')
        self.assertIn('## Still needed\n- email address', self.reply_prompt())

        # 4. The email: moves to confirmation, without asking the LLM about confirmation yet.
        response = self.send('alice@example.com', {'name': None, 'email': 'alice@example.com'})
        self.assertIn('not checked until the customer has seen the summary', response.json()['debug']['stop_reason'])
        self.assertEqual(self.session.chat_state_id, 4)
        self.assertEqual(self.session.chat_state_data['details'], {'name': 'Alice', 'email': 'alice@example.com'})
        self.assertEqual(len(self.calls(structured=True)), 1)
        self.assertIn('Current step: Confirmation', self.reply_prompt())
        self.assertIn('name: Alice, email address: alice@example.com', self.reply_prompt())

        # 5. Confirms: the flow is completed, at the last block.
        self.send('Yes', {'decision': 'confirm'}, reply='Thanks Alice, your order is confirmed!')
        self.assertEqual(self.session.chat_state_id, 4)
        self.assertIs(self.session.chat_state_data['completed'], True)
        self.assertIn('Done (order confirmed)', self.reply_prompt())

        # 6. After that: no more extraction, just replies.
        response = self.send('Thank you!')
        self.assertEqual(self.calls(structured=True), [])
        self.assertEqual(response.json()['debug']['steps'], [])
        self.assertIn('The order is confirmed and complete', self.reply_prompt())

        messages = self.session.chat_message_json
        self.assertEqual(len(messages), 12)
        self.assertEqual(messages[9]['message'], 'Thanks Alice, your order is confirmed!')
        validate_chat_messages(messages)
        validate_chat_state_data(self.session.chat_state_data)
        self.session.full_clean()

    def test_change_at_confirmation_goes_back_through_the_flow(self):
        self.session.chat_state_id = 4
        self.session.chat_state_data = {
            'items': [{'product_id': self.kopi.pk, 'name': 'Kopi C', 'unit_price': '1.80', 'quantity': 2}],
            'details': {'name': 'Alice', 'email': 'alice@example.com'},
        }
        self.session.save()
        self.send(
            'Actually make it 3 Kaya Toast Sets',
            {'decision': 'change'},
            {'items': [{'product_id': self.toast.pk, 'quantity': 3}]},
            {'name': None, 'email': None},  # details already known: passes straight through
        )
        # Back at confirmation, with the new order, to show the updated summary.
        self.assertEqual(self.session.chat_state_id, 4)
        self.assertEqual(self.session.chat_state_data['items'][0]['name'], 'Kaya Toast Set')
        self.assertNotIn('completed', self.session.chat_state_data)
        self.assertIn('3 × Kaya Toast Set ($5.50 each). Total: $16.50', self.reply_prompt())

    def test_invalid_choice_stays_and_explains(self):
        self.session.chat_state_id = 2
        self.session.save()
        self.send('10 Kaya Toast Sets please', {'items': [{'product_id': self.toast.pk, 'quantity': 10}]})
        self.assertEqual(self.session.chat_state_id, 2)
        self.assertEqual(self.session.chat_state_data, {})
        self.assertIn('Only 3 Kaya Toast Set are available.', self.reply_prompt())

    def test_unknown_state_falls_back_to_start_block(self):
        self.session.chat_state_id = 'deleted-block'  # e.g. removed from the workflow since
        self.session.save()
        self.send('Hello', {'wants_to_order': False})
        self.assertEqual(self.session.chat_state_id, 1)

    def test_lone_start_block_never_completes(self):
        lone = BusinessConfiguration.objects.create(business_name='New Shop', location='SG')
        ChatConfiguration.objects.create(business=lone, config_json=[FULL_CONFIG[0] | {'next_block_id': None}])
        user = BusinessUser.objects.create_user(username='new', password='123', business=lone)
        self.session = ChatSession.objects.create(business=lone, is_sandbox=True, chat_state_id=1)
        self.client.force_authenticate(user)
        self.send('I want to order', {'wants_to_order': True})
        self.assertEqual(self.session.chat_state_id, 1)
        self.assertEqual(self.session.chat_state_data, {})

    def test_invalid_json_from_llm_returns_502_and_keeps_state(self):
        self.ollama.reset_mock()
        self.ollama.chat.side_effect = None
        self.ollama.chat.return_value = fake_chat_response('not json')
        response = self.client.post(
            reverse('chat_app:sandbox-session-messages', args=[self.session.pk]), {'message': 'Hi'}, format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_502_BAD_GATEWAY)
        self.session.refresh_from_db()
        self.assertEqual([m['sent_by'] for m in self.session.chat_message_json], ['customer'])
        self.assertEqual((self.session.chat_state_id, self.session.chat_state_data), (1, {}))

    def test_reply_can_call_read_only_tools(self):
        tool_call = SimpleNamespace(function=SimpleNamespace(name='list_faqs', arguments={}))
        responses = iter([
            fake_chat_response('{"wants_to_order": false}'),
            SimpleNamespace(message=SimpleNamespace(content='', tool_calls=[tool_call])),
            fake_chat_response('We are open 8am to 7pm daily.'),
        ])
        self.ollama.chat.side_effect = lambda **kwargs: next(responses)
        response = self.client.post(
            reverse('chat_app:sandbox-session-messages', args=[self.session.pk]),
            {'message': 'When are you open?'},
            format='json',
        )
        self.assertEqual(response.json()['message'], 'We are open 8am to 7pm daily.')
        reply_calls = self.ollama.chat.call_args_list[1:]
        self.assertEqual(
            {spec['function']['name'] for spec in reply_calls[0].kwargs['tools']}, {'list_products', 'list_faqs'}
        )
        tool_message = reply_calls[1].kwargs['messages'][-1]
        self.assertEqual((tool_message['role'], tool_message['tool_name']), ('tool', 'list_faqs'))
        self.assertIn('8am to 7pm daily.', tool_message['content'])
        self.assertEqual(response.json()['debug']['tool_calls'], [{'name': 'list_faqs', 'arguments': {}}])
        self.session.refresh_from_db()
        self.assertNotIn('debug', self.session.chat_message_json[-1])  # debug info isn't stored


class FlowCheckTests(SimpleTestCase):
    """The deterministic checks of the LLM's extraction, one per block type."""

    def test_start(self):
        self.assertTrue(check_start({'wants_to_order': True}, {}, PRODUCTS).complete)
        for extracted in ({'wants_to_order': False}, {}, {'wants_to_order': 'yes'}):
            self.assertFalse(check_start(extracted, {}, PRODUCTS).complete)

    def test_product_selection_valid_choice(self):
        data = {}
        result = check_product_selection(
            {'items': [{'product_id': 1, 'quantity': 2}, {'product_id': 2, 'quantity': 3}]}, data, PRODUCTS
        )
        self.assertTrue(result.complete)
        self.assertEqual([(i['name'], i['quantity'], i['unit_price']) for i in data['items']],
                         [('Kopi C', 2, '1.80'), ('Kaya Toast Set', 3, '5.50')])

    def test_product_selection_problems(self):
        cases = {
            'unknown product': ({'product_id': 99, 'quantity': 1}, 'not on sale'),
            'no quantity': ({'product_id': 1, 'quantity': None}, 'how many Kopi C'),
            'zero quantity': ({'product_id': 1, 'quantity': 0}, 'how many Kopi C'),
            'bool quantity': ({'product_id': 1, 'quantity': True}, 'how many Kopi C'),
            'not enough stock': ({'product_id': 2, 'quantity': 4}, 'Only 3 Kaya Toast Set'),
        }
        for label, (item, issue) in cases.items():
            with self.subTest(label):
                result = check_product_selection({'items': [item]}, {}, PRODUCTS)
                self.assertFalse(result.complete)
                self.assertIn(issue, result.issues[0])

    def test_product_selection_keeps_earlier_choice_when_nothing_new(self):
        earlier = {'items': [{'product_id': 1, 'name': 'Kopi C', 'unit_price': '1.80', 'quantity': 1}]}
        self.assertTrue(check_product_selection({'items': []}, earlier, PRODUCTS).complete)
        result = check_product_selection({'items': []}, {}, PRODUCTS)
        self.assertFalse(result.complete)
        self.assertEqual(result.missing, ['which products, and how many of each'])

    def test_details_collection(self):
        data = {}
        result = check_details_collection({'name': ' Alice ', 'email': None}, data, PRODUCTS)
        self.assertEqual((result.complete, result.missing), (False, ['email address']))
        self.assertEqual(data, {'details': {'name': 'Alice'}})

        result = check_details_collection({'name': None, 'email': 'not-an-email'}, data, PRODUCTS)
        self.assertFalse(result.complete)
        self.assertIn('not a valid email address', result.issues[0])

        result = check_details_collection({'name': None, 'email': 'alice@example.com'}, data, PRODUCTS)
        self.assertTrue(result.complete)
        self.assertEqual(data['details'], {'name': 'Alice', 'email': 'alice@example.com'})

    def test_details_collection_nothing_given_adds_no_key(self):
        data = {}
        check_details_collection({'name': '', 'email': None}, data, PRODUCTS)
        self.assertEqual(data, {})

    def test_confirmation(self):
        self.assertTrue(check_confirmation({'decision': 'confirm'}, {}, PRODUCTS).complete)
        self.assertTrue(check_confirmation({'decision': 'change'}, {}, PRODUCTS).go_back)
        result = check_confirmation({'decision': 'none'}, {}, PRODUCTS)
        self.assertFalse(result.complete or result.go_back)
