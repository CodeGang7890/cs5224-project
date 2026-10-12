import hashlib
import hmac
import json
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import httpx
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.db import IntegrityError, connection, transaction
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APITestCase

from auth_app.models import BusinessUser

from . import crypto, meta_api
from .models import (
    BUSINESS_NAME_MAX_LENGTH,
    DESCRIPTION_MAX_LENGTH,
    WHATSAPP_ACCESS_TOKEN_MAX_LENGTH,
    WHATSAPP_APP_SECRET_MAX_LENGTH,
    WHATSAPP_ID_MAX_LENGTH,
    BusinessConfiguration,
    WhatsAppConfiguration,
)
from .views import INTERNAL_API_KEY_HEADER, SIGNATURE_HEADER


class RandomNumberViewTests(TestCase):
    url = reverse('configuration_app:random-number')

    def test_returns_number_between_1_and_10(self):
        for _ in range(50):
            response = self.client.get(self.url)
            self.assertEqual(response.status_code, 200)
            self.assertIn(response.json()['value'], range(1, 11))

    def test_allows_frontend_dev_origin(self):
        response = self.client.get(self.url, headers={'Origin': 'http://localhost:5173'})
        self.assertEqual(response.headers.get('Access-Control-Allow-Origin'), 'http://localhost:5173')

    def test_preflight_from_frontend_dev_origin(self):
        response = self.client.options(
            self.url,
            headers={
                'Origin': 'http://localhost:5173',
                'Access-Control-Request-Method': 'GET',
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get('Access-Control-Allow-Origin'), 'http://localhost:5173')

    def test_rejects_unknown_origin(self):
        response = self.client.get(self.url, headers={'Origin': 'http://evil.example'})
        self.assertNotIn('Access-Control-Allow-Origin', response.headers)


class BusinessConfigurationModelTests(TestCase):
    def test_valid_business(self):
        BusinessConfiguration(business_name='Shop', location='Singapore').full_clean()

    def test_length_limits(self):
        cases = {
            'business_name': 'x' * (BUSINESS_NAME_MAX_LENGTH + 1),
            'description': 'x' * (DESCRIPTION_MAX_LENGTH + 1),
        }
        for field, value in cases.items():
            with self.subTest(field=field):
                business = BusinessConfiguration(business_name='Shop', location='Singapore')
                setattr(business, field, value)
                with self.assertRaises(ValidationError) as ctx:
                    business.full_clean()
                self.assertIn(field, ctx.exception.message_dict)

    def test_name_and_location_required(self):
        with self.assertRaises(ValidationError) as ctx:
            BusinessConfiguration(business_name='', location='').full_clean()
        self.assertEqual(set(ctx.exception.message_dict), {'business_name', 'location'})


# --- Internal WhatsApp webhook checks (/api/internal/whatsapp/<business_id>/verify-…/) ---------

TEST_INTERNAL_KEY = 'test-internal-key'
TEST_APP_SECRET = '0123456789abcdef0123456789abcdef'
TEST_PAYLOAD = '{"object":"whatsapp_business_account","entry":[{"id":"1","changes":[]}],"note":"caf\\u00e9"}'.encode()


def meta_signature(payload: bytes, secret: str = TEST_APP_SECRET) -> str:
    """X-Hub-Signature-256 as Meta computes it."""
    return 'sha256=' + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()


@override_settings(INTERNAL_API_KEY=TEST_INTERNAL_KEY)
class InternalWhatsAppVerifyAPITests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.cafe = BusinessConfiguration.objects.create(business_name='Café', location='Singapore')
        cls.florist = BusinessConfiguration.objects.create(business_name='Florist', location='Singapore')
        cls.config = WhatsAppConfiguration.objects.create(
            business=cls.cafe, phone_number_id='106540352242922', access_token='EAAGtoken', app_secret=TEST_APP_SECRET
        )
        cls.cafe_user = BusinessUser.objects.create_user(username='cafe', password='123', business=cls.cafe)

    def post(self, name, business_id, data, key=TEST_INTERNAL_KEY):
        headers = {} if key is None else {INTERNAL_API_KEY_HEADER: key}
        url = reverse(f'internal:whatsapp-{name}', args=[business_id])
        return self.client.post(url, data, format='json', headers=headers)

    def verify_token(self, token, business_id=None, **kwargs):
        return self.post('verify-token', business_id or self.cafe.pk, {'verify_token': token}, **kwargs)

    def verify_signature(self, payload, signature, business_id=None, key=TEST_INTERNAL_KEY,
                         content_type='application/octet-stream'):
        """Forwards a webhook like the ingester does: raw body + Meta's signature header."""
        headers = {} if key is None else {INTERNAL_API_KEY_HEADER: key}
        if signature is not None:
            headers[SIGNATURE_HEADER] = signature
        url = reverse('internal:whatsapp-verify-signature', args=[business_id or self.cafe.pk])
        return self.client.post(url, payload, content_type=content_type, headers=headers)

    # --- verify-token ---------------------------------------------------------------------

    def test_verify_token_matches(self):
        response = self.verify_token(self.config.verify_token)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'valid': True, 'phone_number_id': '106540352242922'})

    def test_verify_token_mismatch(self):
        for token in ('', 'wrong', self.config.verify_token + 'x', self.config.verify_token.upper()):
            with self.subTest(token=token):
                response = self.verify_token(token)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json(), {'valid': False, 'phone_number_id': None})

    # --- verify-signature -----------------------------------------------------------------

    def test_signature_matches(self):
        response = self.verify_signature(TEST_PAYLOAD, meta_signature(TEST_PAYLOAD))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'valid': True, 'phone_number_id': '106540352242922'})

    def test_signature_hex_case_does_not_matter(self):
        signature = 'sha256=' + meta_signature(TEST_PAYLOAD).removeprefix('sha256=').upper()
        self.assertTrue(self.verify_signature(TEST_PAYLOAD, signature).json()['valid'])

    def test_signature_mismatch(self):
        cases = {
            'other secret': (TEST_PAYLOAD, meta_signature(TEST_PAYLOAD, secret='f' * 32)),
            'tampered body': (TEST_PAYLOAD + b' ', meta_signature(TEST_PAYLOAD)),
            'missing prefix': (TEST_PAYLOAD, meta_signature(TEST_PAYLOAD).removeprefix('sha256=')),
            'sha1 prefix': (TEST_PAYLOAD, 'sha1=' + meta_signature(TEST_PAYLOAD).removeprefix('sha256=')),
            'empty': (TEST_PAYLOAD, ''),
            'no header': (TEST_PAYLOAD, None),
            'garbage': (TEST_PAYLOAD, 'sha256=not-hex'),
            'empty body': (b'', meta_signature(TEST_PAYLOAD)),
        }
        for name, (payload, signature) in cases.items():
            with self.subTest(name):
                response = self.verify_signature(payload, signature)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json(), {'valid': False, 'phone_number_id': None})

    def test_signature_covers_the_exact_bytes(self):
        reencoded = TEST_PAYLOAD.decode('unicode_escape').encode()  # same JSON, \\u00e9 written as é
        self.assertFalse(self.verify_signature(reencoded, meta_signature(TEST_PAYLOAD)).json()['valid'])
        self.assertTrue(self.verify_signature(reencoded, meta_signature(reencoded)).json()['valid'])

    def test_signature_body_is_not_parsed(self):
        # Forwarded as JSON (or anything else) it still works: only the raw bytes matter.
        response = self.verify_signature(TEST_PAYLOAD, meta_signature(TEST_PAYLOAD), content_type='application/json')
        self.assertTrue(response.json()['valid'])
        not_json = b'\x00\xff not json'
        self.assertTrue(self.verify_signature(not_json, meta_signature(not_json)).json()['valid'])

    # --- Shared rules ---------------------------------------------------------------------

    def test_verify_token_missing_field_is_400(self):
        response = self.post('verify-token', self.cafe.pk, {})
        self.assertEqual(response.status_code, 400)
        self.assertIn('verify_token', response.json())

    def test_not_connected_or_unknown_business_is_404(self):
        for business_id in (self.florist.pk, 999_999):
            with self.subTest(business_id=business_id):
                self.assertEqual(self.verify_token('x', business_id=business_id).status_code, 404)
                self.assertEqual(self.verify_signature(TEST_PAYLOAD, 'sha256=00', business_id=business_id).status_code, 404)

    def test_missing_or_wrong_key_is_403(self):
        for key in (None, '', 'wrong', TEST_INTERNAL_KEY + 'x'):
            with self.subTest(key=key):
                self.assertEqual(self.verify_token(self.config.verify_token, key=key).status_code, 403)
                self.assertEqual(self.verify_signature(TEST_PAYLOAD, meta_signature(TEST_PAYLOAD), key=key).status_code, 403)

    def test_a_logged_in_user_is_not_enough(self):
        self.client.force_authenticate(self.cafe_user)
        self.assertEqual(self.verify_token(self.config.verify_token, key=None).status_code, 403)

    @override_settings(INTERNAL_API_KEY='')
    def test_disabled_when_no_key_is_configured(self):
        self.assertEqual(self.verify_token(self.config.verify_token, key='').status_code, 403)

    def test_only_post_is_allowed(self):
        url = reverse('internal:whatsapp-verify-token', args=[self.cafe.pk])
        for method in ('get', 'put', 'delete'):
            with self.subTest(method=method):
                response = getattr(self.client, method)(url, headers={INTERNAL_API_KEY_HEADER: TEST_INTERNAL_KEY})
                self.assertEqual(response.status_code, 405)

    def test_no_secret_is_ever_returned(self):
        responses = [
            self.verify_token(self.config.verify_token),
            self.verify_token('wrong'),
            self.verify_signature(TEST_PAYLOAD, meta_signature(TEST_PAYLOAD)),
            self.verify_signature(TEST_PAYLOAD, 'sha256=00'),
        ]
        for response in responses:
            body = response.content.decode()
            for secret in (TEST_APP_SECRET, 'EAAGtoken', self.config.verify_token):
                self.assertNotIn(secret, body)


