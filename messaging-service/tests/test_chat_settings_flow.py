"""Ported from configuration-service's chat_app/tests/test_chat_settings.py: the chat flow's use of
the welcome message and the reply style (the configuration API stays in configuration-service)."""

import unittest

from app.chat_flow.constants import DEFAULT_DETAIL_FIELDS, REPLY_STYLE_PRESETS
from app.chat_flow.errors import ValidationError
from app.chat_flow.prompts import (
    BUSINESS_STYLE_INTRO,
    WELCOMED_NOTE,
    build_aside_prompt,
    build_order_status_prompt,
    build_reply_prompt,
    reply_style_section,
    welcome_message_text,
)
from app.chat_flow.settings import ChatSettings
from app.chat_flow.validators import validate_welcome_message
from app.models import BusinessConfiguration, ChatConfiguration

from .chat_helpers import ApiTestCase, DatabaseTestCase, FlowTestMixin

WELCOME = 'Hi, welcome to {business_name}! Ask me about our menu, or order for pickup.'


class ChatSettingsModelTests(DatabaseTestCase):
    """The defaults (ChatSettings.for_business) and the welcome message's placeholders. (The model's
    full_clean / database constraints stay in configuration-service.)"""

    def setUp(self):
        super().setUp()
        self.business = self.make.business('Kopi Café')

    def test_defaults(self):
        with self.sessions() as db:
            config = ChatSettings.for_business(db, self.business)
        self.assertEqual((config.welcome_message, config.reply_style, config.custom_style), ('', 'friendly', ''))

    def test_welcome_message_placeholders(self):
        validate_welcome_message(WELCOME)
        validate_welcome_message('Hello! No placeholders at all.')
        for text in ('Hi {name}!', 'Hi {business_name} and {customer}', 'A stray { brace', 'Closing } brace', '{}'):
            with self.subTest(text=text), self.assertRaises(ValidationError) as ctx:
                validate_welcome_message(text)
            self.assertIn('the only one you can use is {business_name}', ctx.exception.messages[0])


class StylePromptTests(unittest.TestCase):
    """The reply prompts' "How to write" section, and the welcome message text."""

    business = BusinessConfiguration(business_name='Kopi Café', description='A café.', location='Tiong Bahru')

    def test_presets(self):
        for key, meta in REPLY_STYLE_PRESETS.items():
            with self.subTest(style=key):
                section = reply_style_section(key)
                self.assertTrue(section.startswith('## How to write\n' + meta['instructions']))
                self.assertIn('It never changes the rules', section)
        self.assertEqual(reply_style_section('unknown'), reply_style_section('friendly'))
        self.assertEqual(reply_style_section(), reply_style_section('friendly'))

    def test_custom(self):
        section = reply_style_section('custom', '  Talk like a friendly pirate.  ')
        self.assertIn(f'{BUSINESS_STYLE_INTRO}\n"Talk like a friendly pirate."', section)
        self.assertIn('never make anything up', section)
        self.assertEqual(reply_style_section('custom', ''), reply_style_section('friendly'))  # nothing given: the default

    def test_every_reply_prompt_gets_the_style(self):
        style = reply_style_section('professional')
        prompts = [
            build_reply_prompt(self.business, 'start', {}, products=[], fields=DEFAULT_DETAIL_FIELDS, style=style),
            build_aside_prompt(self.business, context='The summary is sent next.', style=style),
            build_order_status_prompt(self.business, '- Order #1 …', style=style),
        ]
        for prompt in prompts:
            self.assertIn(style, prompt)
            self.assertNotIn(REPLY_STYLE_PRESETS['friendly']['instructions'], prompt)
        default = build_reply_prompt(self.business, 'start', {}, products=[], fields=DEFAULT_DETAIL_FIELDS)
        self.assertIn(REPLY_STYLE_PRESETS['friendly']['instructions'], default)

    def test_welcomed_note(self):
        reply = build_reply_prompt(self.business, 'start', {}, products=[], fields=DEFAULT_DETAIL_FIELDS, welcomed=True)
        self.assertIn(WELCOMED_NOTE, reply)
        self.assertNotIn(WELCOMED_NOTE, build_reply_prompt(self.business, 'start', {}, products=[], fields=DEFAULT_DETAIL_FIELDS))
        self.assertTrue(build_order_status_prompt(self.business, '-', welcomed=True).endswith(WELCOMED_NOTE))

    def test_welcome_message_text(self):
        self.assertEqual(
            welcome_message_text(self.business, f'  {WELCOME}\n'),
            'Hi, welcome to Kopi Café! Ask me about our menu, or order for pickup.',
        )


