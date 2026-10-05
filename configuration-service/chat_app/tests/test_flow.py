import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from auth_app.models import BusinessUser
from configuration_app.models import BusinessConfiguration
from checkout_app.models import OrderItem, OrderStatus
from product_app.models import FAQ, Product

from ..flow import (
    check_confirmation,
    check_details_collection,
    check_product_selection,
    check_start,
    clean_detail_value,
)
from ..models import ChatConfiguration, ChatSession
from ..validators import validate_chat_messages, validate_chat_state_data
from .test_api import fake_chat_response, fake_ollama_chat

FULL_CONFIG = [
    {'id': 1, 'next_block_id': 2, 'block_type': 'START_BLOCK', 'position_x': 0, 'position_y': 0},
    {'id': 2, 'next_block_id': 'details', 'block_type': 'PRODUCT_SELECTION_BLOCK', 'position_x': 0, 'position_y': 0},
    {'id': 'details', 'next_block_id': 4, 'block_type': 'DETAILS_COLLECTION_BLOCK', 'position_x': 0, 'position_y': 0},
    {'id': 4, 'next_block_id': None, 'block_type': 'CONFIRMATION_BLOCK', 'position_x': 0, 'position_y': 0},
]

# A DETAILS_COLLECTION_BLOCK without `fields`: it asks for the default name and email.
DEFAULT_DETAILS_BLOCK = FULL_CONFIG[2]

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

        # 2. Wants to order and picks a product in one message: start → product selection, which
        #    pauses to recap the order and ask if they want anything else (no details yet).
        response = self.send(
            "I'd like 2 Kopi C",
            {'wants_to_order': True},
            {'items': [{'product_id': self.kopi.pk, 'quantity': 2}], 'done_choosing': False},
        )
        self.assertEqual(self.session.chat_state_id, 2)
        self.assertEqual(self.session.chat_state_data, {'items': [{'product_id': self.kopi.pk, 'name': 'Kopi C', 'unit_price': '1.80', 'quantity': 2}]})
        self.assertEqual(len(self.calls(structured=True)), 2)
        prompt = self.reply_prompt()
        self.assertIn('Current step: Product selection', prompt)
        self.assertIn('just completed: Start', prompt)
        self.assertIn('2 × Kopi C ($1.80 each). Total: $3.60', prompt)
        self.assertIn('## Still needed\n- the customer to confirm that this is everything they want', prompt)
        self.assertIn('ask whether they would like anything else', prompt)
        self.assertNotIn('## Details to collect', prompt)
        # The sandbox reply also says what happened inside the turn, for the debug panel.
        debug = response.json()['debug']
        self.assertEqual(debug['before'], {'chat_state_id': 1, 'chat_state_data': {}})
        self.assertEqual(debug['after']['chat_state_id'], 2)
        self.assertEqual(debug['after']['block_type'], 'PRODUCT_SELECTION_BLOCK')
        self.assertEqual([(step['block_id'], step['complete']) for step in debug['steps']], [(1, True), (2, False)])
        self.assertEqual(
            debug['steps'][1]['extracted'], {'items': [{'product_id': self.kopi.pk, 'quantity': 2}], 'done_choosing': False}
        )
        self.assertIn('Products on sale', debug['steps'][1]['system_prompt'])
        self.assertIn('"done_choosing"', debug['steps'][1]['system_prompt'])
        self.assertEqual(debug['stop_reason'], 'This block is not complete yet: waiting for the customer.')
        self.assertEqual(debug['reply_system_prompt'], prompt)
        self.assertEqual(debug['tool_calls'], [])

        # 2b. That's everything: product selection completes, on to details.
        response = self.send(
            "No, that's all",
            {'items': [{'product_id': self.kopi.pk, 'quantity': 2}], 'done_choosing': True},
            {'name': None, 'email': None},
        )
        self.assertEqual(self.session.chat_state_id, 'details')
        self.assertEqual(self.session.chat_state_data, {'items': [{'product_id': self.kopi.pk, 'name': 'Kopi C', 'unit_price': '1.80', 'quantity': 2}], 'items_confirmed': True})
        prompt = self.reply_prompt()
        self.assertIn('Current step: Details collection', prompt)
        self.assertIn('just completed: Product selection', prompt)
        self.assertIn('## Still needed\n- Name\n- Email', prompt)
        self.assertIn(
            '## Details to collect\n- "Name" (required; text, at most 150 characters)\n- "Email" (required; an email address)',
            prompt,
        )
        self.assertEqual(response.json()['debug']['steps'][1]['missing'], ['Name', 'Email'])

        # 3. Only the name: still at details, asks for the email. The name fills in display_name.
        self.send("I'm Alice", {'name': 'Alice', 'email': None})
        self.assertEqual(self.session.chat_state_id, 'details')
        self.assertEqual(self.session.chat_state_data['details'], {'name': 'Alice'})
        self.assertEqual(self.session.display_name, 'Alice')
        self.assertIn('## Still needed\n- Email', self.reply_prompt())

        # 4. The email: moves to confirmation, without asking the LLM about confirmation yet.
        response = self.send('alice@example.com', {'name': None, 'email': 'alice@example.com'})
        self.assertIn('not checked until the customer has seen the summary', response.json()['debug']['stop_reason'])
        self.assertEqual(self.session.chat_state_id, 4)
        self.assertEqual(self.session.chat_state_data['details'], {'name': 'Alice', 'email': 'alice@example.com'})
        self.assertEqual(len(self.calls(structured=True)), 1)
        self.assertIn('Current step: Confirmation', self.reply_prompt())
        self.assertIn('Name: Alice, Email: alice@example.com', self.reply_prompt())

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
        self.assertEqual(len(messages), 14)
        self.assertEqual(messages[11]['message'], 'Thanks Alice, your order is confirmed!')
        validate_chat_messages(messages)
        validate_chat_state_data(self.session.chat_state_data)
        self.session.full_clean()

    def test_change_at_confirmation_goes_back_through_the_flow(self):
        self.session.chat_state_id = 4
        self.session.chat_state_data = {
            'items': [{'product_id': self.kopi.pk, 'name': 'Kopi C', 'unit_price': '1.80', 'quantity': 2}],
            'items_confirmed': True,
            'details': {'name': 'Alice', 'email': 'alice@example.com'},
        }
        self.session.save()
        self.send(
            'Actually make it 3 Kaya Toast Sets',
            {'decision': 'change'},
            {'items': [{'product_id': self.toast.pk, 'quantity': 3}], 'done_choosing': False},
        )
        # A changed order: back at product selection, to recap it and ask if that's everything.
        self.assertEqual(self.session.chat_state_id, 2)
        self.assertEqual(self.session.chat_state_data['items'][0]['name'], 'Kaya Toast Set')
        self.assertNotIn('items_confirmed', self.session.chat_state_data)
        self.assertIn('3 × Kaya Toast Set ($5.50 each). Total: $16.50', self.reply_prompt())
        self.assertIn('Current step: Product selection', self.reply_prompt())

        self.send(
            "That's it",
            {'items': [{'product_id': self.toast.pk, 'quantity': 3}], 'done_choosing': True},
            {'name': None, 'email': None},  # details already known: passes straight through
        )
        # Back at confirmation, with the new order, to show the updated summary.
        self.assertEqual(self.session.chat_state_id, 4)
        self.assertNotIn('completed', self.session.chat_state_data)
        self.assertIn('Current step: Confirmation', self.reply_prompt())

    def test_change_of_details_at_confirmation_keeps_the_confirmed_order(self):
        self.session.chat_state_id = 4
        self.session.chat_state_data = {
            'items': [{'product_id': self.kopi.pk, 'name': 'Kopi C', 'unit_price': '1.80', 'quantity': 2}],
            'items_confirmed': True,
            'details': {'name': 'Alice', 'email': 'alice@example.com'},
        }
        self.session.save()
        self.send(
            'Please change my email to alice@work.com',
            {'decision': 'change'},
            {'items': [{'product_id': self.kopi.pk, 'quantity': 2}], 'done_choosing': False},  # same order
            {'name': None, 'email': 'alice@work.com'},
        )
        # The order was already confirmed and didn't change: no "anything else?" again.
        self.assertEqual(self.session.chat_state_id, 4)
        self.assertEqual(self.session.chat_state_data['details']['email'], 'alice@work.com')
        self.assertTrue(self.session.chat_state_data['items_confirmed'])

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
            {spec['function']['name'] for spec in reply_calls[0].kwargs['tools']},
            {'list_products', 'get_product_description', 'list_faqs'},
        )
        tool_message = reply_calls[1].kwargs['messages'][-1]
        self.assertEqual((tool_message['role'], tool_message['tool_name']), ('tool', 'list_faqs'))
        self.assertIn('8am to 7pm daily.', tool_message['content'])
        self.assertEqual(response.json()['debug']['tool_calls'], [{'name': 'list_faqs', 'arguments': {}}])
        self.session.refresh_from_db()
        self.assertNotIn('debug', self.session.chat_message_json[-1])  # debug info isn't stored


