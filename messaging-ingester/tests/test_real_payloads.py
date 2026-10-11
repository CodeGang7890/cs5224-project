"""Webhooks in the exact shape Meta sent them (captured in TODO.txt), with the phone number,
name and IDs replaced. They include fields the ingester doesn't use (user_id, from_user_id,
internal_1p_only_data, pricing...), which must simply be ignored.
"""

import unittest

from app.parsing import parse_webhook

PHONE_NUMBER_ID = '1359207187280395'

CUSTOMER_MESSAGE = {
    'object': 'whatsapp_business_account',
    'entry': [{
        'id': '1402880644763944',
        'changes': [{
            'value': {
                'messaging_product': 'whatsapp',
                'metadata': {'display_phone_number': '15556367390', 'phone_number_id': PHONE_NUMBER_ID},
                'contacts': [{
                    'profile': {'name': 'Test Customer'},
                    'wa_id': '6591234567',
                    'user_id': 'SG.1000000000000000',
                    'country_code': 'SG',
                }],
                'messages': [{
                    'from': '6591234567',
                    'from_user_id': 'SG.1000000000000000',
                    'id': 'wamid.HBgKNjU5MTIzNDU2NxUCABIYIEE1NUY2NzNCRTIzMTRDQjZCQTIxMDg3OTAzNkNFNDM1AA==',
                    'timestamp': '1791366359',
                    'text': {'body': 'Hello'},
                    'from_logical_id': '200000000000000',
                    'type': 'text',
                    'internal_1p_only_data': {'account_context': {
                        'waac_id': '1000000000000000',
                        'cs_id': PHONE_NUMBER_ID,
                        'account_context_type': 'non_paid_messaging',
                    }},
                }],
            },
            'field': 'messages',
        }],
    }],
}

STATUS_UPDATE = {
    'object': 'whatsapp_business_account',
    'entry': [{
        'id': '1402880644763944',
        'changes': [{
            'value': {
                'messaging_product': 'whatsapp',
                'metadata': {'display_phone_number': '15556367390', 'phone_number_id': PHONE_NUMBER_ID},
                'contacts': [{'wa_id': '6591234567', 'user_id': 'SG.1000000000000000'}],
                'statuses': [{
                    'id': 'wamid.HBgKNjU5MTIzNDU2NxUCABEYEkM4MzAwMjRDM0E1OTlBOUNFRQA=',
                    'status': 'delivered',
                    'timestamp': '1791366349',
                    'recipient_id': '6591234567',
                    'conversation': {'id': '47aff61b2ac0b300c6a1f8d9a200a584', 'origin': {'type': 'utility'}},
                    'pricing': {'billable': True, 'pricing_model': 'PMP', 'category': 'utility', 'type': 'regular'},
                }],
            },
            'field': 'messages',
        }],
    }],
}


class RealPayloadTests(unittest.TestCase):
    def test_customer_message(self):
        result = parse_webhook(CUSTOMER_MESSAGE, 1, PHONE_NUMBER_ID)
        self.assertEqual(result.skipped, 0)
        self.assertEqual(
            [m.to_dict() for m in result.messages],
            [{
                'business_id': 1,
                'phone_number_id': PHONE_NUMBER_ID,
                'message_id': 'wamid.HBgKNjU5MTIzNDU2NxUCABIYIEE1NUY2NzNCRTIzMTRDQjZCQTIxMDg3OTAzNkNFNDM1AA==',
                'from': '+6591234567',
                'display_name': 'Test Customer',
                'type': 'text',
                'text': 'Hello',
                'timestamp': '2026-10-07T09:45:59+00:00',
            }],
        )

    def test_status_update_publishes_nothing(self):
        result = parse_webhook(STATUS_UPDATE, 1, PHONE_NUMBER_ID)
        self.assertEqual((result.messages, result.skipped), ([], 0))
