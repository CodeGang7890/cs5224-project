import copy
import json
import uuid

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import SimpleTestCase, TestCase

from configuration_app.models import BusinessConfiguration

from ..constants import BLOCK_TYPES, MESSAGE_SENDERS
from ..models import ChatConfiguration, ChatSession
from ..validators import (
    CHAT_MESSAGE_MAX_LENGTH,
    block_detail_fields,
    is_required_detail,
    validate_chat_config,
    validate_chat_messages,
    validate_chat_state_data,
)

VALID_CONFIG = [
    {'id': 1, 'next_block_id': 2, 'block_type': 'START_BLOCK', 'position_x': 100, 'position_y': 100},
    {'id': 2, 'next_block_id': 3, 'block_type': 'PRODUCT_SELECTION_BLOCK', 'position_x': 300, 'position_y': 100},
    {'id': 3, 'next_block_id': None, 'block_type': 'CONFIRMATION_BLOCK', 'position_x': 500, 'position_y': 100},
]


def config(**changes_by_index):
    """A copy of VALID_CONFIG, with e.g. `b1={'block_type': 'X'}` merged into block 1."""
    blocks = copy.deepcopy(VALID_CONFIG)
    for key, changes in changes_by_index.items():
        blocks[int(key[1:])].update(changes)
    return blocks


class ValidateChatConfigTests(SimpleTestCase):
    def assertInvalid(self, value, message_part):
        with self.assertRaises(ValidationError) as ctx:
            validate_chat_config(value)
        self.assertTrue(
            any(message_part in message for message in ctx.exception.messages),
            f'{message_part!r} not in {ctx.exception.messages}',
        )

    def test_valid_config(self):
        validate_chat_config(VALID_CONFIG)

    def test_block_types_constant(self):
        self.assertEqual(
            BLOCK_TYPES,
            ['START_BLOCK', 'PRODUCT_SELECTION_BLOCK', 'DETAILS_COLLECTION_BLOCK', 'CONFIRMATION_BLOCK', 'SEND_MESSAGE_BLOCK'],
        )

    def test_every_block_type_accepted(self):
        blocks = [
            {'id': str(i), 'next_block_id': None, 'block_type': t, 'position_x': 0, 'position_y': 0}
            for i, t in enumerate(BLOCK_TYPES)
        ]
        blocks[-1]['message'] = 'Thanks for your order!'  # SEND_MESSAGE_BLOCK requires one
        validate_chat_config(blocks)

    def test_non_start_blocks_can_repeat(self):
        blocks = config()
        blocks.append({**blocks[2], 'id': 4})
        blocks[2]['next_block_id'] = 4
        validate_chat_config(blocks)

    def test_uuid_ids_and_forward_references(self):
        start, product, end = (str(uuid.uuid4()) for _ in range(3))
        blocks = config(
            b0={'id': start, 'next_block_id': product},
            b1={'id': product, 'next_block_id': end},
            b2={'id': end},
        )
        validate_chat_config(list(reversed(blocks)))  # START_BLOCK doesn't have to come first

    def test_float_positions_accepted(self):
        validate_chat_config(config(b0={'position_x': 12.5, 'position_y': -3.25}))

    def test_not_a_list(self):
        for bad in ({'id': 1}, None, 'START_BLOCK', 42, True):
            with self.subTest(value=bad):
                self.assertInvalid(bad, 'must be a list')

    def test_json_encoded_string_is_not_parsed(self):
        # The value must already be a list, not a JSON string of one.
        self.assertInvalid(json.dumps(VALID_CONFIG), 'must be a list')

    def test_nested_list_rejected(self):
        self.assertInvalid([VALID_CONFIG], 'must be an object')

    def test_block_type_is_case_sensitive(self):
        self.assertInvalid(config(b1={'block_type': 'product_selection_block'}), 'block_type must be one of')

    def test_block_not_an_object(self):
        self.assertInvalid([*VALID_CONFIG, 'oops'], 'must be an object')

    def test_missing_and_unknown_fields(self):
        blocks = config()
        del blocks[1]['position_y']
        self.assertInvalid(blocks, 'missing field(s) position_y')
        self.assertInvalid(config(b1={'colour': 'red'}), 'unknown field(s) colour')

    def test_invalid_block_type(self):
        self.assertInvalid(config(b1={'block_type': 'PAYMENT_BLOCK'}), 'block_type must be one of')

    def test_exactly_one_start_block(self):
        self.assertInvalid(config(b1={'block_type': 'START_BLOCK'}), 'exactly one START_BLOCK (found 2)')
        self.assertInvalid(config(b0={'block_type': 'CONFIRMATION_BLOCK'}), 'exactly one START_BLOCK (found 0)')
        self.assertInvalid([], 'exactly one START_BLOCK (found 0)')

    def test_duplicate_id(self):
        self.assertInvalid(config(b2={'id': 1}), 'duplicate id 1')

    def test_invalid_id_types(self):
        for bad in (None, True, '', '  ', 1.5, [1], {'a': 1}):
            with self.subTest(id=bad):
                self.assertInvalid(config(b2={'id': bad}), 'id must be an integer or a non-blank string')

    def test_next_block_id_must_exist(self):
        self.assertInvalid(config(b2={'next_block_id': 99}), 'next_block_id 99 does not match any block id')
        # Types must match exactly: '2' is not the block with id 2.
        self.assertInvalid(config(b0={'next_block_id': '2'}), "next_block_id '2' does not match")

    def test_next_block_id_cannot_point_at_itself(self):
        self.assertInvalid(config(b2={'next_block_id': 3}), 'must not point at the block itself')

    def test_invalid_next_block_id_type(self):
        self.assertInvalid(config(b2={'next_block_id': True}), 'next_block_id must be null')

    def test_positions_must_be_numbers(self):
        for bad in ('100', None, True):
            with self.subTest(position=bad):
                self.assertInvalid(config(b0={'position_x': bad}), 'position_x must be a number')

    def test_reports_all_errors(self):
        with self.assertRaises(ValidationError) as ctx:
            validate_chat_config(config(b1={'block_type': 'X', 'position_y': 'y'}, b2={'id': 1}))
        self.assertEqual(len(ctx.exception.messages), 4)  # block_type, position_y, duplicate id, dangling next id