class CustomDetailFieldsFlowTests(APITestCase):
    """A Details collection block with business-chosen fields: the flow asks for exactly those."""

    FIELDS = [
        {'key': 'name', 'label': 'Receiver name', 'type': 'text', 'max_length': 150},
        {'key': 'postal_code', 'label': 'Postal code', 'type': 'number', 'min_value': 100000, 'max_value': 999999},
        {'key': 'notes', 'label': 'Customisation notes', 'type': 'text', 'max_length': 20, 'description': 'e.g. less sugar'},
    ]  # no email: the business deselected it

    @classmethod
    def setUpTestData(cls):
        cls.cafe = BusinessConfiguration.objects.create(business_name='Kopi Café', location='Tiong Bahru')
        cls.user = BusinessUser.objects.create_user(username='cafe', password='123', business=cls.cafe)
        blocks = [dict(block) for block in FULL_CONFIG]
        blocks[2]['fields'] = cls.FIELDS
        cls.chat_config = ChatConfiguration.objects.create(business=cls.cafe, config_json=blocks)
        cls.chat_config.full_clean()
        cls.kopi = Product.objects.create(business=cls.cafe, name='Kopi C', price='1.80', quantity_available=200)

    def setUp(self):
        self.session = ChatSession.objects.create(
            business=self.cafe,
            is_sandbox=True,
            chat_state_id='details',
            chat_state_data={'items': [{'product_id': self.kopi.pk, 'name': 'Kopi C', 'unit_price': '1.80', 'quantity': 1}]},
        )
        self.ollama = MagicMock()
        patcher = patch('chat_app.llm.get_client', return_value=self.ollama)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.client.force_authenticate(self.user)

    send = ChatFlowAPITests.send
    calls = ChatFlowAPITests.calls
    reply_prompt = ChatFlowAPITests.reply_prompt

    def test_asks_for_every_field_and_only_proceeds_when_all_are_valid(self):
        # Nothing given yet: asks for all three, with their formats.
        self.send('Hi', {'name': None, 'postal_code': None, 'notes': None})
        self.assertEqual(self.session.chat_state_id, 'details')
        prompt = self.reply_prompt()
        self.assertIn('## Still needed\n- Receiver name\n- Postal code\n- Customisation notes', prompt)
        self.assertIn(
            '## Details to collect\n'
            '- "Receiver name" (required; text, at most 150 characters)\n'
            '- "Postal code" (required; a number from 100000 to 999999)\n'
            '- "Customisation notes" (required; text, at most 20 characters). e.g. less sugar',
            prompt,
        )
        self.assertNotIn('Email', prompt)

        # The extraction asks for exactly these keys, with the number field typed as a number.
        extraction = self.calls(structured=True)[0]
        self.assertEqual(
            extraction['format']['properties'],
            {
                'name': {'anyOf': [{'type': 'string'}, {'type': 'null'}]},
                'postal_code': {'anyOf': [{'type': 'number'}, {'type': 'null'}]},
                'notes': {'anyOf': [{'type': 'string'}, {'type': 'null'}]},
            },
        )
        self.assertEqual(extraction['format']['required'], ['name', 'postal_code', 'notes'])
        self.assertIn('"postal_code": "Postal code" (required; a number from 100000 to 999999)', extraction['messages'][0]['content'])

        # Some given, some invalid: keeps the valid ones, explains the problems, stays.
        self.send('Alice, 12, extra extra extra sweet please', {'name': 'Alice', 'postal_code': 12, 'notes': 'extra extra extra sweet please'})
        self.assertEqual(self.session.chat_state_id, 'details')
        self.assertEqual(self.session.chat_state_data['details'], {'name': 'Alice'})
        prompt = self.reply_prompt()
        self.assertIn('## Still needed\n- Postal code\n- Customisation notes', prompt)
        self.assertIn('- Postal code must be at least 100000.', prompt)
        self.assertIn('- Customisation notes is too long (max 20 characters).', prompt)
        self.assertIn('Customer details: Receiver name: Alice.', prompt)

        # One still missing: stays.
        self.send('Postal code 238801', {'name': None, 'postal_code': 238801, 'notes': None})
        self.assertEqual(self.session.chat_state_id, 'details')
        self.assertIn('## Still needed\n- Customisation notes', self.reply_prompt())

        # All valid (the number even as text): moves on to confirmation.
        self.send('Less sugar', {'name': None, 'postal_code': None, 'notes': 'Less sugar'})
        self.assertEqual(self.session.chat_state_id, 4)
        self.assertEqual(
            self.session.chat_state_data['details'], {'name': 'Alice', 'postal_code': 238801, 'notes': 'Less sugar'}
        )
        self.assertIn(
            'Customer details: Receiver name: Alice, Postal code: 238801, Customisation notes: Less sugar.',
            self.reply_prompt(),
        )
        self.session.full_clean()

    def test_number_given_as_text_is_accepted(self):
        self.send('x', {'name': 'Bob', 'postal_code': '238,801', 'notes': 'none'})
        self.assertEqual(self.session.chat_state_id, 4)
        self.assertEqual(self.session.chat_state_data['details']['postal_code'], 238801)

    def test_new_session_from_updated_configuration_asks_for_new_fields(self):
        # A session created through the API after the configuration changed starts at Start and,
        # once there, asks for the business's fields.
        response = self.client.post(reverse('chat_app:sandbox-session-list'), {}, format='json')
        self.session = ChatSession.objects.get(pk=response.json()['id'])
        self.send(
            'I want 1 Kopi C',
            {'wants_to_order': True},
            {'items': [{'product_id': self.kopi.pk, 'quantity': 1}], 'done_choosing': False},
        )
        self.assertEqual(self.session.chat_state_id, 2)  # recaps the order first
        self.send(
            "That's all",
            {'items': [{'product_id': self.kopi.pk, 'quantity': 1}], 'done_choosing': True},
            {'name': None, 'postal_code': None, 'notes': None},
        )
        self.assertEqual(self.session.chat_state_id, 'details')
        self.assertIn('## Still needed\n- Receiver name\n- Postal code\n- Customisation notes', self.reply_prompt())


