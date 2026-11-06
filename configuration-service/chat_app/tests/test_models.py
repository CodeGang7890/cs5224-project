import copy

from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import SimpleTestCase, TestCase, TransactionTestCase
from django.utils import timezone

from configuration_app.models import BusinessConfiguration

from ..constants import CHAT_STEPS, DEFAULT_DETAIL_FIELDS, MESSAGE_SENDERS
from ..models import ChatConfiguration, ChatSession, InboundMessage, InboundMessageStatus
from ..validators import (
    CHAT_MESSAGE_MAX_LENGTH,
    is_required_detail,
    validate_chat_messages,
    validate_chat_state_data,
    validate_detail_fields,
)

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


class ChatStepsTests(SimpleTestCase):
    def test_steps_constant(self):
        self.assertEqual(CHAT_STEPS, [
            'start', 'product_selection', 'details_collection', 'confirmation',
            'service_selection', 'slot_selection', 'booking_details', 'booking_confirmation',
        ])


class ValidateDetailFieldsTests(SimpleTestCase):
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

    def test_every_field_error_is_listed(self):
        messages = self.errors([
            {'key': 'Bad', 'label': '', 'type': 'text'},
            {'key': 'ok', 'label': 'OK', 'type': 'number', 'min_value': 5, 'max_value': 1},
        ])
        self.assertEqual(len(messages), 3, messages)


class ChatConfigurationModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.business = BusinessConfiguration.objects.create(business_name='Test Café', location='Singapore')

    def test_no_phone_type(self):
        # Customers chat on WhatsApp: the chat already has their number.
        with self.assertRaises(ValidationError) as ctx:
            validate_detail_fields([{'key': 'name', 'label': 'Name', 'type': 'text'}, {'key': 'phone', 'label': 'Phone', 'type': 'phone'}])
        self.assertIn('type must be one of text, number, email', ctx.exception.messages[0])

    def test_valid_configuration(self):
        chat_config = ChatConfiguration(business=self.business, product_detail_fields=DETAIL_FIELDS, schedule_detail_fields=BOOKING_FIELDS)
        chat_config.full_clean()
        chat_config.save()
        self.assertEqual(self.business.chat_configuration, chat_config)
        self.assertIsNotNone(chat_config.last_updated)

    def test_default_detail_fields(self):
        # Both lists default to a required name and email, each its own copy.
        chat_config = ChatConfiguration.objects.create(business=self.business)
        self.assertEqual(chat_config.product_detail_fields, DEFAULT_DETAIL_FIELDS)
        self.assertEqual(chat_config.schedule_detail_fields, DEFAULT_DETAIL_FIELDS)
        self.assertEqual([f['key'] for f in DEFAULT_DETAIL_FIELDS], ['name', 'email'])
        self.assertTrue(all(is_required_detail(f) for f in DEFAULT_DETAIL_FIELDS))
        chat_config.product_detail_fields[0]['label'] = 'Changed'
        self.assertEqual(chat_config.schedule_detail_fields[0]['label'], 'Name')
        self.assertEqual(ChatConfiguration(business=self.business).product_detail_fields[0]['label'], 'Name')

    def test_the_two_lists_are_independent(self):
        chat_config = ChatConfiguration.objects.create(
            business=self.business, product_detail_fields=DETAIL_FIELDS, schedule_detail_fields=BOOKING_FIELDS
        )
        chat_config.refresh_from_db()
        self.assertEqual((chat_config.product_detail_fields, chat_config.schedule_detail_fields), (DETAIL_FIELDS, BOOKING_FIELDS))
        # The order steps (and Start) ask for the product details, the booking steps for the schedule ones.
        for step in ('start', 'product_selection', 'details_collection', 'confirmation'):
            self.assertEqual(chat_config.detail_fields_for(step), DETAIL_FIELDS, step)
        for step in ('service_selection', 'slot_selection', 'booking_details', 'booking_confirmation'):
            self.assertEqual(chat_config.detail_fields_for(step), BOOKING_FIELDS, step)

    def test_invalid_detail_fields_rejected_by_full_clean(self):
        for field in ('product_detail_fields', 'schedule_detail_fields'):
            with self.subTest(field=field), self.assertRaises(ValidationError) as ctx:
                ChatConfiguration(business=self.business, **{field: []}).full_clean()
            self.assertIn(field, ctx.exception.message_dict)

    def test_last_updated_changes_on_save(self):
        chat_config = ChatConfiguration.objects.create(business=self.business)
        first = chat_config.last_updated
        chat_config.product_detail_fields = DETAIL_FIELDS
        chat_config.save()
        self.assertGreater(chat_config.last_updated, first)

    def test_one_configuration_per_business(self):
        ChatConfiguration.objects.create(business=self.business)
        with self.assertRaises(IntegrityError), transaction.atomic():
            ChatConfiguration.objects.create(business=self.business)

    def test_deleted_with_business(self):
        ChatConfiguration.objects.create(business=self.business)
        self.business.delete()
        self.assertFalse(ChatConfiguration.objects.exists())

    def test_for_business_returns_the_saved_one_or_the_defaults(self):
        unsaved = ChatConfiguration.for_business(self.business)
        self.assertIsNone(unsaved.pk)
        self.assertEqual((unsaved.business, unsaved.product_detail_fields), (self.business, DEFAULT_DETAIL_FIELDS))
        self.assertEqual(unsaved.schedule_detail_fields, DEFAULT_DETAIL_FIELDS)
        self.assertFalse(ChatConfiguration.objects.exists())  # nothing saved
        saved = ChatConfiguration.objects.create(business=self.business, product_detail_fields=DETAIL_FIELDS)
        self.assertEqual(ChatConfiguration.for_business(self.business), saved)
        self.assertEqual(ChatConfiguration.for_business(self.business).product_detail_fields, DETAIL_FIELDS)


