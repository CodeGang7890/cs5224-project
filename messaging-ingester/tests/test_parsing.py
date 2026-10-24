import unittest

from app.parsing import AccountUpdate, InboundMessage, parse_account_updates, parse_webhook, to_e164, to_iso_timestamp

from .helpers import BUSINESS_ID, PHONE_NUMBER_ID, account_update, change, text_message, webhook


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


class ParseAccountUpdatesTests(unittest.TestCase):
    """Meta's account_update shapes (webhooks reference), from our app's /webhook."""

    def test_the_account_is_the_entry_id_or_waba_info(self):
        payload = webhook(
            account_update(ban_info={'waba_ban_state': 'REINSTATE', 'waba_ban_date': 'April 17, 2025'}),
            account_update('ACCOUNT_DELETED'),
            account_update('PARTNER_APP_UNINSTALLED', waba_info={
                'waba_id': '184943124712545', 'owner_business_id': '1284923862322270', 'partner_app_id': 869361281603019,
            }),
            account_update('PARTNER_REMOVED', waba_info={'waba_id': '980198427658004'},
                           disconnection_info={'reason': 'PRIMARY_INACTIVITY', 'initiated_by': 'SYSTEM'}),
        )
        self.assertEqual(parse_account_updates(payload), [
            AccountUpdate('102290129340398', 'DISABLED_UPDATE', ban_state='REINSTATE'),
            AccountUpdate('102290129340398', 'ACCOUNT_DELETED'),
            AccountUpdate('184943124712545', 'PARTNER_APP_UNINSTALLED', partner_app_id='869361281603019'),
            AccountUpdate('980198427658004', 'PARTNER_REMOVED'),
        ])

    def test_other_fields_and_malformed_changes_are_skipped(self):
        payload = webhook(
            change(messages=[text_message()]),
            account_update(''),
            {'field': 'account_update', 'value': 'not a dict'},
            account_update('ACCOUNT_DELETED', waba_info={'waba_id': 'abc'}),  # falls back to the entry id
        )
        payload['entry'].append({'id': 'not-a-number', 'changes': [account_update('ACCOUNT_DELETED')]})
        with self.assertLogs('app.parsing', 'WARNING') as logs:
            updates = parse_account_updates(payload)
        self.assertEqual(updates, [AccountUpdate('102290129340398', 'ACCOUNT_DELETED')])
        self.assertEqual(len(logs.output), 3)

    def test_not_a_webhook(self):
        for payload in (None, [], {'entry': 'x'}, {'entry': [None, {'changes': None}]}):
            with self.subTest(payload=payload):
                self.assertEqual(parse_account_updates(payload), [])