class OrderPlacementFlowTests(APITestCase):
    """Confirming at the Confirmation block places an order (checkout_app) and reserves its stock."""

    @classmethod
    def setUpTestData(cls):
        cls.cafe = BusinessConfiguration.objects.create(business_name='Kopi Café', location='Tiong Bahru')
        cls.user = BusinessUser.objects.create_user(username='cafe', password='123', business=cls.cafe)
        ChatConfiguration.objects.create(business=cls.cafe, config_json=FULL_CONFIG)

    def setUp(self):
        self.kopi = Product.objects.create(business=self.cafe, name='Kopi C', price='1.80', quantity_available=10)
        self.session = ChatSession.objects.create(
            business=self.cafe,
            is_sandbox=True,
            chat_state_id=4,  # at confirmation, with the summary already shown
            chat_state_data={
                'items': [{'product_id': self.kopi.pk, 'name': 'Kopi C', 'unit_price': '1.80', 'quantity': 3}],
                'details': {'name': 'Alice', 'email': 'alice@example.com'},
            },
        )
        self.ollama = MagicMock()
        patcher = patch('chat_app.llm.get_client', return_value=self.ollama)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.client.force_authenticate(self.user)

    send = ChatFlowAPITests.send
    reply_prompt = ChatFlowAPITests.reply_prompt
    calls = ChatFlowAPITests.calls

    def test_confirming_places_the_order_and_reserves_stock(self):
        response = self.send('Yes', {'decision': 'confirm'})
        order = OrderItem.objects.get()
        self.assertEqual(order.business, self.cafe)
        self.assertEqual(order.chat_session, self.session)
        self.assertTrue(order.is_sandbox)
        self.assertEqual(order.order_status, OrderStatus.PENDING_PAYMENT)
        self.assertEqual(
            order.order_data,
            {
                'items': [{'product_id': self.kopi.pk, 'name': 'Kopi C', 'unit_price': '1.80', 'quantity': 3}],
                'details': {'name': 'Alice', 'email': 'alice@example.com'},
            },
        )
        self.kopi.refresh_from_db()
        self.assertEqual((self.kopi.quantity_available, self.kopi.quantity_on_hold), (7, 3))

        self.assertIs(self.session.chat_state_data['completed'], True)
        self.assertEqual(self.session.chat_state_data['order_id'], order.pk)
        self.assertIn(f'Order number: #{order.pk} (placed; payment pending).', self.reply_prompt())
        self.assertEqual(response.json()['debug']['order_id'], order.pk)

        # Later messages don't order again.
        self.send('Thanks!')
        self.send('When is it ready?')
        self.assertEqual(OrderItem.objects.count(), 1)
        self.kopi.refresh_from_db()
        self.assertEqual(self.kopi.quantity_available, 7)

    def test_not_confirming_places_nothing(self):
        for decision in ('none', 'change'):
            with self.subTest(decision):
                self.send('Hmm', {'decision': decision}, {'items': []}, {'name': None, 'email': None})
        self.assertFalse(OrderItem.objects.exists())

    def test_sold_out_since_chosen_undoes_the_confirmation(self):
        Product.objects.filter(pk=self.kopi.pk).update(quantity_available=2)  # someone else bought some
        response = self.send('Yes', {'decision': 'confirm'})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(OrderItem.objects.exists())
        self.kopi.refresh_from_db()
        self.assertEqual((self.kopi.quantity_available, self.kopi.quantity_on_hold), (2, 0))
        # Still at confirmation, not completed, and the reply explains why.
        self.assertEqual(self.session.chat_state_id, 4)
        self.assertNotIn('completed', self.session.chat_state_data)
        self.assertNotIn('order_id', self.session.chat_state_data)
        prompt = self.reply_prompt()
        self.assertIn('Current step: Confirmation', prompt)
        self.assertIn('- Only 2 Kopi C are left.', prompt)
        self.assertIn('the order was NOT placed', prompt)
        self.assertNotIn('just completed: Confirmation', prompt)
        self.assertIn('The order could not be placed', response.json()['debug']['stop_reason'])

    def test_product_deactivated_since_chosen(self):
        Product.objects.filter(pk=self.kopi.pk).update(is_active=False)
        self.send('Yes', {'decision': 'confirm'})
        self.assertFalse(OrderItem.objects.exists())
        self.assertIn('- Kopi C is no longer available.', self.reply_prompt())

    def test_real_customer_chat_places_a_real_order(self):
        real = ChatSession.objects.create(
            business=self.cafe, phone_number='+6591234567', chat_state_id=4, chat_state_data=self.session.chat_state_data
        )
        self.ollama.chat.side_effect = fake_ollama_chat('Confirmed!', [{'decision': 'confirm'}])
        response = self.client.post(
            reverse('chat_app:customer-message'),
            {'business_id': self.cafe.pk, 'phone_number': '+6591234567', 'message': 'YES'},
            format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('debug', response.json())
        order = OrderItem.objects.get()
        self.assertFalse(order.is_sandbox)
        self.assertEqual(order.chat_session, real)


SEND_MESSAGE_CONFIG = [
    {'id': 1, 'next_block_id': 2, 'block_type': 'START_BLOCK', 'position_x': 0, 'position_y': 0},
    {'id': 2, 'next_block_id': 5, 'block_type': 'PRODUCT_SELECTION_BLOCK', 'position_x': 0, 'position_y': 0},
    {'id': 5, 'next_block_id': 'details', 'block_type': 'SEND_MESSAGE_BLOCK', 'position_x': 0, 'position_y': 0,
     'message': 'Great choice! Now a couple of quick questions.'},
    {'id': 'details', 'next_block_id': 4, 'block_type': 'DETAILS_COLLECTION_BLOCK', 'position_x': 0, 'position_y': 0},
    {'id': 4, 'next_block_id': 6, 'block_type': 'CONFIRMATION_BLOCK', 'position_x': 0, 'position_y': 0},
    {'id': 6, 'next_block_id': None, 'block_type': 'SEND_MESSAGE_BLOCK', 'position_x': 0, 'position_y': 0,
     'message': 'Thank you! We have received your order.'},
]


class SendMessageFlowTests(APITestCase):
    """A Send message block sends its fixed message (no LLM), then the chat moves straight on."""

    @classmethod
    def setUpTestData(cls):
        cls.cafe = BusinessConfiguration.objects.create(business_name='Kopi Café', location='Tiong Bahru')
        cls.user = BusinessUser.objects.create_user(username='cafe', password='123', business=cls.cafe)
        cls.chat_config = ChatConfiguration.objects.create(business=cls.cafe, config_json=SEND_MESSAGE_CONFIG)
        cls.chat_config.full_clean()

    def setUp(self):
        self.kopi = Product.objects.create(business=self.cafe, name='Kopi C', price='1.80', quantity_available=10)
        self.kopi_line = {'product_id': self.kopi.pk, 'name': 'Kopi C', 'unit_price': '1.80', 'quantity': 2}
        self.session = ChatSession.objects.create(
            business=self.cafe, is_sandbox=True, chat_state_id=2, chat_state_data={'items': [self.kopi_line]}
        )
        self.ollama = MagicMock()
        patcher = patch('chat_app.llm.get_client', return_value=self.ollama)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.client.force_authenticate(self.user)

    send = ChatFlowAPITests.send
    calls = ChatFlowAPITests.calls
    reply_prompt = ChatFlowAPITests.reply_prompt

    def new_messages(self, count):
        return [(m['sent_by'], m['message']) for m in self.session.chat_message_json[-count:]]

    def test_sends_its_message_then_moves_on_in_the_same_turn(self):
        response = self.send(
            "That's all",
            {'items': [{'product_id': self.kopi.pk, 'quantity': 2}], 'done_choosing': True},
            {'name': None, 'email': None},
            reply='May I have your name and email?',
        )
        # Product selection → Send message (sent) → Details collection, all with one customer message.
        self.assertEqual(self.session.chat_state_id, 'details')
        self.assertEqual(
            self.new_messages(3),
            [
                ('customer', "That's all"),
                ('business-automated', 'Great choice! Now a couple of quick questions.'),
                ('business-automated', 'May I have your name and email?'),
            ],
        )
        validate_chat_messages(self.session.chat_message_json)
        self.assertEqual(response.json()['message'], 'May I have your name and email?')
        # No LLM call for the block itself: one extraction each for product selection and details.
        self.assertEqual([c['format']['required'] for c in self.calls(structured=True)], [['items', 'done_choosing'], ['name', 'email']])
        # The reply knows what was just sent, and sees it as the last assistant message.
        prompt = self.reply_prompt()
        self.assertIn('## Just sent', prompt)
        self.assertIn('- "Great choice! Now a couple of quick questions."', prompt)
        self.assertIn('just completed: Product selection, Send message', prompt)
        reply_history = self.calls(structured=False)[-1]['messages']
        self.assertEqual(reply_history[-1], {'role': 'assistant', 'content': 'Great choice! Now a couple of quick questions.'})
        debug = response.json()['debug']
        self.assertEqual(debug['sent_messages'], [{'block_id': 5, 'message': 'Great choice! Now a couple of quick questions.'}])

    def test_last_block_message_is_the_last_word(self):
        self.session.chat_state_id = 4
        self.session.chat_state_data = {
            'items': [self.kopi_line], 'items_confirmed': True, 'details': {'name': 'Alice', 'email': 'a@b.co'},
        }
        self.session.save()
        response = self.send('Yes', {'decision': 'confirm'})
        # Confirmation → the last block (Send message): order placed, flow completed, no LLM reply.
        self.assertEqual(self.session.chat_state_id, 6)
        self.assertIs(self.session.chat_state_data['completed'], True)
        self.assertEqual(OrderItem.objects.count(), 1)
        self.assertEqual(self.calls(structured=False), [])
        self.assertEqual(response.json()['message'], 'Thank you! We have received your order.')
        self.assertEqual(self.new_messages(2), [('customer', 'Yes'), ('business-automated', 'Thank you! We have received your order.')])
        self.assertEqual(response.json()['debug']['reply_system_prompt'], '')

        # Later messages: a normal reply, and the message isn't sent again.
        self.send('When will it be ready?', reply='In about 10 minutes!')
        self.assertEqual(self.new_messages(2), [('customer', 'When will it be ready?'), ('business-automated', 'In about 10 minutes!')])
        texts = [m['message'] for m in self.session.chat_message_json]
        self.assertEqual(texts.count('Thank you! We have received your order.'), 1)

    def test_failed_order_does_not_send_the_message_after_confirmation(self):
        self.session.chat_state_id = 4
        self.session.chat_state_data = {
            'items': [self.kopi_line], 'items_confirmed': True, 'details': {'name': 'Alice', 'email': 'a@b.co'},
        }
        self.session.save()
        Product.objects.filter(pk=self.kopi.pk).update(quantity_available=1)
        response = self.send('Yes', {'decision': 'confirm'}, reply='Sorry, only 1 Kopi C is left.')
        self.assertEqual(self.session.chat_state_id, 4)
        self.assertFalse(OrderItem.objects.exists())
        self.assertEqual(self.new_messages(2), [('customer', 'Yes'), ('business-automated', 'Sorry, only 1 Kopi C is left.')])
        self.assertEqual(response.json()['debug']['sent_messages'], [])

    def test_send_message_blocks_in_a_loop_send_each_once(self):
        blocks = [
            {'id': 1, 'next_block_id': 'a', 'block_type': 'START_BLOCK', 'position_x': 0, 'position_y': 0},
            {'id': 'a', 'next_block_id': 'b', 'block_type': 'SEND_MESSAGE_BLOCK', 'position_x': 0, 'position_y': 0, 'message': 'A'},
            {'id': 'b', 'next_block_id': 'a', 'block_type': 'SEND_MESSAGE_BLOCK', 'position_x': 0, 'position_y': 0, 'message': 'B'},
        ]
        self.chat_config.config_json = blocks
        self.chat_config.full_clean()
        self.chat_config.save()
        self.session.chat_state_id, self.session.chat_state_data = 1, {}
        self.session.save()
        response = self.send('I want to order', {'wants_to_order': True})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.new_messages(3), [('customer', 'I want to order'), ('business-automated', 'A'), ('business-automated', 'B')])
        self.assertIn('lead back to one already sent', response.json()['debug']['stop_reason'])