class WelcomeFlowTests(FlowTestMixin, ApiTestCase):
    """The welcome message on a chat's first message, and the reply style, in the chat flow."""

    def setUp(self):
        super().setUp()
        self.cafe = self.make.business('Kopi Café', location='Tiong Bahru')
        self.user = self.make.user(self.cafe, username='cafe')
        self.kopi = self.make.product(self.cafe, 'Kopi C', '1.80', total_quantity=20)
        self.config = self.make.chat_config(self.cafe, welcome_message=WELCOME)
        self.session = self.make.session(self.cafe, is_sandbox=True)
        self.mock_llm()
        self.login(self.user)

    welcome_text = 'Hi, welcome to Kopi Café! Ask me about our menu, or order for pickup.'

    def update_config(self, **fields):
        """config.<field> = …; config.save()"""
        with self.sessions.begin() as db:
            config = db.get(ChatConfiguration, self.config.id)
            for name, value in fields.items():
                setattr(config, name, value)

    def chat(self):
        return [(m['sent_by'], m['message']) for m in self.session.chat_message_json]

    def test_a_first_hi_gets_only_the_welcome_message(self):
        response = self.send('hi', reply='Hello there!', intents=[])
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['message'], self.welcome_text)
        self.assertEqual([m['message'] for m in body['messages']], [self.welcome_text])
        self.assertEqual(body['debug']['reply_kind'], 'welcome')
        self.assertEqual(body['debug']['welcome_message'], self.welcome_text)
        self.assertEqual(body['debug']['reply_system_prompt'], '')
        self.assertEqual(self.ollama.chat.call_count, 1)  # only the router: no reply call
        self.assertEqual(self.chat(), [('customer', 'hi'), ('business-automated', self.welcome_text)])

    def test_a_first_message_asking_for_something_gets_the_welcome_then_the_reply(self):
        response = self.send(
            '2 Kopi C please', {'items': [{'product_id': self.kopi.pk, 'quantity': 2}], 'done_choosing': False},
            reply='2 Kopi C, anything else?', intents=['order'],
        )
        body = response.json()
        self.assertEqual(body['message'], '2 Kopi C, anything else?')
        self.assertEqual([m['message'] for m in body['messages']], [self.welcome_text, '2 Kopi C, anything else?'])
        self.assertEqual(body['debug']['reply_kind'], 'llm')
        self.assertEqual(
            self.chat(),
            [('customer', '2 Kopi C please'), ('business-automated', self.welcome_text), ('business-automated', '2 Kopi C, anything else?')],
        )
        reply_call = self.calls(structured=False)[-1]
        self.assertIn(WELCOMED_NOTE, reply_call['messages'][0]['content'])
        self.assertEqual(reply_call['messages'][-1], {'role': 'assistant', 'content': self.welcome_text})  # it saw the welcome

    def test_only_on_the_first_message(self):
        self.send('hi', intents=[])
        response = self.send('Are you open today?', reply='Yes, until 6pm.', intents=[])
        self.assertEqual(response.json()['message'], 'Yes, until 6pm.')
        self.assertEqual(len(response.json()['messages']), 1)
        self.assertIsNone(response.json()['debug']['welcome_message'])
        self.assertNotIn(WELCOMED_NOTE, self.reply_prompt())
        self.assertEqual([m['message'] for m in self.session.chat_message_json].count(self.welcome_text), 1)

    def test_no_welcome_message_when_blank(self):
        self.update_config(welcome_message='')
        response = self.send('hi', reply='Hello! How can I help?', intents=[])
        self.assertEqual(response.json()['message'], 'Hello! How can I help?')
        self.assertEqual(response.json()['debug']['reply_kind'], 'llm')
        self.assertEqual(self.chat(), [('customer', 'hi'), ('business-automated', 'Hello! How can I help?')])

    def test_the_reply_style_is_in_the_reply_prompt(self):
        self.update_config(welcome_message='', reply_style='custom', custom_style='Always end with "Cheers!"')
        self.send('Are you open today?', intents=[])
        prompt = self.reply_prompt()
        self.assertIn(f'## How to write\n{BUSINESS_STYLE_INTRO}\n"Always end with "Cheers!""', prompt)
        self.assertNotIn(REPLY_STYLE_PRESETS['friendly']['instructions'], prompt)