# --- Owner-facing WhatsApp connection (/api/configuration/whatsapp/) ----------------------------

TEST_ACCESS_TOKEN = 'EAAGm0PX4ZCpsBAJZBZCqkw0ZD'
TEST_PHONE_NUMBER_ID = '106540352242922'
VALID_WHATSAPP = {
    'phone_number_id': TEST_PHONE_NUMBER_ID,
    'access_token': TEST_ACCESS_TOKEN,
    'app_secret': TEST_APP_SECRET,
}
SECRET_REQUIRED = ['This field is required when connecting WhatsApp for the first time.']
META_INFO = meta_api.PhoneNumberInfo(display_phone_number='+65 9123 4567', verified_name='Café Pte Ltd')


def create_whatsapp_config(business, **overrides) -> WhatsAppConfiguration:
    return WhatsAppConfiguration.objects.create(business=business, **{**VALID_WHATSAPP, **overrides})


@override_settings(MESSAGING_INGESTER_PUBLIC_URL='https://ingester.example')
class WhatsAppConfigurationAPITests(APITestCase):
    url = reverse('configuration_app:whatsapp-configuration')

    @classmethod
    def setUpTestData(cls):
        cls.cafe = BusinessConfiguration.objects.create(business_name='Café', location='Singapore')
        cls.florist = BusinessConfiguration.objects.create(business_name='Florist', location='Singapore')
        cls.cafe_user = BusinessUser.objects.create_user(username='cafe', password='123', business=cls.cafe)
        cls.florist_user = BusinessUser.objects.create_user(
            username='florist', password='123', business=cls.florist
        )
        cls.no_business_user = BusinessUser.objects.create_user(username='nobiz', password='123')

    def setUp(self):
        # Every save checks the credentials with Meta: fake it (tests never call the real Meta).
        patcher = patch.object(meta_api, 'check_credentials', return_value=META_INFO)
        self.meta = patcher.start()
        self.addCleanup(patcher.stop)

    def put(self, data, user=None):
        self.client.force_authenticate(user or self.cafe_user)
        return self.client.put(self.url, data, format='json')

    def saved(self) -> WhatsAppConfiguration:
        return WhatsAppConfiguration.objects.get(business=self.cafe)

    # --- Access ---------------------------------------------------------------------------

    def test_requires_authentication(self):
        for method in ('get', 'put', 'delete'):
            with self.subTest(method=method):
                self.assertEqual(getattr(self.client, method)(self.url).status_code, 401)

    def test_user_without_business_gets_403(self):
        self.client.force_authenticate(self.no_business_user)
        for method in ('get', 'put', 'delete'):
            with self.subTest(method=method):
                response = getattr(self.client, method)(self.url, VALID_WHATSAPP, format='json')
                self.assertEqual(response.status_code, 403)
        self.assertFalse(WhatsAppConfiguration.objects.exists())

    def test_other_methods_are_not_allowed(self):
        self.client.force_authenticate(self.cafe_user)
        for method in ('post', 'patch'):
            with self.subTest(method=method):
                response = getattr(self.client, method)(self.url, VALID_WHATSAPP, format='json')
                self.assertEqual(response.status_code, 405)

    def test_businesses_only_see_and_change_their_own(self):
        create_whatsapp_config(self.cafe)
        self.client.force_authenticate(self.florist_user)
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertEqual(self.client.delete(self.url).status_code, 404)
        # Connecting the florist doesn't touch the café's connection.
        self.assertEqual(self.put({**VALID_WHATSAPP, 'phone_number_id': '2'}, self.florist_user).status_code, 201)
        self.assertEqual(self.saved().phone_number_id, TEST_PHONE_NUMBER_ID)
        self.assertEqual(WhatsAppConfiguration.objects.count(), 2)

    # --- GET ------------------------------------------------------------------------------

    def test_get_before_connecting_is_404(self):
        self.client.force_authenticate(self.cafe_user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()['detail'], 'Your business has not connected WhatsApp yet. Connect it with PUT.')

    def test_get(self):
        config = create_whatsapp_config(self.cafe)
        self.client.force_authenticate(self.cafe_user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(
            set(body),
            {'phone_number_id', 'display_phone_number', 'verified_name', 'webhook_url', 'verify_token',
             'created_time', 'last_updated'},
        )
        self.assertEqual(body['phone_number_id'], TEST_PHONE_NUMBER_ID)
        self.assertEqual(body['verify_token'], config.verify_token)
        self.assertEqual(body['webhook_url'], f'https://ingester.example/webhook/{self.cafe.pk}')

    def test_secrets_are_never_returned(self):
        responses = [self.put(VALID_WHATSAPP), self.client.get(self.url), self.put({'phone_number_id': '9'})]
        for response in responses:
            body = response.content.decode()
            self.assertNotIn('access_token', body)
            self.assertNotIn('app_secret', body)
            self.assertNotIn(TEST_ACCESS_TOKEN, body)
            self.assertNotIn(TEST_APP_SECRET, body)

    # --- PUT: connect ---------------------------------------------------------------------

    def test_connect(self):
        response = self.put(VALID_WHATSAPP)
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body['phone_number_id'], TEST_PHONE_NUMBER_ID)
        self.assertEqual(body['webhook_url'], f'https://ingester.example/webhook/{self.cafe.pk}')
        self.assertEqual(len(body['verify_token']), 43)

        config = self.saved()
        self.assertEqual(config.access_token, TEST_ACCESS_TOKEN)
        self.assertEqual(config.app_secret, TEST_APP_SECRET)
        self.assertEqual(config.verify_token, body['verify_token'])

    def test_connect_requires_both_secrets(self):
        for missing in ({'access_token'}, {'app_secret'}, {'access_token', 'app_secret'}):
            for blank in (False, True):
                with self.subTest(missing=missing, blank=blank):
                    data = {k: v for k, v in VALID_WHATSAPP.items() if k not in missing}
                    if blank:
                        data.update({field: '  ' for field in missing})  # whitespace is trimmed to blank
                    response = self.put(data)
                    self.assertEqual(response.status_code, 400)
                    self.assertEqual(response.json(), {field: SECRET_REQUIRED for field in missing})
        self.assertFalse(WhatsAppConfiguration.objects.exists())

    def test_connect_requires_the_phone_number_id(self):
        secrets = {'access_token': TEST_ACCESS_TOKEN, 'app_secret': TEST_APP_SECRET}
        for data in (secrets, {**secrets, 'phone_number_id': ''}):
            with self.subTest(data=data):
                response = self.put(data)
                self.assertEqual(response.status_code, 400)
                self.assertEqual(set(response.json()), {'phone_number_id'})

    def test_secrets_are_trimmed(self):
        self.put({**VALID_WHATSAPP, 'access_token': f'  {TEST_ACCESS_TOKEN}\n', 'app_secret': f' {TEST_APP_SECRET} '})
        self.assertEqual(self.saved().access_token, TEST_ACCESS_TOKEN)
        self.assertEqual(self.saved().app_secret, TEST_APP_SECRET)

    def test_invalid_values(self):
        cases = {
            'phone_number_id': ['abc', '1065 4035', '-1', '1.5', '1' * (WHATSAPP_ID_MAX_LENGTH + 1)],
            'access_token': ['has a space', 'x' * (WHATSAPP_ACCESS_TOKEN_MAX_LENGTH + 1)],
            'app_secret': ['has a space', 'x' * (WHATSAPP_APP_SECRET_MAX_LENGTH + 1)],
        }
        for field, values in cases.items():
            for value in values:
                with self.subTest(field=field, value=value):
                    response = self.put({**VALID_WHATSAPP, field: value})
                    self.assertEqual(response.status_code, 400)
                    self.assertEqual(set(response.json()), {field})
        self.assertFalse(WhatsAppConfiguration.objects.exists())

    def test_longest_valid_values(self):
        response = self.put({
            'phone_number_id': '1' * WHATSAPP_ID_MAX_LENGTH,
            'access_token': 'x' * WHATSAPP_ACCESS_TOKEN_MAX_LENGTH,
            'app_secret': 'y' * WHATSAPP_APP_SECRET_MAX_LENGTH,
        })
        self.assertEqual(response.status_code, 201)
        self.assertEqual(self.saved().access_token, 'x' * WHATSAPP_ACCESS_TOKEN_MAX_LENGTH)

    def test_read_only_and_unknown_fields_are_ignored(self):
        response = self.put({
            **VALID_WHATSAPP,
            'verify_token': 'mine',
            'webhook_url': 'https://evil.example',
            'business': self.florist.pk,
            'display_phone_number': '+6591234567',
        })
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertNotEqual(body['verify_token'], 'mine')
        self.assertEqual(body['webhook_url'], f'https://ingester.example/webhook/{self.cafe.pk}')
        self.assertEqual(self.saved().business, self.cafe)

    def test_phone_number_id_must_be_unique_across_businesses(self):
        create_whatsapp_config(self.florist)
        response = self.put(VALID_WHATSAPP)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json(), {'phone_number_id': ['This phone number ID is already connected to another business.']}
        )

    # --- PUT: update ----------------------------------------------------------------------

    def test_update_keeps_secrets_when_left_out_or_blank(self):
        original = create_whatsapp_config(self.cafe)
        for secrets in ({}, {'access_token': '', 'app_secret': ''}, {'access_token': ' ', 'app_secret': None}):
            with self.subTest(secrets=secrets):
                data = {'phone_number_id': '999', **{k: v for k, v in secrets.items() if v is not None}}
                response = self.put(data)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()['phone_number_id'], '999')
                config = self.saved()
                self.assertEqual(config.access_token, TEST_ACCESS_TOKEN)
                self.assertEqual(config.app_secret, TEST_APP_SECRET)
                self.assertEqual(config.verify_token, original.verify_token)
                self.assertEqual(config.created_time, original.created_time)
        self.assertEqual(WhatsAppConfiguration.objects.count(), 1)

    def test_update_replaces_one_secret(self):
        create_whatsapp_config(self.cafe)
        response = self.put({**VALID_WHATSAPP, 'access_token': 'NEWTOKEN', 'app_secret': ''})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.saved().access_token, 'NEWTOKEN')
        self.assertEqual(self.saved().app_secret, TEST_APP_SECRET)

    def test_update_can_keep_its_own_phone_number_id(self):
        create_whatsapp_config(self.cafe)
        self.assertEqual(self.put(VALID_WHATSAPP).status_code, 200)

    def test_update_still_validates(self):
        create_whatsapp_config(self.cafe)
        response = self.put({'phone_number_id': 'abc', 'access_token': 'has a space'})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(set(response.json()), {'phone_number_id', 'access_token'})
        self.assertEqual(self.saved().phone_number_id, TEST_PHONE_NUMBER_ID)

    # --- Checked with Meta -----------------------------------------------------------------

    def test_connect_checks_with_meta_and_stores_its_details(self):
        response = self.put(VALID_WHATSAPP)
        self.assertEqual(response.status_code, 201)
        self.meta.assert_called_once_with(TEST_PHONE_NUMBER_ID, TEST_ACCESS_TOKEN, TEST_APP_SECRET)
        self.assertEqual(response.json()['display_phone_number'], '+65 9123 4567')
        self.assertEqual(response.json()['verified_name'], 'Café Pte Ltd')
        self.assertEqual(self.saved().verified_name, 'Café Pte Ltd')

    def test_update_checks_the_saved_secrets_with_the_new_phone_number_id(self):
        create_whatsapp_config(self.cafe)
        self.put({'phone_number_id': '999'})
        self.meta.assert_called_once_with('999', TEST_ACCESS_TOKEN, TEST_APP_SECRET)

    def test_update_checks_a_replaced_secret(self):
        create_whatsapp_config(self.cafe)
        self.put({'phone_number_id': TEST_PHONE_NUMBER_ID, 'app_secret': 'newsecret'})
        self.meta.assert_called_once_with(TEST_PHONE_NUMBER_ID, TEST_ACCESS_TOKEN, 'newsecret')

    def test_update_refreshes_metas_details(self):
        create_whatsapp_config(self.cafe)
        self.meta.return_value = meta_api.PhoneNumberInfo('+65 8000 0000', 'Renamed Café')
        self.put(VALID_WHATSAPP)
        self.assertEqual((self.saved().display_phone_number, self.saved().verified_name), ('+65 8000 0000', 'Renamed Café'))

    def test_credentials_meta_rejects_are_400_under_their_field(self):
        for field, message in (
            ('access_token', meta_api.INVALID_TOKEN_MESSAGE),
            ('app_secret', meta_api.INVALID_APP_SECRET_MESSAGE),
            ('phone_number_id', meta_api.UNKNOWN_PHONE_NUMBER_ID_MESSAGE),
        ):
            with self.subTest(field=field):
                self.meta.side_effect = meta_api.MetaCredentialsError(field, message)
                response = self.put(VALID_WHATSAPP)
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json(), {field: [message]})
        self.assertFalse(WhatsAppConfiguration.objects.exists())

    def test_rejected_update_changes_nothing(self):
        create_whatsapp_config(self.cafe)
        self.meta.side_effect = meta_api.MetaCredentialsError('access_token', meta_api.INVALID_TOKEN_MESSAGE)
        response = self.put({'phone_number_id': '999', 'access_token': 'BADTOKEN'})
        self.assertEqual(response.status_code, 400)
        self.assertEqual((self.saved().phone_number_id, self.saved().access_token), (TEST_PHONE_NUMBER_ID, TEST_ACCESS_TOKEN))

    def test_meta_unreachable_is_503_and_nothing_is_saved(self):
        self.meta.side_effect = meta_api.MetaUnavailableError('timeout')
        response = self.put(VALID_WHATSAPP)
        self.assertEqual(response.status_code, 503)
        self.assertIn("Couldn't reach Meta", response.json()['detail'])
        self.assertFalse(WhatsAppConfiguration.objects.exists())

    def test_meta_is_not_asked_when_the_fields_are_invalid(self):
        create_whatsapp_config(self.florist)  # owns TEST_PHONE_NUMBER_ID
        for data in (
            {**VALID_WHATSAPP, 'phone_number_id': 'abc'},
            {'phone_number_id': '1', 'access_token': TEST_ACCESS_TOKEN},  # missing App Secret
            VALID_WHATSAPP,  # Phone Number ID already used by the florist
        ):
            with self.subTest(data=data):
                self.assertEqual(self.put(data).status_code, 400)
        self.meta.assert_not_called()

    # --- DELETE ---------------------------------------------------------------------------

    def test_disconnect(self):
        create_whatsapp_config(self.cafe)
        self.client.force_authenticate(self.cafe_user)
        self.assertEqual(self.client.delete(self.url).status_code, 204)
        self.assertFalse(WhatsAppConfiguration.objects.exists())
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertEqual(self.client.delete(self.url).status_code, 404)
        self.assertTrue(BusinessConfiguration.objects.filter(pk=self.cafe.pk).exists())

    def test_reconnect_gets_a_new_verify_token(self):
        first = self.put(VALID_WHATSAPP).json()['verify_token']
        self.client.delete(self.url)
        second = self.put(VALID_WHATSAPP).json()['verify_token']
        self.assertNotEqual(first, second)


class WhatsAppConfigurationModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.cafe = BusinessConfiguration.objects.create(business_name='Café', location='Singapore')

    def raw_column(self, config, column):
        with connection.cursor() as cursor:
            cursor.execute(
                f'SELECT {column} FROM {WhatsAppConfiguration._meta.db_table} WHERE id = %s', [config.pk]
            )
            return cursor.fetchone()[0]

    def test_valid(self):
        WhatsAppConfiguration(business=self.cafe, **VALID_WHATSAPP).full_clean()

    def test_secrets_are_encrypted_at_rest(self):
        config = create_whatsapp_config(self.cafe)
        for column, plaintext in (('access_token', TEST_ACCESS_TOKEN), ('app_secret', TEST_APP_SECRET)):
            with self.subTest(column=column):
                raw = self.raw_column(config, column)
                self.assertNotIn(plaintext, raw)
                self.assertTrue(raw.startswith('gAAAAA'))  # Fernet token
                self.assertEqual(crypto.decrypt(raw), plaintext)
        config.refresh_from_db()
        self.assertEqual(config.access_token, TEST_ACCESS_TOKEN)
        self.assertEqual(config.app_secret, TEST_APP_SECRET)

    def test_other_fields_are_not_encrypted(self):
        config = create_whatsapp_config(self.cafe)
        self.assertEqual(self.raw_column(config, 'phone_number_id'), TEST_PHONE_NUMBER_ID)
        self.assertEqual(self.raw_column(config, 'verify_token'), config.verify_token)

    def test_encrypting_twice_gives_different_ciphertexts(self):
        self.assertNotEqual(crypto.encrypt('same'), crypto.encrypt('same'))
        self.assertEqual(crypto.decrypt(crypto.encrypt('same')), 'same')

    def test_verify_tokens_are_random_and_url_safe(self):
        florist = BusinessConfiguration.objects.create(business_name='Florist', location='Singapore')
        first = create_whatsapp_config(self.cafe)
        second = create_whatsapp_config(florist, phone_number_id='2')
        self.assertNotEqual(first.verify_token, second.verify_token)
        self.assertRegex(first.verify_token, r'^[A-Za-z0-9_-]{43}$')

    def test_reading_with_a_different_key_fails_clearly(self):
        config = create_whatsapp_config(self.cafe)
        with override_settings(CONFIGURATION_ENCRYPTION_KEY='another-key'):
            with self.assertRaisesMessage(ImproperlyConfigured, 'CONFIGURATION_ENCRYPTION_KEY has changed'):
                WhatsAppConfiguration.objects.get(pk=config.pk)

    @override_settings(CONFIGURATION_ENCRYPTION_KEY='')
    def test_falls_back_to_secret_key(self):
        config = create_whatsapp_config(self.cafe)
        config.refresh_from_db()
        self.assertEqual(config.access_token, TEST_ACCESS_TOKEN)

    @override_settings(CONFIGURATION_ENCRYPTION_KEY='', SECRET_KEY='')
    def test_needs_a_key(self):
        with self.assertRaises(ImproperlyConfigured):
            crypto.encrypt('x')

    def test_database_rejects_empty_fields(self):
        for field in ('phone_number_id', 'access_token', 'app_secret', 'verify_token'):
            with self.subTest(field=field):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    create_whatsapp_config(self.cafe, **{field: ''})

    def test_one_connection_per_business(self):
        create_whatsapp_config(self.cafe)
        with self.assertRaises(IntegrityError), transaction.atomic():
            create_whatsapp_config(self.cafe, phone_number_id='2')

    def test_deleted_with_the_business(self):
        create_whatsapp_config(self.cafe)
        self.cafe.delete()
        self.assertFalse(WhatsAppConfiguration.objects.exists())