class RequiredAndOptionalDetailsFlowTests(APITestCase):
    """Required details hold the chat at Details collection until given; optional ones don't."""

    FIELDS = [
        {'key': 'name', 'label': 'Name', 'type': 'text'},
        {'key': 'boo', 'label': 'BOO', 'type': 'text'},  # an unusual label: asked for exactly as it is
        {'key': 'notes', 'label': 'Notes', 'type': 'text', 'required': False},
        {'key': 'phone', 'label': 'Phone', 'type': 'phone', 'required': False},
    ]

    @classmethod
    def setUpTestData(cls):
        cls.cafe = BusinessConfiguration.objects.create(business_name='Kopi Café', location='Tiong Bahru')
        cls.user = BusinessUser.objects.create_user(username='cafe', password='123', business=cls.cafe)
        blocks = [dict(block) for block in FULL_CONFIG]
        blocks[2]['fields'] = cls.FIELDS
        chat_config = ChatConfiguration.objects.create(business=cls.cafe, config_json=blocks)
        chat_config.full_clean()
        cls.kopi = Product.objects.create(business=cls.cafe, name='Kopi C', price='1.80', quantity_available=200)

    def setUp(self):
        self.session = ChatSession.objects.create(
            business=self.cafe,
            is_sandbox=True,
            chat_state_id='details',
            chat_state_data={
                'items': [{'product_id': self.kopi.pk, 'name': 'Kopi C', 'unit_price': '1.80', 'quantity': 1}],
                'items_confirmed': True,
            },
        )
        self.ollama = MagicMock()
        patcher = patch('chat_app.llm.get_client', return_value=self.ollama)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.client.force_authenticate(self.user)

    send = ChatFlowAPITests.send
    calls = ChatFlowAPITests.calls
    reply_prompt = ChatFlowAPITests.reply_prompt

    def test_ignoring_a_required_detail_keeps_the_chat_there_and_asking(self):
        self.send('Alice', {'name': 'Alice', 'boo': None, 'notes': None, 'phone': None})
        # The customer ignores the BOO question, twice: still at Details collection, no order.
        for message in ('Is my order confirmed?', 'Just confirm it please'):
            with self.subTest(message):
                self.send(message, {'name': None, 'boo': None, 'notes': None, 'phone': None})
                self.assertEqual(self.session.chat_state_id, 'details')
                self.assertNotIn('completed', self.session.chat_state_data)
                self.assertFalse(OrderItem.objects.exists())
                prompt = self.reply_prompt()
                self.assertIn('## Still needed\n- BOO\n', prompt)  # optional ones aren't "still needed"
                self.assertIn('the order is NOT confirmed yet', prompt)
                self.assertIn('Never tell the customer that their order is confirmed', prompt)
                self.assertIn('Keep asking in every reply until they give it', prompt)
                self.assertIn('if a label is "Boo", ask for "Boo"', prompt)
                self.assertIn('- "BOO" (required; text, at most 500 characters)', prompt)
                self.assertIn('- "Notes" (optional; text, at most 500 characters)', prompt)

    def test_optional_details_can_be_skipped(self):
        self.send('Alice, and BOO is 42', {'name': 'Alice', 'boo': '42', 'notes': None, 'phone': None})
        self.assertEqual(self.session.chat_state_id, 4)  # on to confirmation without notes or phone
        self.assertEqual(self.session.chat_state_data['details'], {'name': 'Alice', 'boo': '42'})

    def test_optional_details_are_kept_when_given(self):
        self.send('x', {'name': 'Alice', 'boo': 'yes', 'notes': 'Less ice', 'phone': '+65 9123 4567'})
        self.assertEqual(self.session.chat_state_id, 4)
        self.assertEqual(
            self.session.chat_state_data['details'],
            {'name': 'Alice', 'boo': 'yes', 'notes': 'Less ice', 'phone': '+65 9123 4567'},
        )

    def test_invalid_optional_detail_is_explained_but_does_not_block(self):
        response = self.send('x', {'name': 'Alice', 'boo': 'yes', 'notes': None, 'phone': 'call me'})
        self.assertEqual(self.session.chat_state_id, 4)
        self.assertNotIn('phone', self.session.chat_state_data['details'])
        self.assertIn('"call me" is not a valid phone number.', response.json()['debug']['steps'][0]['issues'])

    def test_optional_fields_are_still_extracted(self):
        self.send('x', {'name': None, 'boo': None, 'notes': None, 'phone': None})
        extraction = self.calls(structured=True)[0]
        self.assertEqual(extraction['format']['required'], ['name', 'boo', 'notes', 'phone'])
        self.assertIn('Take each label literally', extraction['messages'][0]['content'])


