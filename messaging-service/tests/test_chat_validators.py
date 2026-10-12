"""Ported from configuration-service's chat_app/tests/test_models.py: the validators (pure
functions) and ChatSettings (ChatConfiguration.for_business / detail_fields_for). The model tests
(full_clean, database constraints, fixtures, migrations) stay in configuration-service."""

import copy
import unittest

from app.chat_flow.constants import CHAT_STEPS, DEFAULT_DETAIL_FIELDS, MESSAGE_SENDERS
from app.chat_flow.errors import ValidationError
from app.chat_flow.settings import ChatSettings
from app.chat_flow.validators import (
    CHAT_MESSAGE_MAX_LENGTH,
    default_detail_fields,
    detail_field_errors,
    is_required_detail,
    validate_chat_messages,
    validate_chat_state_data,
    validate_detail_fields,
)

from .chat_helpers import DatabaseTestCase

DETAIL_FIELDS = [
    {'key': 'name', 'label': 'Receiver name', 'type': 'text', 'max_length': 150},
    {'key': 'postal_code', 'label': 'Postal code', 'type': 'number', 'min_value': 100000, 'max_value': 999999},
    {'key': 'notes', 'label': 'Customisation notes', 'type': 'text', 'max_length': 200, 'description': 'e.g. less sugar'},
    {'key': 'email', 'label': 'Email', 'type': 'email', 'description': 'For the receipt'},
]
BOOKING_FIELDS = [
    {'key': 'name', 'label': 'Name', 'type': 'text', 'max_length': 150},
    {'key': 'people', 'label': 'Number of people', 'type': 'number', 'min_value': 1, 'max_value': 12},
]


class ChatStepsTests(unittest.TestCase):
    def test_steps_constant(self):
        self.assertEqual(CHAT_STEPS, [
            'start', 'product_selection', 'details_collection', 'confirmation',
            'service_selection', 'slot_selection', 'booking_details', 'booking_confirmation',
        ])