# --- Meta Graph API client (configuration_app/meta_api.py) ------------------------------------

@override_settings(META_GRAPH_API_URL='https://graph.example/v25.0')
class MetaApiTests(SimpleTestCase):
    def check(self, status=200, body=None, error=None, raw=None):
        """Runs check_credentials against a fake Meta; returns its result (or raises)."""
        self.requests = []

        def handler(request):
            self.requests.append(request)
            if error is not None:
                raise error
            if raw is not None:
                return httpx.Response(status, content=raw)
            return httpx.Response(status, json=body if body is not None else {
                'display_phone_number': '+65 9123 4567', 'verified_name': 'Café Pte Ltd', 'id': '106540352242922',
            })

        return meta_api.check_credentials('106540352242922', 'EAAGtoken', 'appsecret', transport=httpx.MockTransport(handler))

    @staticmethod
    def meta_error(code, message='Error', status=400):
        return {'status': status, 'body': {'error': {'message': message, 'type': 'OAuthException', 'code': code}}}

    def test_request(self):
        self.check()
        request = self.requests[0]
        url = urlsplit(str(request.url))
        self.assertEqual(f'{url.scheme}://{url.netloc}{url.path}', 'https://graph.example/v25.0/106540352242922')
        self.assertEqual(request.method, 'GET')
        self.assertEqual(request.headers['Authorization'], 'Bearer EAAGtoken')
        query = parse_qs(url.query)
        self.assertEqual(query['fields'], ['display_phone_number,verified_name'])
        expected_proof = hmac.new(b'appsecret', b'EAAGtoken', hashlib.sha256).hexdigest()
        self.assertEqual(query['appsecret_proof'], [expected_proof])

    def test_success_returns_metas_details(self):
        self.assertEqual(self.check(), meta_api.PhoneNumberInfo('+65 9123 4567', 'Café Pte Ltd'))

    def test_success_with_missing_details(self):
        self.assertEqual(self.check(body={'id': '1'}), meta_api.PhoneNumberInfo('', ''))

    def test_errors_map_to_the_field_they_are_about(self):
        cases = [
            (self.meta_error(190, 'Error validating access token: Session has expired'), 'access_token', meta_api.INVALID_TOKEN_MESSAGE),
            (self.meta_error(100, 'Invalid appsecret_proof provided in the API argument'), 'app_secret', meta_api.INVALID_APP_SECRET_MESSAGE),
            (self.meta_error(100, 'Unsupported get request. Object with ID does not exist'), 'phone_number_id', meta_api.UNKNOWN_PHONE_NUMBER_ID_MESSAGE),
            (self.meta_error(10, 'Application does not have permission'), 'access_token', meta_api.TOKEN_PERMISSION_MESSAGE),
            (self.meta_error(200, 'Permissions error', status=403), 'access_token', meta_api.TOKEN_PERMISSION_MESSAGE),
            (self.meta_error(803, 'Some other problem'), 'non_field_errors', 'Meta rejected these credentials: Some other problem'),
        ]
        for kwargs, field, message in cases:
            with self.subTest(field=field, code=kwargs['body']['error']['code']):
                with self.assertRaises(meta_api.MetaCredentialsError) as ctx:
                    self.check(**kwargs)
                self.assertEqual((ctx.exception.field, ctx.exception.message), (field, message))

    def test_meta_side_problems_mean_unavailable(self):
        cases = [
            self.meta_error(4, 'Application request limit reached'),
            self.meta_error(2, 'Service temporarily unavailable', status=503),
            {'status': 500, 'body': {}},
            {'status': 502, 'raw': b'<html>Bad gateway</html>'},
            {'status': 200, 'body': ['not', 'an', 'object']},
        ]
        for kwargs in cases:
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(meta_api.MetaUnavailableError):
                    self.check(**kwargs)

    def test_network_errors_mean_unavailable(self):
        for error in (httpx.ConnectError('refused'), httpx.ReadTimeout('slow')):
            with self.subTest(error=type(error).__name__):
                with self.assertRaises(meta_api.MetaUnavailableError):
                    self.check(error=error)

    def test_appsecret_proof(self):
        self.assertEqual(
            meta_api.appsecret_proof('token', 'secret'),
            hmac.new(b'secret', b'token', hashlib.sha256).hexdigest(),
        )