class CleanDetailValueTests(SimpleTestCase):
    def check(self, detail_field, raw):
        return clean_detail_value(detail_field, raw)

    def test_not_given(self):
        for raw in (None, '', '   ', True):
            with self.subTest(raw=raw):
                self.assertEqual(self.check({'key': 'a', 'label': 'A', 'type': 'text'}, raw), (None, None))

    def test_text(self):
        text = {'key': 'notes', 'label': 'Notes', 'type': 'text', 'max_length': 5}
        self.assertEqual(self.check(text, '  hello '), ('hello', None))
        self.assertEqual(self.check(text, 'too long'), (None, 'Notes is too long (max 5 characters).'))
        self.assertEqual(self.check({**text, 'max_length': 500}, 42), ('42', None))  # numbers become text
        self.assertEqual(self.check({'key': 'n', 'label': 'N', 'type': 'text'}, 'x' * 501)[0], None)  # default 500

    def test_number(self):
        number = {'key': 'qty', 'label': 'Guests', 'type': 'number', 'min_value': 1, 'max_value': 50}
        self.assertEqual(self.check(number, 20), (20, None))
        self.assertEqual(self.check(number, 2.0), (2, None))
        self.assertEqual(self.check(number, 2.5), (2.5, None))
        self.assertEqual(self.check(number, ' 12 '), (12, None))
        self.assertEqual(self.check(number, 'twelve'), (None, 'Guests must be a number (got "twelve").'))
        self.assertEqual(self.check(number, 'nan'), (None, 'Guests must be a number (got "nan").'))
        self.assertEqual(self.check(number, 0), (None, 'Guests must be at least 1.'))
        self.assertEqual(self.check(number, 51), (None, 'Guests must be at most 50.'))

    def test_email(self):
        email = {'key': 'email', 'label': 'Email', 'type': 'email'}
        self.assertEqual(self.check(email, ' a@b.co '), ('a@b.co', None))
        self.assertEqual(self.check(email, 'nope'), (None, '"nope" is not a valid email address.'))

    def test_phone(self):
        phone = {'key': 'phone', 'label': 'Phone', 'type': 'phone'}
        for valid in ('+65 9123 4567', '91234567', '(65) 9123-4567'):
            with self.subTest(valid):
                self.assertEqual(self.check(phone, valid), (valid, None))
        for invalid in ('12345', 'call me', '+65 9123 4567 8901 2345'):
            with self.subTest(invalid):
                self.assertIn('is not a valid phone number', self.check(phone, invalid)[1])