DETAIL_FIELDS = [
    {'key': 'name', 'label': 'Receiver name', 'type': 'text', 'max_length': 150},
    {'key': 'postal_code', 'label': 'Postal code', 'type': 'number', 'min_value': 100000, 'max_value': 999999},
    {'key': 'notes', 'label': 'Customisation notes', 'type': 'text', 'max_length': 200, 'description': 'e.g. less sugar'},
    {'key': 'email', 'label': 'Email', 'type': 'email'},
    {'key': 'phone', 'label': 'Phone', 'type': 'phone', 'description': 'For delivery updates'},
]


def details_config(fields):
    """VALID_CONFIG with a DETAILS_COLLECTION_BLOCK (id 4, between product selection and confirmation)."""
    blocks = config(b1={'next_block_id': 4})
    blocks.append({
        'id': 4, 'next_block_id': 3, 'block_type': 'DETAILS_COLLECTION_BLOCK',
        'position_x': 0, 'position_y': 0, 'fields': fields,
    })
    return blocks


class ValidateDetailFieldsTests(SimpleTestCase):
    """The optional `fields` of a DETAILS_COLLECTION_BLOCK (validate_chat_config)."""

    def errors(self, value) -> list[str]:
        try:
            validate_chat_config(value)
        except ValidationError as exc:
            return exc.messages
        return []

    def assertInvalid(self, fields, message_part):
        messages = self.errors(details_config(fields))
        self.assertTrue(any(message_part in m for m in messages), f'{message_part!r} not in {messages}')

    def test_valid_fields(self):
        validate_chat_config(details_config(DETAIL_FIELDS))
        validate_chat_config(details_config([{'key': 'a', 'label': 'A', 'type': 'number'}]))  # no bounds
        validate_chat_config(details_config([  # optional fields, on every type, next to a required one
            {'key': 'name', 'label': 'Name', 'type': 'text', 'required': True},
            {'key': 'notes', 'label': 'Notes', 'type': 'text', 'required': False},
            {'key': 'n', 'label': 'N', 'type': 'number', 'required': False},
            {'key': 'e', 'label': 'E', 'type': 'email', 'required': False},
            {'key': 'p', 'label': 'P', 'type': 'phone', 'required': False},
        ]))
        validate_chat_config(details_config([{'key': 'x', 'label': 'X', 'type': 'number', 'min_value': 1.5, 'max_value': 1.5}]))

    def test_fields_are_optional(self):
        blocks = details_config(DETAIL_FIELDS)
        del blocks[-1]['fields']
        validate_chat_config(blocks)
        self.assertEqual([f['key'] for f in block_detail_fields(blocks[-1])], ['name', 'email'])  # the defaults
        self.assertEqual(block_detail_fields(details_config(DETAIL_FIELDS)[-1]), DETAIL_FIELDS)

    def test_fields_only_on_details_blocks(self):
        blocks = config(b1={'fields': DETAIL_FIELDS})
        self.assertIn('Block 1: fields is only allowed on a DETAILS_COLLECTION_BLOCK.', self.errors(blocks))

    def test_invalid_fields(self):
        field = {'key': 'notes', 'label': 'Notes', 'type': 'text'}
        cases = {
            'not a list': ({'key': 'a'}, 'fields must be a list'),
            'empty': ([], 'fields must have between 1 and 20 items'),
            'too many': ([{**field, 'key': f'f{i}'} for i in range(21)], 'fields must have between 1 and 20 items'),
            'field not an object': (['notes'], 'field 0: must be an object'),
            'missing keys': ([{'key': 'notes'}], 'field 0: missing label, type'),
            'uppercase key': ([{**field, 'key': 'Notes'}], 'key must be lowercase letters'),
            'key with space': ([{**field, 'key': 'postal code'}], 'key must be lowercase letters'),
            'key starting with digit': ([{**field, 'key': '1st'}], 'key must be lowercase letters'),
            'key too long': ([{**field, 'key': 'k' * 41}], 'max 40 characters'),
            'duplicate key': ([field, {**field, 'label': 'Other'}], "field 1: duplicate key 'notes'"),
            'blank label': ([{**field, 'label': '  '}], 'label must be a non-blank string'),
            'label too long': ([{**field, 'label': 'x' * 101}], 'at most 100 characters'),
            'unknown type': ([{**field, 'type': 'date'}], 'type must be one of text, number, email, phone'),
            'max_length on number': ([{**field, 'type': 'number', 'max_length': 5}], 'max_length not allowed for type number'),
            'min_value on text': ([{**field, 'min_value': 1}], 'min_value not allowed for type text'),
            'max_length on email': ([{**field, 'type': 'email', 'max_length': 5}], 'max_length not allowed for type email'),
            'unknown key': ([{**field, 'placeholder': 'x'}], 'placeholder not allowed for type text'),
            'required not a bool': ([{**field, 'required': 'yes'}], 'required must be true or false'),
            'all optional': ([{**field, 'required': False}], 'at least one field must be required'),
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

    def test_every_field_error_is_listed(self):
        messages = self.errors(details_config([
            {'key': 'Bad', 'label': '', 'type': 'text'},
            {'key': 'ok', 'label': 'OK', 'type': 'number', 'min_value': 5, 'max_value': 1},
        ]))
        self.assertEqual(len(messages), 3, messages)


def send_message_config(**block_changes):
    """VALID_CONFIG with a SEND_MESSAGE_BLOCK (id 5) between product selection and confirmation."""
    blocks = config(b1={'next_block_id': 5})
    blocks.append({
        'id': 5, 'next_block_id': 3, 'block_type': 'SEND_MESSAGE_BLOCK', 'position_x': 0, 'position_y': 0,
        'message': 'Great choice! Just a few more questions.', **block_changes,
    })
    return blocks


class ValidateSendMessageBlockTests(SimpleTestCase):
    """A SEND_MESSAGE_BLOCK's required `message` (validate_chat_config)."""

    def assertInvalid(self, value, message_part):
        with self.assertRaises(ValidationError) as ctx:
            validate_chat_config(value)
        self.assertTrue(
            any(message_part in message for message in ctx.exception.messages),
            f'{message_part!r} not in {ctx.exception.messages}',
        )

    def test_valid(self):
        validate_chat_config(send_message_config())
        validate_chat_config(send_message_config(message='x' * CHAT_MESSAGE_MAX_LENGTH))
        validate_chat_config(send_message_config(message='Line 1\nLine 2 🎉'))

    def test_invalid_message(self):
        blocks = send_message_config()
        del blocks[-1]['message']
        cases = {
            'missing': (blocks, 'Block 3: a SEND_MESSAGE_BLOCK needs a non-blank message.'),
            'empty': (send_message_config(message=''), 'needs a non-blank message'),
            'blank': (send_message_config(message='  \n '), 'needs a non-blank message'),
            'not a string': (send_message_config(message=['hi']), 'needs a non-blank message'),
            'null': (send_message_config(message=None), 'needs a non-blank message'),
            'too long': (send_message_config(message='x' * (CHAT_MESSAGE_MAX_LENGTH + 1)), 'message must be at most 4096 characters'),
        }
        for label, (value, message_part) in cases.items():
            with self.subTest(label):
                self.assertInvalid(value, message_part)

    def test_message_only_on_send_message_blocks(self):
        self.assertInvalid(config(b1={'message': 'Hi'}), 'Block 1: message is only allowed on a SEND_MESSAGE_BLOCK.')

    def test_send_message_block_can_be_last_and_repeat(self):
        blocks = send_message_config()
        blocks[2]['next_block_id'] = 6
        blocks.append({'id': 6, 'next_block_id': None, 'block_type': 'SEND_MESSAGE_BLOCK',
                       'position_x': 0, 'position_y': 0, 'message': 'Thank you!'})
        validate_chat_config(blocks)


class ChatConfigurationModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.business = BusinessConfiguration.objects.create(business_name='Test Café', location='Singapore')

    def test_valid_configuration(self):
        chat_config = ChatConfiguration(business=self.business, config_json=VALID_CONFIG)
        chat_config.full_clean()
        chat_config.save()
        self.assertEqual(self.business.chat_configuration, chat_config)
        self.assertIsNotNone(chat_config.last_updated)

    def test_invalid_config_json_rejected_by_full_clean(self):
        with self.assertRaises(ValidationError) as ctx:
            ChatConfiguration(business=self.business, config_json=config(b2={'id': 1})).full_clean()
        self.assertIn('config_json', ctx.exception.message_dict)

    def test_last_updated_changes_on_save(self):
        chat_config = ChatConfiguration.objects.create(business=self.business, config_json=VALID_CONFIG)
        first = chat_config.last_updated
        chat_config.config_json = config(b0={'position_x': 150})
        chat_config.save()
        self.assertGreater(chat_config.last_updated, first)

    def test_one_configuration_per_business(self):
        ChatConfiguration.objects.create(business=self.business, config_json=VALID_CONFIG)
        with self.assertRaises(IntegrityError), transaction.atomic():
            ChatConfiguration.objects.create(business=self.business, config_json=VALID_CONFIG)

    def test_deleted_with_business(self):
        ChatConfiguration.objects.create(business=self.business, config_json=VALID_CONFIG)
        self.business.delete()
        self.assertFalse(ChatConfiguration.objects.exists())

    def test_get_block_matches_id_and_type(self):
        blocks = config(b1={'next_block_id': 'x'}, b2={'id': 'x'})
        chat_config = ChatConfiguration(business=self.business, config_json=blocks)
        self.assertEqual(chat_config.get_block(1)['block_type'], 'START_BLOCK')
        self.assertEqual(chat_config.get_block('x')['block_type'], 'CONFIRMATION_BLOCK')
        self.assertIsNone(chat_config.get_block('1'))  # "1" is not block 1
        self.assertIsNone(chat_config.get_block(None))
        self.assertIsNone(chat_config.get_block(99))
        self.assertEqual(chat_config.start_block['id'], 1)


class SampleChatConfigurationFixtureTests(TestCase):
    fixtures = ['sample_business_configurations', 'sample_chat_configurations']

    def test_fixture_is_valid(self):
        chat_config = ChatConfiguration.objects.get(business_id=1)
        chat_config.full_clean()  # loaddata skips validation
        self.assertEqual(
            [block['block_type'] for block in chat_config.config_json],
            ['START_BLOCK', 'PRODUCT_SELECTION_BLOCK', 'DETAILS_COLLECTION_BLOCK', 'CONFIRMATION_BLOCK'],
        )
        details = chat_config.config_json[2]
        self.assertEqual([f['key'] for f in details['fields']], ['name', 'email', 'pickup_time'])

    def test_florist_fixture_is_valid(self):
        chat_config = ChatConfiguration.objects.get(business_id=2)
        chat_config.full_clean()
        self.assertEqual(
            [block['block_type'] for block in chat_config.config_json],
            ['START_BLOCK', 'PRODUCT_SELECTION_BLOCK', 'DETAILS_COLLECTION_BLOCK', 'CONFIRMATION_BLOCK'],
        )
        details = chat_config.config_json[2]
        self.assertEqual([f['key'] for f in details['fields']], ['name', 'card_message', 'collection_date'])
        self.assertTrue(all(is_required_detail(f) for f in details['fields']))


# --- ChatSession ----------------------------------------------------------------------------

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


class ValidateChatMessagesTests(SimpleTestCase):
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


class ChatSessionModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.business = BusinessConfiguration.objects.create(business_name='Test Café', location='Singapore')
        cls.other_business = BusinessConfiguration.objects.create(business_name='Other', location='Singapore')
        ChatConfiguration.objects.create(business=cls.business, config_json=VALID_CONFIG)

    def make_session(self, **overrides):
        fields = {
            'business': self.business,
            'phone_number': '+6591234567',
            'display_name': 'Alice',
            'chat_message_json': VALID_MESSAGES,
            'chat_state_id': 2,
        }
        return ChatSession(**{**fields, **overrides})

    def assertFieldInvalid(self, session, field):
        with self.assertRaises(ValidationError) as ctx:
            session.full_clean()
        self.assertIn(field, ctx.exception.message_dict)

    def test_valid_session(self):
        session = self.make_session()
        session.full_clean()
        session.save()
        self.assertIsNotNone(session.created_time)
        self.assertIsNotNone(session.last_chat_time)
        self.assertEqual(list(self.business.chat_sessions.all()), [session])

    def test_defaults(self):
        session = ChatSession(business=self.business, phone_number='+6591234567')
        session.full_clean()  # no name, no messages, no state
        self.assertEqual(session.chat_message_json, [])
        self.assertIsNone(session.chat_state_id)

    def test_phone_number_format(self):
        for good in ('+6591234567', '+14155552671', '+441234567890'):
            with self.subTest(phone_number=good):
                self.make_session(phone_number=good).full_clean()
        for bad in ('', '91234567', '+65 9123 4567', '+0123456789', '+65-91234567', '+1234567890123456'):
            with self.subTest(phone_number=bad):
                self.assertFieldInvalid(self.make_session(phone_number=bad), 'phone_number')

    def test_invalid_messages_rejected(self):
        self.assertFieldInvalid(self.make_session(chat_message_json=messages(m0={'sent_by': 'bot'})), 'chat_message_json')

    def test_chat_state_id_must_be_a_block_of_the_business(self):
        for block_id in (1, 2, 3):
            with self.subTest(chat_state_id=block_id):
                self.make_session(chat_state_id=block_id).full_clean()
        for bad in (99, '2', True, 2.0, '', [2]):
            with self.subTest(chat_state_id=bad):
                self.assertFieldInvalid(self.make_session(chat_state_id=bad), 'chat_state_id')

    def test_chat_state_id_with_string_block_ids(self):
        chat_config = self.business.chat_configuration
        chat_config.config_json = config(b0={'id': 'start', 'next_block_id': 2})
        chat_config.save()
        self.make_session(chat_state_id='start').full_clean()
        self.assertFieldInvalid(self.make_session(chat_state_id=1), 'chat_state_id')

    def test_chat_state_id_must_be_null_without_configuration(self):
        self.make_session(business=self.other_business, chat_state_id=None).full_clean()
        self.assertFieldInvalid(self.make_session(business=self.other_business, chat_state_id=1), 'chat_state_id')

    def test_phone_number_unique_per_business(self):
        self.make_session().save()
        self.assertFieldInvalid(self.make_session(), '__all__')
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.make_session().save()

    def test_same_phone_number_in_another_business(self):
        self.make_session().save()
        other = self.make_session(business=self.other_business, chat_state_id=None)
        other.full_clean()
        other.save()

    def test_sandbox_session_needs_no_phone_number(self):
        session = self.make_session(phone_number='', is_sandbox=True)
        session.full_clean()
        session.save()
        self.assertIn('Sandbox chat', str(ChatSession(business=self.business, is_sandbox=True)))

    def test_real_session_needs_phone_number(self):
        self.assertFieldInvalid(self.make_session(phone_number=''), 'phone_number')

    def test_sandbox_phone_number_still_validated(self):
        self.assertFieldInvalid(self.make_session(phone_number='000', is_sandbox=True), 'phone_number')

    def test_sandbox_sessions_can_share_phone_numbers(self):
        self.make_session().save()  # real session with +6591234567
        for _ in range(2):
            sandbox = self.make_session(is_sandbox=True)
            sandbox.full_clean()
            sandbox.save()
        for _ in range(2):
            self.make_session(phone_number='', is_sandbox=True).save()
        self.assertEqual(ChatSession.objects.filter(is_sandbox=True).count(), 4)

    def test_sandbox_session_chat_state_id_still_checked(self):
        self.assertFieldInvalid(self.make_session(is_sandbox=True, chat_state_id=99), 'chat_state_id')

    def test_empty_phone_number_rejected_by_database(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.make_session(phone_number='').save()

    def test_deleted_with_business(self):
        self.make_session().save()
        self.business.delete()
        self.assertFalse(ChatSession.objects.exists())


VALID_STATE_DATA = {
    'items': [{'product_id': 1, 'name': 'Kopi C', 'unit_price': '1.80', 'quantity': 2}],
    'details': {'name': 'Alice', 'email': 'alice@example.com'},
    'items_confirmed': True,
    'completed': False,
}


class ValidateChatStateDataTests(SimpleTestCase):
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
            'completed not bool': ({'completed': 'yes'}, 'completed must be true or false'),
            'items_confirmed not bool': ({'items_confirmed': 1}, 'items_confirmed must be true or false'),
        }
        for label, (value, message_part) in cases.items():
            with self.subTest(label):
                self.assertInvalid(value, message_part)

    def test_rejected_by_model_full_clean(self):
        session = ChatSession(business_id=1, phone_number='+6591234567', chat_state_data={'completed': 'yes'})
        with self.assertRaises(ValidationError) as ctx:
            session.clean_fields(exclude=['business'])
        self.assertIn('chat_state_data', ctx.exception.message_dict)


class SampleChatSessionFixtureTests(TestCase):
    fixtures = ['sample_business_configurations', 'sample_chat_configurations', 'sample_chat_sessions']

    def test_fixture_is_valid(self):
        sessions = ChatSession.objects.all()
        self.assertEqual(sessions.count(), 16)
        self.assertEqual(sessions.filter(is_sandbox=True).count(), 2)
        for session in sessions:
            with self.subTest(session=session.pk):
                session.full_clean()  # loaddata skips validation, including chat_state_id
                if session.chat_message_json:
                    self.assertEqual(session.last_chat_time.isoformat(), _utc(session.chat_message_json[-1]['message_time']))
                else:  # no messages yet: last chat time is when it was created
                    self.assertEqual(session.last_chat_time, session.created_time)


def _utc(iso_string: str) -> str:
    from datetime import datetime, timezone
    return datetime.fromisoformat(iso_string).astimezone(timezone.utc).isoformat()
