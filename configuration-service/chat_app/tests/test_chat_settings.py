from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from auth_app.models import BusinessUser
from configuration_app.models import BusinessConfiguration

from ..constants import (
    CUSTOM_STYLE_MAX_LENGTH,
    DEFAULT_DETAIL_FIELDS,
    REPLY_STYLE_PRESETS,
    REPLY_STYLES,
    WELCOME_MESSAGE_MAX_LENGTH,
)
from ..models import ChatConfiguration
from ..validators import validate_welcome_message

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