class ProductDescriptionToolFlowTests(APITestCase):
    """Asking about one product: the reply looks up its full description with get_product_description."""

    LONG_DESCRIPTION = (
        'Our signature kopi, brewed the traditional way. ' + 'Robusta beans roasted with butter and sugar. ' * 30
        + 'Contains dairy (evaporated milk). Ask for kopi-o if you would like it without milk.'
    )

    @classmethod
    def setUpTestData(cls):
        cls.cafe = BusinessConfiguration.objects.create(business_name='Kopi Café', location='Tiong Bahru')
        cls.user = BusinessUser.objects.create_user(username='cafe', password='123', business=cls.cafe)
        ChatConfiguration.objects.create(business=cls.cafe, config_json=FULL_CONFIG)
        cls.kopi = Product.objects.create(
            business=cls.cafe, name='Kopi C', price='1.80', quantity_available=20, description=cls.LONG_DESCRIPTION
        )

    def setUp(self):
        self.session = ChatSession.objects.create(business=self.cafe, is_sandbox=True, chat_state_id=1)
        self.ollama = MagicMock()
        patcher = patch('chat_app.llm.get_client', return_value=self.ollama)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.client.force_authenticate(self.user)

    def test_reply_looks_up_the_full_description(self):
        tool_call = SimpleNamespace(function=SimpleNamespace(name='get_product_description', arguments={'product': 'kopi c'}))
        responses = iter([
            fake_chat_response('{"wants_to_order": false}'),
            SimpleNamespace(message=SimpleNamespace(content='', tool_calls=[tool_call])),
            fake_chat_response('Yes, it contains dairy (evaporated milk).'),
        ])
        self.ollama.chat.side_effect = lambda **kwargs: next(responses)
        response = self.client.post(
            reverse('chat_app:sandbox-session-messages', args=[self.session.pk]),
            {'message': 'Does the Kopi C have milk in it?'},
            format='json',
        )
        self.assertEqual(response.json()['message'], 'Yes, it contains dairy (evaporated milk).')
        reply_calls = self.ollama.chat.call_args_list[1:]
        # The prompt only has the start of the description, and says how to get the rest honestly.
        prompt = reply_calls[0].kwargs['messages'][0]['content']
        self.assertIn('call get_product_description', prompt)
        self.assertIn('say honestly that you do not know', prompt)
        self.assertNotIn('Contains dairy', prompt)
        # The tool returned the whole description.
        tool_message = reply_calls[1].kwargs['messages'][-1]
        self.assertEqual(tool_message['tool_name'], 'get_product_description')
        self.assertEqual(json.loads(tool_message['content'])['description'], self.LONG_DESCRIPTION)
        self.assertEqual(
            response.json()['debug']['tool_calls'], [{'name': 'get_product_description', 'arguments': {'product': 'kopi c'}}]
        )