class ValidateDetailFieldsTests(unittest.TestCase):
    """ChatConfiguration.detail_fields (validate_detail_fields)."""

    def errors(self, value) -> list[str]:
        try:
            validate_detail_fields(value)
        except ValidationError as exc:
            return exc.messages
        return []

    def assertInvalid(self, fields, message_part):
        messages = self.errors(fields)
        self.assertTrue(any(message_part in m for m in messages), f'{message_part!r} not in {messages}')

    def test_valid_fields(self):
        validate_detail_fields(DETAIL_FIELDS)
        validate_detail_fields(DEFAULT_DETAIL_FIELDS)
        validate_detail_fields([{'key': 'a', 'label': 'A', 'type': 'number'}])  # no bounds
        validate_detail_fields([  # optional fields, on every type, next to a required one
            {'key': 'name', 'label': 'Name', 'type': 'text', 'required': True},
            {'key': 'notes', 'label': 'Notes', 'type': 'text', 'required': False},
            {'key': 'n', 'label': 'N', 'type': 'number', 'required': False},
            {'key': 'e', 'label': 'E', 'type': 'email', 'required': False},
        ])
        validate_detail_fields([{'key': 'x', 'label': 'X', 'type': 'number', 'min_value': 1.5, 'max_value': 1.5}])

    def test_invalid_fields(self):
        field = {'key': 'notes', 'label': 'Notes', 'type': 'text'}
        cases = {
            'not a list': ({'key': 'a'}, 'Details must be a list'),
            'null': (None, 'Details must be a list'),
            'empty': ([], 'There must be between 1 and 20 details'),
            'too many': ([{**field, 'key': f'f{i}'} for i in range(21)], 'There must be between 1 and 20 details'),
            'field not an object': (['notes'], 'Detail 0: must be an object'),
            'missing keys': ([{'key': 'notes'}], 'Detail 0: missing label, type'),
            'uppercase key': ([{**field, 'key': 'Notes'}], 'key must be lowercase letters'),
            'key with space': ([{**field, 'key': 'postal code'}], 'key must be lowercase letters'),
            'key starting with digit': ([{**field, 'key': '1st'}], 'key must be lowercase letters'),
            'key too long': ([{**field, 'key': 'k' * 41}], 'max 40 characters'),
            'duplicate key': ([field, {**field, 'label': 'Other'}], "Detail 1: duplicate key 'notes'"),
            'blank label': ([{**field, 'label': '  '}], 'label must be a non-blank string'),
            'label too long': ([{**field, 'label': 'x' * 101}], 'at most 100 characters'),
            'unknown type': ([{**field, 'type': 'date'}], 'type must be one of text, number, email'),
            'max_length on number': ([{**field, 'type': 'number', 'max_length': 5}], 'max_length not allowed for type number'),
            'min_value on text': ([{**field, 'min_value': 1}], 'min_value not allowed for type text'),
            'max_length on email': ([{**field, 'type': 'email', 'max_length': 5}], 'max_length not allowed for type email'),
            'unknown key': ([{**field, 'placeholder': 'x'}], 'placeholder not allowed for type text'),
            'required not a bool': ([{**field, 'required': 'yes'}], 'required must be true or false'),
            'all optional': ([{**field, 'required': False}], 'At least one detail must be required'),
            'max_length zero': ([{**field, 'max_length': 0}], 'max_length must be an integer from 1 to 2000'),
            'max_length too big': ([{**field, 'max_length': 2001}], 'max_length must be an integer from 1 to 2000'),
            'max_length bool': ([{**field, 'max_length': True}], 'max_length must be an integer from 1 to 2000'),
            'min greater than max': ([{**field, 'type': 'number', 'min_value': 10, 'max_value': 1}], 'min_value must not be greater'),
            'bound not a number': ([{**field, 'type': 'number', 'min_value': '1'}], 'min_value and max_value must be numbers'),
            'description too long': ([{**field, 'description': 'x' * 301}], 'description must be a string of at most 300'),
            'description not a string': ([{**field, 'description': 5}], 'description must be a string'),
        }
        for label, (fields, message_part) in cases.items():
            with self.subTest(label):
                self.assertInvalid(fields, message_part)
                # detail_field_errors lists the same messages, without raising.
                self.assertEqual(detail_field_errors(fields), self.errors(fields))

    def test_every_field_error_is_listed(self):
        messages = self.errors([
            {'key': 'Bad', 'label': '', 'type': 'text'},
            {'key': 'ok', 'label': 'OK', 'type': 'number', 'min_value': 5, 'max_value': 1},
        ])
        self.assertEqual(len(messages), 3, messages)


class ChatConfigurationModelTests(DatabaseTestCase):
    """The validator and ChatSettings parts of the Django model tests (ChatSettings replaces
    ChatConfiguration.for_business / detail_fields_for; full_clean and the constraints stay in Django)."""

    def setUp(self):
        super().setUp()
        self.business = self.make.business('Test Café')

    def test_no_phone_type(self):
        # Customers chat on WhatsApp: the chat already has their number.
        with self.assertRaises(ValidationError) as ctx:
            validate_detail_fields([{'key': 'name', 'label': 'Name', 'type': 'text'}, {'key': 'phone', 'label': 'Phone', 'type': 'phone'}])
        self.assertIn('type must be one of text, number, email', ctx.exception.messages[0])

    def test_default_detail_fields(self):
        # Both lists default to a required name and email, each its own copy.
        chat_config = ChatSettings(business=self.business)
        self.assertEqual(chat_config.product_detail_fields, DEFAULT_DETAIL_FIELDS)
        self.assertEqual(chat_config.schedule_detail_fields, DEFAULT_DETAIL_FIELDS)
        self.assertEqual([f['key'] for f in DEFAULT_DETAIL_FIELDS], ['name', 'email'])
        self.assertTrue(all(is_required_detail(f) for f in DEFAULT_DETAIL_FIELDS))
        chat_config.product_detail_fields[0]['label'] = 'Changed'
        self.assertEqual(chat_config.schedule_detail_fields[0]['label'], 'Name')
        self.assertEqual(ChatSettings(business=self.business).product_detail_fields[0]['label'], 'Name')
        self.assertEqual(default_detail_fields()[0]['label'], 'Name')

    def test_the_two_lists_are_independent(self):
        self.make.chat_config(self.business, product_detail_fields=DETAIL_FIELDS, schedule_detail_fields=BOOKING_FIELDS)
        with self.sessions() as db:
            chat_config = ChatSettings.for_business(db, self.business)
        self.assertEqual((chat_config.product_detail_fields, chat_config.schedule_detail_fields), (DETAIL_FIELDS, BOOKING_FIELDS))
        # The order steps (and Start) ask for the product details, the booking steps for the schedule ones.
        for step in ('start', 'product_selection', 'details_collection', 'confirmation'):
            self.assertEqual(chat_config.detail_fields_for(step), DETAIL_FIELDS, step)
        for step in ('service_selection', 'slot_selection', 'booking_details', 'booking_confirmation'):
            self.assertEqual(chat_config.detail_fields_for(step), BOOKING_FIELDS, step)

    def test_for_business_returns_the_saved_one_or_the_defaults(self):
        from app.models import ChatConfiguration

        with self.sessions() as db:
            unsaved = ChatSettings.for_business(db, self.business)
        self.assertEqual((unsaved.business, unsaved.product_detail_fields), (self.business, DEFAULT_DETAIL_FIELDS))
        self.assertEqual(unsaved.schedule_detail_fields, DEFAULT_DETAIL_FIELDS)
        self.assertEqual(self.all(ChatConfiguration), [])  # nothing saved
        self.make.chat_config(self.business, product_detail_fields=DETAIL_FIELDS)
        with self.sessions() as db:
            self.assertEqual(ChatSettings.for_business(db, self.business).product_detail_fields, DETAIL_FIELDS)


