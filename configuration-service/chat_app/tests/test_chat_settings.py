from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from auth_app.models import BusinessUser
from configuration_app.models import BusinessConfiguration
from product_app.models import Product

from ..constants import (
    CUSTOM_STYLE_MAX_LENGTH,
    DEFAULT_DETAIL_FIELDS,
    REPLY_STYLE_PRESETS,
    REPLY_STYLES,
    WELCOME_MESSAGE_MAX_LENGTH,
)
from ..models import ChatConfiguration, ChatSession
from ..prompts import (
    BUSINESS_STYLE_INTRO,
    WELCOMED_NOTE,
    build_aside_prompt,
    build_order_status_prompt,
    build_reply_prompt,
    reply_style_section,
    welcome_message_text,
)
from ..validators import validate_welcome_message
from .test_flow import FlowTestMixin

WELCOME = 'Hi, welcome to {business_name}! Ask me about our menu, or order for pickup.'


class ChatSettingsModelTests(TestCase):
    """ChatConfiguration.welcome_message / reply_style / custom_style: defaults, limits and rules."""

    @classmethod
    def setUpTestData(cls):
        cls.business = BusinessConfiguration.objects.create(business_name='Kopi Café', location='Singapore')

    def make(self, **fields):
        return ChatConfiguration(business=self.business, **fields)

    def test_defaults(self):
        config = ChatConfiguration.for_business(self.business)
        self.assertEqual((config.welcome_message, config.reply_style, config.custom_style), ('', 'friendly', ''))
        self.make().full_clean()

    def test_welcome_message_length_limit(self):
        self.make(welcome_message='x' * WELCOME_MESSAGE_MAX_LENGTH).full_clean()
        with self.assertRaises(ValidationError) as ctx:
            self.make(welcome_message='x' * (WELCOME_MESSAGE_MAX_LENGTH + 1)).full_clean()
        self.assertIn('welcome_message', ctx.exception.message_dict)

    def test_welcome_message_placeholders(self):
        validate_welcome_message(WELCOME)
        validate_welcome_message('Hello! No placeholders at all.')
        for text in ('Hi {name}!', 'Hi {business_name} and {customer}', 'A stray { brace', 'Closing } brace', '{}'):
            with self.subTest(text=text), self.assertRaises(ValidationError) as ctx:
                validate_welcome_message(text)
            self.assertIn('the only one you can use is {business_name}', ctx.exception.messages[0])

    def test_reply_style_must_be_known(self):
        for style in REPLY_STYLES[:-1]:
            self.make(reply_style=style).full_clean()
        with self.assertRaises(ValidationError):
            self.make(reply_style='shouty').full_clean()
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.make(reply_style='shouty').save()

    def test_custom_style_needs_a_description(self):
        self.make(reply_style='custom', custom_style='Short and cheerful, sign off with "Cheers!"').full_clean()
        for custom in ('', '   '):
            with self.subTest(custom=custom), self.assertRaises(ValidationError) as ctx:
                self.make(reply_style='custom', custom_style=custom).full_clean()
            self.assertIn('custom_style', ctx.exception.message_dict)
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.make(reply_style='custom', custom_style='').save()

    def test_custom_style_length_limit(self):
        self.make(reply_style='custom', custom_style='x' * CUSTOM_STYLE_MAX_LENGTH).full_clean()
        with self.assertRaises(ValidationError) as ctx:
            self.make(reply_style='custom', custom_style='x' * (CUSTOM_STYLE_MAX_LENGTH + 1)).full_clean()
        self.assertIn('custom_style', ctx.exception.message_dict)


