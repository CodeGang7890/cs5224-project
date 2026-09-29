import copy
import json
import uuid

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import SimpleTestCase, TestCase

from configuration_app.models import BusinessConfiguration

from .constants import BLOCK_TYPES, MESSAGE_SENDERS
from .models import ChatConfiguration, ChatSession
from .validators import CHAT_MESSAGE_MAX_LENGTH, validate_chat_config, validate_chat_messages

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
            ['START_BLOCK', 'PRODUCT_SELECTION_BLOCK', 'DETAILS_COLLECTION_BLOCK', 'CONFIRMATION_BLOCK'],
        )

    def test_every_block_type_accepted(self):
        blocks = [
            {'id': str(i), 'next_block_id': None, 'block_type': t, 'position_x': 0, 'position_y': 0}
            for i, t in enumerate(BLOCK_TYPES)
        ]
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


class SampleChatConfigurationFixtureTests(TestCase):
    fixtures = ['sample_business_configurations', 'sample_chat_configurations']

    def test_fixture_is_valid(self):
        chat_config = ChatConfiguration.objects.get(business_id=1)
        chat_config.full_clean()  # loaddata skips validation
        self.assertEqual(
            [block['block_type'] for block in chat_config.config_json],
            ['START_BLOCK', 'PRODUCT_SELECTION_BLOCK', 'DETAILS_COLLECTION_BLOCK', 'CONFIRMATION_BLOCK'],
        )


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

    def test_empty_phone_number_rejected_by_database(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.make_session(phone_number='').save()

    def test_deleted_with_business(self):
        self.make_session().save()
        self.business.delete()
        self.assertFalse(ChatSession.objects.exists())


class SampleChatSessionFixtureTests(TestCase):
    fixtures = ['sample_business_configurations', 'sample_chat_configurations', 'sample_chat_sessions']

    def test_fixture_is_valid(self):
        sessions = ChatSession.objects.all()
        self.assertEqual(sessions.count(), 6)
        for session in sessions:
            with self.subTest(session=session.pk):
                session.full_clean()  # loaddata skips validation, including chat_state_id
                self.assertEqual(session.last_chat_time.isoformat(), _utc(session.chat_message_json[-1]['message_time']))


def _utc(iso_string: str) -> str:
    from datetime import datetime, timezone
    return datetime.fromisoformat(iso_string).astimezone(timezone.utc).isoformat()