VALID_MESSAGES = [
    {'message': 'Hi, can I order?', 'sent_by': 'customer', 'message_time': '2026-09-01T09:00:00+08:00'},
    {'message': 'Sure! What would you like?', 'sent_by': 'business-automated', 'message_time': '2026-09-01T09:00:05+08:00'},
    {'message': 'I will help you here.', 'sent_by': 'business-manual', 'message_time': '2026-09-01T01:05:00Z'},
]


def messages(**changes_by_index):
    """A copy of VALID_MESSAGES, with e.g. `m1={'sent_by': 'X'}` merged into message 1."""
    items = copy.deepcopy(VALID_MESSAGES)
    for key, changes in changes_by_index.items():
        items[int(key[1:])].update(changes)
    return items


class ValidateChatMessagesTests(unittest.TestCase):
    def assertInvalid(self, value, message_part):
        with self.assertRaises(ValidationError) as ctx:
            validate_chat_messages(value)
        self.assertTrue(
            any(message_part in message for message in ctx.exception.messages),
            f'{message_part!r} not in {ctx.exception.messages}',
        )

    def test_valid_messages(self):
        validate_chat_messages(VALID_MESSAGES)

    def test_empty_list_is_valid(self):
        validate_chat_messages([])

    def test_senders_constant(self):
        self.assertEqual(MESSAGE_SENDERS, ['customer', 'business-manual', 'business-automated'])

    def test_not_a_list(self):
        for bad in ({'message': 'hi'}, None, 'hi', 1):
            with self.subTest(value=bad):
                self.assertInvalid(bad, 'must be a list')

    def test_item_not_an_object(self):
        self.assertInvalid([*VALID_MESSAGES, 'hi'], 'must be an object')

    def test_missing_and_unknown_fields(self):
        items = messages()
        del items[0]['sent_by']
        self.assertInvalid(items, 'missing field(s) sent_by')
        self.assertInvalid(messages(m0={'read': True}), 'unknown field(s) read')

    def test_message_must_be_non_blank_string(self):
        for bad in ('', '   ', None, 42, ['hi']):
            with self.subTest(message=bad):
                self.assertInvalid(messages(m0={'message': bad}), 'message must be a non-blank string')

    def test_message_length_limit(self):
        validate_chat_messages(messages(m0={'message': 'x' * CHAT_MESSAGE_MAX_LENGTH}))
        self.assertInvalid(messages(m0={'message': 'x' * (CHAT_MESSAGE_MAX_LENGTH + 1)}), 'at most')

    def test_invalid_sent_by(self):
        for bad in ('business', 'Customer', 'business_manual', None):
            with self.subTest(sent_by=bad):
                self.assertInvalid(messages(m1={'sent_by': bad}), 'sent_by must be one of')

    def test_invalid_message_time(self):
        for bad in ('yesterday', '2026-13-01T09:00:00+08:00', '09:00', 1767225600, None):
            with self.subTest(message_time=bad):
                self.assertInvalid(messages(m0={'message_time': bad}), 'ISO 8601')

    def test_message_time_needs_timezone(self):
        for bad in ('2026-09-01T09:00:00', '2026-09-01'):  # a date alone parses as local midnight
            with self.subTest(message_time=bad):
                self.assertInvalid(messages(m0={'message_time': bad}), 'must include a timezone')

    def test_messages_must_be_in_order(self):
        # 00:59Z is 08:59+08:00, before message 1's 09:00:05+08:00.
        self.assertInvalid(messages(m2={'message_time': '2026-09-01T00:59:00Z'}), 'earlier than the previous')

    def test_reports_all_errors(self):
        with self.assertRaises(ValidationError) as ctx:
            validate_chat_messages(messages(m0={'message': ''}, m1={'sent_by': 'bot', 'message_time': 'x'}))
        self.assertEqual(len(ctx.exception.messages), 3)