class ChatSettingsAPITests(APITestCase):
    """GET / PUT /api/chat/configuration/ with the welcome message and reply style, and the styles list."""

    url = reverse('chat_app:chat-configuration')
    styles_url = reverse('chat_app:reply-style-list')

    @classmethod
    def setUpTestData(cls):
        cls.cafe = BusinessConfiguration.objects.create(business_name='Kopi Café', location='Singapore')
        cls.user = BusinessUser.objects.create_user(username='cafe', password='123', business=cls.cafe)

    def setUp(self):
        self.client.force_authenticate(self.user)

    def put(self, **fields):
        return self.client.put(self.url, {'product_detail_fields': DEFAULT_DETAIL_FIELDS, **fields}, format='json')

    def test_save_the_welcome_message_and_style(self):
        response = self.put(welcome_message=f'  {WELCOME}  ', reply_style='professional')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.content)
        body = response.json()
        self.assertEqual((body['welcome_message'], body['reply_style'], body['custom_style']), (WELCOME, 'professional', ''))
        config = ChatConfiguration.objects.get(business=self.cafe)
        self.assertEqual((config.welcome_message, config.reply_style), (WELCOME, 'professional'))
        self.assertEqual(self.client.get(self.url).json()['welcome_message'], WELCOME)

    def test_custom_style(self):
        response = self.put(reply_style='custom', custom_style='Cheerful, and always sign off with "Cheers!"')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.content)
        self.assertEqual(response.json()['custom_style'], 'Cheerful, and always sign off with "Cheers!"')
        # Back to a preset: the custom text is kept, unused.
        response = self.put(reply_style='brief')
        self.assertEqual((response.json()['reply_style'], response.json()['custom_style']), ('brief', 'Cheerful, and always sign off with "Cheers!"'))

    def test_the_settings_are_kept_when_a_put_leaves_them_out(self):
        self.put(welcome_message=WELCOME, reply_style='casual')
        response = self.put()  # e.g. an older client that only sends the detail fields
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual((response.json()['welcome_message'], response.json()['reply_style']), (WELCOME, 'casual'))
        self.assertEqual(self.put(welcome_message='').json()['welcome_message'], '')  # blank: switched off

    def test_invalid_settings(self):
        for fields, field in (
            ({'welcome_message': 'x' * (WELCOME_MESSAGE_MAX_LENGTH + 1)}, 'welcome_message'),
            ({'welcome_message': 'Hi {customer_name}!'}, 'welcome_message'),
            ({'reply_style': 'shouty'}, 'reply_style'),
            ({'reply_style': 'custom'}, 'custom_style'),
            ({'reply_style': 'custom', 'custom_style': '   '}, 'custom_style'),
            ({'reply_style': 'custom', 'custom_style': 'x' * (CUSTOM_STYLE_MAX_LENGTH + 1)}, 'custom_style'),
        ):
            with self.subTest(fields=list(fields)):
                response = self.put(**fields)
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn(field, response.json())
        self.assertFalse(ChatConfiguration.objects.exists())

    def test_reply_styles(self):
        response = self.client.get(self.styles_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        styles = response.json()
        self.assertEqual([style['key'] for style in styles], REPLY_STYLES)
        self.assertEqual(styles[0], {'key': 'friendly', **REPLY_STYLE_PRESETS['friendly']})
        self.assertEqual((styles[-1]['key'], styles[-1]['instructions']), ('custom', None))
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(self.styles_url).status_code, status.HTTP_401_UNAUTHORIZED)


class StylePromptTests(SimpleTestCase):
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


class WelcomeFlowTests(FlowTestMixin, APITestCase):
    """The welcome message on a chat's first message, and the reply style, in the chat flow."""

    @classmethod
    def setUpTestData(cls):
        cls.cafe = BusinessConfiguration.objects.create(business_name='Kopi Café', location='Tiong Bahru')
        cls.user = BusinessUser.objects.create_user(username='cafe', password='123', business=cls.cafe)
        cls.kopi = Product.objects.create(business=cls.cafe, name='Kopi C', price='1.80', total_quantity=20)

    def setUp(self):
        self.config = ChatConfiguration.objects.create(business=self.cafe, welcome_message=WELCOME)
        self.session = ChatSession.objects.create(business=self.cafe, is_sandbox=True)
        self.mock_llm()
        self.client.force_authenticate(self.user)

    welcome_text = 'Hi, welcome to Kopi Café! Ask me about our menu, or order for pickup.'

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
        self.config.welcome_message = ''
        self.config.save()
        response = self.send('hi', reply='Hello! How can I help?', intents=[])
        self.assertEqual(response.json()['message'], 'Hello! How can I help?')
        self.assertEqual(response.json()['debug']['reply_kind'], 'llm')
        self.assertEqual(self.chat(), [('customer', 'hi'), ('business-automated', 'Hello! How can I help?')])

    def test_the_reply_style_is_in_the_reply_prompt(self):
        self.config.welcome_message = ''
        self.config.reply_style = 'custom'
        self.config.custom_style = 'Always end with "Cheers!"'
        self.config.save()
        self.send('Are you open today?', intents=[])
        prompt = self.reply_prompt()
        self.assertIn(f'## How to write\n{BUSINESS_STYLE_INTRO}\n"Always end with "Cheers!""', prompt)
        self.assertNotIn(REPLY_STYLE_PRESETS['friendly']['instructions'], prompt)
