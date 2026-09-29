import copy
import uuid

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import SimpleTestCase, TestCase

from configuration_app.models import BusinessConfiguration

from .constants import BLOCK_TYPES
from .models import ChatConfiguration
from .validators import validate_chat_config

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
        self.assertInvalid({'id': 1}, 'must be a list')

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