VALID_STATE_DATA = {
    'items': [{'product_id': 1, 'name': 'Kopi C', 'unit_price': '1.80', 'quantity': 2}],
    'details': {'name': 'Alice', 'email': 'alice@example.com'},
    'items_confirmed': True,
    'last_order_id': 3,
}


class ValidateChatStateDataTests(unittest.TestCase):
    def assertInvalid(self, value, message_part):
        with self.assertRaises(ValidationError) as ctx:
            validate_chat_state_data(value)
        self.assertTrue(
            any(message_part in message for message in ctx.exception.messages),
            f'{message_part!r} not in {ctx.exception.messages}',
        )

    def test_valid(self):
        validate_chat_state_data(VALID_STATE_DATA)
        validate_chat_state_data({})  # nothing collected yet
        validate_chat_state_data({'details': {'name': 'Alice'}})  # partial details
        validate_chat_state_data({'details': {'postal_code': 123456, 'notes': 'No sugar', 'weight_kg': 1.5}})

    def test_invalid(self):
        item = VALID_STATE_DATA['items'][0]
        cases = {
            'not an object': ([], 'must be an object'),
            'unknown field': ({'cart': []}, 'Unknown field(s) cart'),
            'items not a list': ({'items': {}}, 'items must be a list'),
            'item missing field': ({'items': [{'product_id': 1}]}, 'Item 0: must be an object with exactly'),
            'product_id not int': ({'items': [{**item, 'product_id': '1'}]}, 'product_id must be an integer'),
            'blank name': ({'items': [{**item, 'name': ' '}]}, 'name must be a non-blank string'),
            'numeric price': ({'items': [{**item, 'unit_price': 1.8}]}, 'unit_price must be a decimal string'),
            'zero quantity': ({'items': [{**item, 'quantity': 0}]}, 'quantity must be an integer of at least 1'),
            'bool quantity': ({'items': [{**item, 'quantity': True}]}, 'quantity must be an integer of at least 1'),
            'details not object': ({'details': 'Alice'}, 'details must be an object'),
            'invalid detail key': ({'details': {'Postal Code': '123'}}, "details: invalid key 'Postal Code'"),
            'blank detail': ({'details': {'email': ''}}, 'details: email must be a non-blank string or a number'),
            'bool detail': ({'details': {'agreed': True}}, 'details: agreed must be a non-blank string or a number'),
            'list detail': ({'details': {'notes': ['a']}}, 'details: notes must be a non-blank string or a number'),
            'old completed flag': ({'completed': True}, 'Unknown field(s) completed'),
            'last_order_id zero': ({'last_order_id': 0}, 'last_order_id must be a positive integer'),
            'last_order_id text': ({'last_order_id': '3'}, 'last_order_id must be a positive integer'),
            'items_confirmed not bool': ({'items_confirmed': 1}, 'items_confirmed must be true or false'),
        }
        for label, (value, message_part) in cases.items():
            with self.subTest(label):
                self.assertInvalid(value, message_part)
