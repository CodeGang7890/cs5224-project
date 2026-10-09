import hashlib
import hmac

from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.db import IntegrityError, connection, transaction
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APITestCase

from auth_app.models import BusinessUser

from . import crypto
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
            set(body), {'phone_number_id', 'webhook_url', 'verify_token', 'created_time', 'last_updated'}
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