class SampleWhatsAppConfigurationFixtureTests(TestCase):
    """configuration_app/fixtures/sample_whatsapp_configurations.json: every sample business is
    connected (dummy credentials, for mock_whatsapp), with a Singapore number."""

    fixtures = ['sample_business_configurations', 'sample_whatsapp_configurations']

    def test_every_business_has_one_valid_connection(self):
        from .models import WhatsAppConfiguration

        businesses = BusinessConfiguration.objects.all()
        configs = WhatsAppConfiguration.objects.select_related('business')
        self.assertEqual(configs.count(), businesses.count())
        self.assertEqual({c.business_id for c in configs}, {b.pk for b in businesses})
        for config in configs:
            with self.subTest(business=config.business_id):
                config.full_clean()  # loaddata skips validation
                self.assertRegex(config.display_phone_number, r'^\+65 [89]\d{3} \d{4}$')
                self.assertEqual(config.verified_name, config.business.business_name)
                # Stored encrypted, read back as the plain dummy values mock_whatsapp uses.
                self.assertEqual(config.app_secret, f'dev-app-secret-{config.business_id}')
                self.assertEqual(config.access_token, f'dev-access-token-{config.business_id}')
        from django.db import connection

        with connection.cursor() as cursor:
            cursor.execute('SELECT app_secret FROM configuration_app_whatsappconfiguration')
            self.assertTrue(all(not value.startswith('dev-') for (value,) in cursor.fetchall()))