class FlowCheckTests(SimpleTestCase):
    """The deterministic checks of the LLM's extraction, one per block type."""

    def test_start(self):
        self.assertTrue(check_start({'wants_to_order': True}, {}, PRODUCTS, {}).complete)
        for extracted in ({'wants_to_order': False}, {}, {'wants_to_order': 'yes'}):
            self.assertFalse(check_start(extracted, {}, PRODUCTS, {}).complete)

    def test_product_selection_valid_choice_needs_confirming(self):
        data = {}
        chosen = {'items': [{'product_id': 1, 'quantity': 2}, {'product_id': 2, 'quantity': 3}]}
        # Chosen (even with "that's all" in the same message): recap first.
        result = check_product_selection({**chosen, 'done_choosing': True}, data, PRODUCTS, {})
        self.assertFalse(result.complete)
        self.assertIn('confirm that this is everything', result.missing[0])
        self.assertEqual([(i['name'], i['quantity'], i['unit_price']) for i in data['items']],
                         [('Kopi C', 2, '1.80'), ('Kaya Toast Set', 3, '5.50')])
        # Not done yet: still waiting.
        self.assertFalse(check_product_selection({**chosen, 'done_choosing': False}, data, PRODUCTS, {}).complete)
        # Done with the same cart (in any order): complete, and remembered.
        same = {'items': chosen['items'][::-1], 'done_choosing': True}
        self.assertTrue(check_product_selection(same, data, PRODUCTS, {}).complete)
        self.assertIs(data['items_confirmed'], True)

    def test_product_selection_change_clears_confirmation(self):
        data = {'items': [{'product_id': 1, 'name': 'Kopi C', 'unit_price': '1.80', 'quantity': 1}], 'items_confirmed': True}
        result = check_product_selection({'items': [{'product_id': 1, 'quantity': 2}], 'done_choosing': True}, data, PRODUCTS, {})
        self.assertFalse(result.complete)
        self.assertNotIn('items_confirmed', data)
        self.assertEqual(data['items'][0]['quantity'], 2)

    def test_product_selection_problem_blocks_completion(self):
        data = {'items': [{'product_id': 1, 'name': 'Kopi C', 'unit_price': '1.80', 'quantity': 1}], 'items_confirmed': True}
        result = check_product_selection(
            {'items': [{'product_id': 1, 'quantity': 1}, {'product_id': 2, 'quantity': 9}], 'done_choosing': True},
            data, PRODUCTS, {},
        )
        self.assertFalse(result.complete)
        self.assertIn('Only 3 Kaya Toast Set', result.issues[0])

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
                result = check_product_selection({'items': [item]}, {}, PRODUCTS, {})
                self.assertFalse(result.complete)
                self.assertIn(issue, result.issues[0])

    def test_product_selection_keeps_earlier_choice_when_nothing_new(self):
        earlier = {'items': [{'product_id': 1, 'name': 'Kopi C', 'unit_price': '1.80', 'quantity': 1}]}
        # Not confirmed yet: needs "that's all".
        self.assertFalse(check_product_selection({'items': [], 'done_choosing': False}, dict(earlier), PRODUCTS, {}).complete)
        self.assertTrue(check_product_selection({'items': [], 'done_choosing': True}, dict(earlier), PRODUCTS, {}).complete)
        # Already confirmed (e.g. back here after a "change" at confirmation): passes.
        confirmed = {**earlier, 'items_confirmed': True}
        self.assertTrue(check_product_selection({'items': [], 'done_choosing': False}, confirmed, PRODUCTS, {}).complete)
        result = check_product_selection({'items': [], 'done_choosing': True}, {}, PRODUCTS, {})
        self.assertFalse(result.complete)
        self.assertEqual(result.missing, ['which products, and how many of each'])

    def test_details_collection(self):
        data = {}
        result = check_details_collection({'name': ' Alice ', 'email': None}, data, PRODUCTS, DEFAULT_DETAILS_BLOCK)
        self.assertEqual((result.complete, result.missing), (False, ['Email']))
        self.assertEqual(data, {'details': {'name': 'Alice'}})

        result = check_details_collection({'name': None, 'email': 'not-an-email'}, data, PRODUCTS, DEFAULT_DETAILS_BLOCK)
        self.assertFalse(result.complete)
        self.assertIn('not a valid email address', result.issues[0])

        result = check_details_collection({'name': None, 'email': 'alice@example.com'}, data, PRODUCTS, DEFAULT_DETAILS_BLOCK)
        self.assertTrue(result.complete)
        self.assertEqual(data['details'], {'name': 'Alice', 'email': 'alice@example.com'})

    def test_details_collection_optional_fields(self):
        block = {'fields': [
            {'key': 'name', 'label': 'Name', 'type': 'text'},
            {'key': 'notes', 'label': 'Notes', 'type': 'text', 'max_length': 5, 'required': False},
        ]}
        data = {}
        result = check_details_collection({'name': 'Alice', 'notes': None}, data, PRODUCTS, block)
        self.assertEqual((result.complete, result.missing), (True, []))
        result = check_details_collection({'name': None, 'notes': 'far too long'}, {}, PRODUCTS, block)
        self.assertEqual(result.missing, ['Name'])  # optional Notes isn't missing; its problem is reported
        self.assertEqual(result.issues, ['Notes is too long (max 5 characters).'])
        # An invalid *required* value still blocks.
        result = check_details_collection({'name': 'x' * 501, 'notes': None}, {}, PRODUCTS, block)
        self.assertFalse(result.complete)

    def test_details_collection_nothing_given_adds_no_key(self):
        data = {}
        check_details_collection({'name': '', 'email': None}, data, PRODUCTS, DEFAULT_DETAILS_BLOCK)
        self.assertEqual(data, {})

    def test_confirmation(self):
        self.assertTrue(check_confirmation({'decision': 'confirm'}, {}, PRODUCTS, {}).complete)
        self.assertTrue(check_confirmation({'decision': 'change'}, {}, PRODUCTS, {}).go_back)
        result = check_confirmation({'decision': 'none'}, {}, PRODUCTS, {})
        self.assertFalse(result.complete or result.go_back)
