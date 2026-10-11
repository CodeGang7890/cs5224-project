import unittest

from app.parsing import InboundMessage, parse_webhook, to_e164, to_iso_timestamp

from .helpers import BUSINESS_ID, PHONE_NUMBER_ID, change, text_message, webhook


def parse(payload):
    return parse_webhook(payload, BUSINESS_ID, PHONE_NUMBER_ID)


class ParseWebhookTests(unittest.TestCase):
    def test_text_message(self):
        result = parse(webhook(change([text_message()])))
        self.assertEqual(result.skipped, 0)
        self.assertEqual(
            result.messages,
            [
                InboundMessage(
                    business_id=BUSINESS_ID,
                    phone_number_id=PHONE_NUMBER_ID,
                    message_id='wamid.1',
                    from_number='+6591234567',
                    display_name='Alice',
                    type='text',
                    text='Hi, do you have cakes?',
                    timestamp='2023-11-14T22:13:20+00:00',
                )
            ],
        )

    def test_contract_json(self):
        message = parse(webhook(change([text_message()]))).messages[0]
        self.assertEqual(
            message.to_dict(),
            {
                'business_id': BUSINESS_ID,
                'phone_number_id': PHONE_NUMBER_ID,
                'message_id': 'wamid.1',
                'from': '+6591234567',
                'display_name': 'Alice',
                'type': 'text',
                'text': 'Hi, do you have cakes?',
                'timestamp': '2023-11-14T22:13:20+00:00',
            },
        )

    def test_non_text_messages_have_no_text(self):
        image = {'from': '6591234567', 'id': 'wamid.2', 'timestamp': '1700000000', 'type': 'image',
                 'image': {'id': 'media-1', 'mime_type': 'image/jpeg', 'caption': 'my cake'}}
        message = parse(webhook(change([image]))).messages[0]
        self.assertEqual(message.type, 'image')
        self.assertIsNone(message.text)

    def test_several_messages_entries_and_changes_keep_their_order(self):
        payload = webhook(
            change([text_message('wamid.1', body='one'), text_message('wamid.2', body='two')]),
            change([text_message('wamid.3', sender='6598765432', body='three')]),
        )
        payload['entry'].append({'id': 'x', 'changes': [change([text_message('wamid.4', body='four')])]})
        result = parse(payload)
        self.assertEqual([m.message_id for m in result.messages], ['wamid.1', 'wamid.2', 'wamid.3', 'wamid.4'])
        self.assertEqual([m.text for m in result.messages], ['one', 'two', 'three', 'four'])
        self.assertEqual(result.messages[2].from_number, '+6598765432')

    def test_statuses_only_publishes_nothing(self):
        statuses = [{'id': 'wamid.out', 'status': 'delivered', 'timestamp': '1700000000', 'recipient_id': '6591234567'}]
        result = parse(webhook(change(statuses=statuses)))
        self.assertEqual(result.messages, [])
        self.assertEqual(result.skipped, 0)

    def test_other_fields_are_ignored(self):
        result = parse(webhook(change([text_message()], field='account_update')))
        self.assertEqual((result.messages, result.skipped), ([], 0))

    def test_messages_for_another_phone_number_are_skipped(self):
        payload = webhook(
            change([text_message('wamid.1')], phone_number_id='999'),
            change([text_message('wamid.2')]),
        )
        with self.assertLogs('app.parsing', 'WARNING'):
            result = parse(payload)
        self.assertEqual([m.message_id for m in result.messages], ['wamid.2'])
        self.assertEqual(result.skipped, 1)

    def test_missing_contact_name(self):
        self.assertIsNone(parse(webhook(change([text_message()], contacts=[]))).messages[0].display_name)
        no_profile = [{'wa_id': '6591234567'}]
        self.assertIsNone(parse(webhook(change([text_message()], contacts=no_profile))).messages[0].display_name)

    def test_contact_names_match_by_sender(self):
        contacts = [{'wa_id': '6598765432', 'profile': {'name': 'Bob'}}, {'wa_id': '6591234567', 'profile': {'name': 'Alice'}}]
        self.assertEqual(parse(webhook(change([text_message()], contacts=contacts))).messages[0].display_name, 'Alice')

    def test_messages_with_an_unexpected_shape_are_skipped(self):
        bad = [
            'not a dict',
            {**text_message(), 'from': None},
            {**text_message(), 'id': ''},
            {k: v for k, v in text_message().items() if k != 'type'},
            {**text_message(), 'timestamp': 'yesterday'},
        ]
        with self.assertLogs('app.parsing', 'WARNING'):
            result = parse(webhook(change([*bad, text_message('wamid.ok')], contacts=[])))
        self.assertEqual([m.message_id for m in result.messages], ['wamid.ok'])
        self.assertEqual(result.skipped, len(bad))

    def test_text_without_a_body(self):
        message = parse(webhook(change([{**text_message(), 'text': {}}]))).messages[0]
        self.assertIsNone(message.text)

    def test_malformed_payloads_never_crash(self):
        for payload in (None, [], 'x', 1, {}, {'entry': 'x'}, {'entry': [None]}, {'entry': [{'changes': [1]}]},
                        {'entry': [{'changes': [{'field': 'messages', 'value': None}]}]},
                        {'entry': [{'changes': [{'field': 'messages', 'value': {'messages': 'x'}}]}]}):
            with self.subTest(payload=payload):
                self.assertEqual(parse(payload).messages, [])


class HelperTests(unittest.TestCase):
    def test_to_e164(self):
        self.assertEqual(to_e164('6591234567'), '+6591234567')
        self.assertEqual(to_e164('+6591234567'), '+6591234567')

    def test_to_iso_timestamp(self):
        self.assertEqual(to_iso_timestamp('0'), '1970-01-01T00:00:00+00:00')
        self.assertEqual(to_iso_timestamp(1700000000), '2023-11-14T22:13:20+00:00')
        for bad in (None, '', 'abc', '1.5', '9' * 30):
            with self.subTest(bad=bad):
                self.assertIsNone(to_iso_timestamp(bad))
