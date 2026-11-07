"""Shared test data: Meta webhook payloads, and fakes for configuration-service and Pub/Sub."""

import json

from app.parsing import AccountUpdate, InboundMessage
from app.publisher import PublishError
from app.verification import BusinessNotConnectedError, Verification, ConfigurationServiceUnavailableError

BUSINESS_ID = 7
PHONE_NUMBER_ID = '106540352242922'
VERIFY_TOKEN = 'the-verify-token'
VALID_SIGNATURE = 'sha256=valid'


def text_message(message_id='wamid.1', sender='6591234567', body='Hi, do you have cakes?', timestamp='1700000000'):
    return {'from': sender, 'id': message_id, 'timestamp': timestamp, 'type': 'text', 'text': {'body': body}}


def change(messages=(), phone_number_id=PHONE_NUMBER_ID, contacts=None, statuses=None, field='messages'):
    value = {
        'messaging_product': 'whatsapp',
        'metadata': {'display_phone_number': '15550001234', 'phone_number_id': phone_number_id},
    }
    if messages:
        value['messages'] = list(messages)
        value['contacts'] = contacts if contacts is not None else [
            {'wa_id': m['from'], 'profile': {'name': 'Alice'}} for m in messages
        ]
    if statuses:
        value['statuses'] = statuses
    return {'field': field, 'value': value}


def account_update(event='DISABLED_UPDATE', **value):
    """An account_update change (our app's webhook), e.g. account_update(ban_info={'waba_ban_state': 'DISABLE'})."""
    return {'field': 'account_update', 'value': {'event': event, **value}}


def webhook(*changes):
    return {'object': 'whatsapp_business_account', 'entry': [{'id': '102290129340398', 'changes': list(changes)}]}


def body(payload) -> bytes:
    return json.dumps(payload).encode()


class FakeVerifier:
    """Stands in for ConfigurationServiceClient. `error` makes every call raise it."""

    def __init__(self, verify_token=VERIFY_TOKEN, signature=VALID_SIGNATURE, error=None):
        self.verify_token_value = verify_token
        self.signature_value = signature
        self.error = error
        self.report_error = None  # only report_account_updates raises it
        self.reported: list[AccountUpdate] = []
        self.calls = []

    def verify_token(self, business_id, verify_token):
        self.calls.append(('verify_token', business_id, verify_token))
        if self.error:
            raise self.error
        valid = verify_token == self.verify_token_value
        return Verification(valid=valid, phone_number_id=PHONE_NUMBER_ID if valid else None)

    def verify_signature(self, business_id, body, signature):
        self.calls.append(('verify_signature', business_id, body, signature))
        if self.error:
            raise self.error
        valid = signature == self.signature_value
        return Verification(valid=valid, phone_number_id=PHONE_NUMBER_ID if valid else None)


    def verify_app_token(self, verify_token):
        self.calls.append(('verify_app_token', verify_token))
        if self.error:
            raise self.error
        return Verification(valid=verify_token == self.verify_token_value, phone_number_id=None)

    def verify_app_signature(self, body, signature):
        self.calls.append(('verify_app_signature', body, signature))
        if self.error:
            raise self.error
        return Verification(valid=signature == self.signature_value, phone_number_id=None)

    def report_account_updates(self, updates):
        self.calls.append(('report_account_updates', list(updates)))
        if self.error or self.report_error:
            raise self.error or self.report_error
        self.reported += updates
        return len(updates)  # as if each changed one connection


class FakePublisher:
    def __init__(self, fail=False):
        self.fail = fail
        self.published: list[InboundMessage] = []
        self.calls = 0

    def publish(self, messages):
        self.calls += 1
        if self.fail:
            raise PublishError('Pub/Sub is down')
        self.published.extend(messages)


NOT_CONNECTED = BusinessNotConnectedError('not connected')
UNAVAILABLE = ConfigurationServiceUnavailableError('configuration-service is down')