@override_settings(INTERNAL_API_KEY=TEST_INTERNAL_KEY)
class InternalWhatsAppSendAPITests(APITestCase):
    """POST /api/internal/whatsapp/<id>/send/: messaging-service's replies go out through here."""

    @classmethod
    def setUpTestData(cls):
        cls.cafe = BusinessConfiguration.objects.create(business_name='Café', location='Singapore')
        cls.florist = BusinessConfiguration.objects.create(business_name='Florist', location='Singapore')
        WhatsAppConfiguration.objects.create(
            business=cls.cafe, phone_number_id='106540352242922', access_token='EAAGtoken', app_secret=TEST_APP_SECRET
        )

    def send(self, data, business_id=None, key=TEST_INTERNAL_KEY):
        headers = {} if key is None else {INTERNAL_API_KEY_HEADER: key}
        url = reverse('internal:whatsapp-send', args=[business_id or self.cafe.pk])
        return self.client.post(url, data, format='json', headers=headers)

    @patch('configuration_app.meta_api.send_text_message', return_value='wamid.out1')
    def test_sends_with_the_stored_credentials(self, send):
        response = self.send({'to': '+6591234567', 'text': 'Hello!'})
        self.assertEqual((response.status_code, response.json()), (200, {'message_id': 'wamid.out1'}))
        send.assert_called_once_with('106540352242922', 'EAAGtoken', TEST_APP_SECRET, '+6591234567', 'Hello!')
        self.assertNotIn('EAAGtoken', response.content.decode())

    @patch('configuration_app.meta_api.send_text_message')
    def test_errors(self, send):
        self.assertEqual(self.send({'to': '+6591234567', 'text': 'Hi'}, key='wrong').status_code, 403)
        self.assertEqual(self.send({'to': '+6591234567', 'text': 'Hi'}, business_id=self.florist.pk).status_code, 404)
        self.assertEqual(self.send({'to': '91234567', 'text': 'Hi'}).status_code, 400)
        self.assertEqual(self.send({'to': '+6591234567', 'text': ''}).status_code, 400)
        send.side_effect = meta_api.MetaSendError('Meta refused the message (400): bad number')
        self.assertEqual(self.send({'to': '+6591234567', 'text': 'Hi'}).status_code, 502)
        send.side_effect = meta_api.MetaUnavailableError('Could not reach Meta')
        response = self.send({'to': '+6591234567', 'text': 'Hi'})
        self.assertEqual((response.status_code, response.json()), (503, {'detail': 'Could not reach Meta'}))