class SampleChatConfigurationFixtureTests(TestCase):
    fixtures = ['sample_business_configurations', 'sample_chat_configurations']

    def test_fixture_is_valid(self):
        chat_config = ChatConfiguration.objects.get(business_id=1)
        chat_config.full_clean()  # loaddata skips validation
        self.assertEqual([f['key'] for f in chat_config.product_detail_fields], ['name', 'email', 'pickup_time'])
        self.assertEqual(chat_config.schedule_detail_fields, DEFAULT_DETAIL_FIELDS)

    def test_florist_fixture_is_valid(self):
        chat_config = ChatConfiguration.objects.get(business_id=2)
        chat_config.full_clean()
        self.assertEqual([f['key'] for f in chat_config.product_detail_fields], ['name', 'card_message', 'collection_date'])
        self.assertTrue(all(is_required_detail(f) for f in chat_config.product_detail_fields))

    def test_photography_fixture_collects_its_own_booking_details(self):
        chat_config = ChatConfiguration.objects.get(business_id=4)
        chat_config.full_clean()
        # Prints and frames are delivered: the orders ask for the photos and an address.
        self.assertEqual([f['key'] for f in chat_config.product_detail_fields], ['name', 'email', 'photos', 'delivery_address'])
        self.assertEqual([f['key'] for f in chat_config.schedule_detail_fields], ['name', 'people', 'notes'])

    def test_court_fixture(self):
        chat_config = ChatConfiguration.objects.get(business_id=5)
        chat_config.full_clean()
        self.assertEqual([f['key'] for f in chat_config.schedule_detail_fields], ['name', 'email', 'players'])
        self.assertEqual((chat_config.reply_style, chat_config.welcome_message[:28]), ('casual', 'Hi, welcome to {business_nam'))

    def test_no_fixture_asks_for_a_phone_number(self):
        for chat_config in ChatConfiguration.objects.all():
            for field in chat_config.product_detail_fields + chat_config.schedule_detail_fields:
                self.assertNotEqual(field['type'], 'phone')
                self.assertNotIn('phone', field['key'])



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

    def make_session(self, **overrides):
        fields = {
            'business': self.business,
            'phone_number': '+6591234567',
            'display_name': 'Alice',
            'chat_message_json': VALID_MESSAGES,
            'chat_state_id': 'product_selection',
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
        self.assertEqual(session.chat_state_id, 'start')
        self.assertEqual(session.chat_state_data, {})

    def test_phone_number_format(self):
        for good in ('+6591234567', '+14155552671', '+441234567890'):
            with self.subTest(phone_number=good):
                self.make_session(phone_number=good).full_clean()
        for bad in ('', '91234567', '+65 9123 4567', '+0123456789', '+65-91234567', '+1234567890123456'):
            with self.subTest(phone_number=bad):
                self.assertFieldInvalid(self.make_session(phone_number=bad), 'phone_number')

    def test_invalid_messages_rejected(self):
        self.assertFieldInvalid(self.make_session(chat_message_json=messages(m0={'sent_by': 'bot'})), 'chat_message_json')

    def test_chat_state_id_must_be_a_step(self):
        for step in CHAT_STEPS:  # with or without a saved configuration: the steps are fixed
            with self.subTest(chat_state_id=step):
                self.make_session(chat_state_id=step).full_clean()
                self.make_session(business=self.other_business, chat_state_id=step).full_clean()
        for bad in ('done', 'START', '', '2', None):
            with self.subTest(chat_state_id=bad):
                self.assertFieldInvalid(self.make_session(chat_state_id=bad), 'chat_state_id')

    def test_invalid_step_rejected_by_database(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.make_session(chat_state_id='done').save()

    def test_phone_number_unique_per_business(self):
        self.make_session().save()
        self.assertFieldInvalid(self.make_session(), '__all__')
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.make_session().save()

    def test_same_phone_number_in_another_business(self):
        self.make_session().save()
        other = self.make_session(business=self.other_business)
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
        self.assertFieldInvalid(self.make_session(is_sandbox=True, chat_state_id='done'), 'chat_state_id')

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
    'last_order_id': 3,
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
            'old completed flag': ({'completed': True}, 'Unknown field(s) completed'),
            'last_order_id zero': ({'last_order_id': 0}, 'last_order_id must be a positive integer'),
            'last_order_id text': ({'last_order_id': '3'}, 'last_order_id must be a positive integer'),
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
        self.assertEqual(sessions.count(), 31)  # 1–32 but 6 (21–32: Rally Point Courts)
        self.assertEqual(sessions.filter(is_sandbox=True).count(), 2)
        self.assertEqual(sessions.get(pk=1).chat_state_id, 'confirmation')
        # 20: Lumen & Lens, a booking made in the chat (checkout_app sample_schedule_items pk 1).
        self.assertEqual((sessions.get(pk=20).chat_state_id, sessions.get(pk=20).chat_state_data), ('start', {'last_booking_id': 1}))
        for session in sessions:
            with self.subTest(session=session.pk):
                session.full_clean()  # loaddata skips validation
                if session.chat_message_json:
                    self.assertEqual(session.last_chat_time.isoformat(), _utc(session.chat_message_json[-1]['message_time']))
                else:  # no messages yet: last chat time is when it was created
                    self.assertEqual(session.last_chat_time, session.created_time)


def _utc(iso_string: str) -> str:
    from datetime import datetime, timezone
    return datetime.fromisoformat(iso_string).astimezone(timezone.utc).isoformat()


class LastOrderIdMigrationTests(TestCase):
    """Migration 0008: chats whose order was placed go back to the start, keeping last_order_id."""

    def test_converts_old_state(self):
        from importlib import import_module

        from django.apps import apps

        migration = import_module('chat_app.migrations.0008_chat_state_last_order_id')
        business = BusinessConfiguration.objects.create(business_name='B', location='SG')
        items = [{'product_id': 1, 'name': 'Kopi C', 'unit_price': '1.80', 'quantity': 1}]
        done = ChatSession.objects.create(business=business, is_sandbox=True, chat_state_id='confirmation')
        open_order = ChatSession.objects.create(business=business, is_sandbox=True, chat_state_id='product_selection')
        untouched = ChatSession.objects.create(business=business, is_sandbox=True, chat_state_data={'items': items})
        # Written with update(), as the old keys no longer pass validation.
        ChatSession.objects.filter(pk=done.pk).update(chat_state_data={'items': items, 'completed': True, 'order_id': 7})
        ChatSession.objects.filter(pk=open_order.pk).update(chat_state_data={'items': items, 'completed': False})

        migration.to_last_order_id(apps, None)
        for session in (done, open_order, untouched):
            session.refresh_from_db()
            session.full_clean()
        self.assertEqual((done.chat_state_id, done.chat_state_data), ('start', {'last_order_id': 7}))
        self.assertEqual((open_order.chat_state_id, open_order.chat_state_data), ('product_selection', {'items': items}))
        self.assertEqual(untouched.chat_state_data, {'items': items})

        migration.to_completed(apps, None)  # backwards
        done.refresh_from_db()
        self.assertEqual((done.chat_state_id, done.chat_state_data), ('confirmation', {'completed': True, 'order_id': 7}))


class DetailFieldsSplitMigrationTests(TransactionTestCase):
    """chat_app 0011: the one detail fields list becomes the product and the schedule lists, both
    without phone fields (customers chat on WhatsApp)."""

    before = [('chat_app', '0010_chat_configuration_welcome_and_style')]
    after = [('chat_app', '0011_product_and_schedule_detail_fields')]

    def migrate(self, targets):
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(targets)
        return executor.loader.project_state(targets).apps

    def tearDown(self):
        self.migrate(MigrationExecutor(connection).loader.graph.leaf_nodes())

    def test_split_without_phone_fields(self):
        apps = self.migrate(self.before)
        Business = apps.get_model('configuration_app', 'BusinessConfiguration')
        OldConfig = apps.get_model('chat_app', 'ChatConfiguration')
        studio = Business.objects.create(business_name='Snap', location='SG')
        cafe = Business.objects.create(business_name='Cafe', location='SG')
        fields = [
            {'key': 'name', 'label': 'Name', 'type': 'text'},
            {'key': 'phone', 'label': 'Phone', 'type': 'phone'},
            {'key': 'people', 'label': 'People', 'type': 'number'},
        ]
        OldConfig.objects.create(business=studio, detail_fields=fields)
        # Only a phone left required: back to the defaults.
        OldConfig.objects.create(business=cafe, detail_fields=[
            {'key': 'mobile', 'label': 'Mobile', 'type': 'phone'},
            {'key': 'notes', 'label': 'Notes', 'type': 'text', 'required': False},
        ])

        apps = self.migrate(self.after)
        Config = apps.get_model('chat_app', 'ChatConfiguration')
        studio_config = Config.objects.get(business_id=studio.pk)
        expected = [fields[0], fields[2]]
        self.assertEqual((studio_config.product_detail_fields, studio_config.schedule_detail_fields), (expected, expected))
        cafe_config = Config.objects.get(business_id=cafe.pk)
        self.assertEqual(cafe_config.product_detail_fields, DEFAULT_DETAIL_FIELDS)
        self.assertEqual(cafe_config.schedule_detail_fields, DEFAULT_DETAIL_FIELDS)


class InboundMessageModelTests(TestCase):
    """A WhatsApp message messaging-service took from Pub/Sub: one row per Meta message id."""

    @classmethod
    def setUpTestData(cls):
        cls.business = BusinessConfiguration.objects.create(business_name='Café', location='Singapore')
        cls.session = ChatSession.objects.create(business=cls.business, phone_number='+6591234567')

    def test_defaults_and_one_row_per_message_id(self):
        item = InboundMessage.objects.create(business=self.business, chat_session=self.session, message_id='wamid.1')
        self.assertEqual((item.status, item.replied_time), (InboundMessageStatus.RECEIVED, None))
        with self.assertRaises(IntegrityError), transaction.atomic():
            InboundMessage.objects.create(business=self.business, chat_session=self.session, message_id='wamid.1')

    def test_replied_time_set_exactly_when_replied(self):
        for status, replied_time in (('replied', None), ('received', timezone.now()), ('sent', None)):
            with self.subTest(status=status), self.assertRaises(IntegrityError), transaction.atomic():
                InboundMessage.objects.create(
                    business=self.business, chat_session=self.session, message_id=f'wamid.{status}',
                    status=status, replied_time=replied_time,
                )