@override_settings(META_GRAPH_API_URL='https://graph.example/v25.0')
class SendTextMessageTests(SimpleTestCase):
    def send(self, status=200, body=None, error=None):
        self.requests = []

        def handler(request):
            self.requests.append(request)
            if error is not None:
                raise error
            return httpx.Response(status, json=body if body is not None else {
                'messaging_product': 'whatsapp', 'contacts': [{'input': '6591234567', 'wa_id': '6591234567'}],
                'messages': [{'id': 'wamid.out1'}],
            })

        return meta_api.send_text_message(
            '106540352242922', 'EAAGtoken', 'appsecret', '+6591234567', 'Hello!', transport=httpx.MockTransport(handler)
        )

    def test_request_in_metas_format(self):
        self.assertEqual(self.send(), 'wamid.out1')
        request = self.requests[0]
        url = urlsplit(str(request.url))
        self.assertEqual((request.method, f'{url.scheme}://{url.netloc}{url.path}'), ('POST', 'https://graph.example/v25.0/106540352242922/messages'))
        self.assertEqual(request.headers['Authorization'], 'Bearer EAAGtoken')
        self.assertEqual(parse_qs(url.query)['appsecret_proof'], [meta_api.appsecret_proof('EAAGtoken', 'appsecret')])
        self.assertEqual(json.loads(request.content), {
            'messaging_product': 'whatsapp', 'recipient_type': 'individual', 'to': '6591234567',
            'type': 'text', 'text': {'preview_url': False, 'body': 'Hello!'},
        })

    def test_errors(self):
        with self.assertRaises(meta_api.MetaSendError):
            self.send(400, {'error': {'message': 'Invalid parameter', 'code': 100}})
        for status, body in ((500, {'error': {'message': 'oops'}}), (429, {'error': {'message': 'slow down', 'code': 4}}), (200, {})):
            with self.subTest(status=status), self.assertRaises(meta_api.MetaUnavailableError):
                self.send(status, body)
        with self.assertRaises(meta_api.MetaUnavailableError):
            self.send(error=httpx.ConnectError('down'))
