import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import httpx
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import SimpleTestCase, TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from auth_app.models import BusinessUser

from . import crypto, meta_api
from .models import (
    BUSINESS_NAME_MAX_LENGTH,
    DESCRIPTION_MAX_LENGTH,
    PHONE_NUMBER_TAKEN_MESSAGE,
    BusinessConfiguration,
    ConnectionHealth,
    WhatsAppConfiguration,
    WhatsAppConnectionMethod,
    WhatsAppConnectionStatus,
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

    @override_settings(META_APP_SECRET='our-app-secret')
    def test_embedded_signup_connections_are_signed_with_our_app_secret(self):
        create_whatsapp_config(self.florist, phone_number_id='222', waba_id='9', connection_method='embedded_signup')
        for secret, valid in (('our-app-secret', True), (TEST_APP_SECRET, False)):
            with self.subTest(secret=secret):
                response = self.verify_signature(TEST_PAYLOAD, meta_signature(TEST_PAYLOAD, secret), self.florist.pk)
                self.assertEqual(response.json()['valid'], valid)

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
META_INFO = meta_api.PhoneNumberInfo(display_phone_number='+65 9123 4567', verified_name='Café Pte Ltd')


def create_whatsapp_config(business, **overrides) -> WhatsAppConfiguration:
    values = {**VALID_WHATSAPP, **overrides}
    if values.get('connection_method') == WhatsAppConnectionMethod.EMBEDDED_SIGNUP:
        values['app_secret'] = overrides.get('app_secret', '')  # they use settings.META_APP_SECRET
    return WhatsAppConfiguration.objects.create(business=business, **values)


class WhatsAppConfigurationAPITests(APITestCase):
    """GET / DELETE /api/configuration/whatsapp/ (connecting is Embedded Signup's, below)."""

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

    def test_requires_authentication(self):
        for method in ('get', 'delete'):
            with self.subTest(method=method):
                self.assertEqual(getattr(self.client, method)(self.url).status_code, 401)

    def test_user_without_business_gets_403(self):
        self.client.force_authenticate(self.no_business_user)
        for method in ('get', 'delete'):
            with self.subTest(method=method):
                self.assertEqual(getattr(self.client, method)(self.url).status_code, 403)

    def test_other_methods_are_not_allowed(self):
        self.client.force_authenticate(self.cafe_user)
        for method in ('post', 'put', 'patch'):
            with self.subTest(method=method):
                response = getattr(self.client, method)(self.url, VALID_WHATSAPP, format='json')
                self.assertEqual(response.status_code, 405)
        self.assertFalse(WhatsAppConfiguration.objects.exists())

    def test_businesses_only_see_and_change_their_own(self):
        create_whatsapp_config(self.cafe)
        self.client.force_authenticate(self.florist_user)
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertEqual(self.client.delete(self.url).status_code, 404)
        self.assertTrue(WhatsAppConfiguration.objects.filter(business=self.cafe).exists())

    def test_get_before_connecting_is_404(self):
        self.client.force_authenticate(self.cafe_user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            response.json()['detail'], 'Your business has not connected WhatsApp yet. Connect it with Facebook.'
        )

    def test_get(self):
        create_whatsapp_config(self.cafe, display_phone_number='+65 9123 4567', verified_name='Café Pte Ltd')
        self.client.force_authenticate(self.cafe_user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(
            set(body),
            {'phone_number_id', 'display_phone_number', 'verified_name', 'waba_id', 'connection_method', 'status',
             'status_reason', 'status_updated_time', 'access_token_expires_time', 'health',
             'created_time', 'last_updated'},
        )
        self.assertEqual((body['access_token_expires_time'], body['health']), (None, 'ok'))
        self.assertEqual((body['status'], body['status_reason'], body['status_updated_time']), ('connected', '', None))
        self.assertEqual(
            (body['phone_number_id'], body['display_phone_number'], body['connection_method']),
            (TEST_PHONE_NUMBER_ID, '+65 9123 4567', 'manual'),
        )

    def test_get_says_when_to_reconnect(self):
        create_whatsapp_config(self.cafe, access_token_expires_time=timezone.now() + timedelta(days=3))
        self.client.force_authenticate(self.cafe_user)
        body = self.client.get(self.url).json()
        self.assertEqual(body['health'], 'expiring_soon')
        self.assertIsNotNone(body['access_token_expires_time'])

    def test_secrets_and_webhook_details_are_never_returned(self):
        config = create_whatsapp_config(self.cafe, two_step_pin='482913')
        self.client.force_authenticate(self.cafe_user)
        response = self.client.get(self.url)
        body = response.content.decode()
        for value in (TEST_ACCESS_TOKEN, TEST_APP_SECRET, '482913', config.verify_token, 'webhook'):
            self.assertNotIn(value, body)
        self.assertFalse({'access_token', 'app_secret', 'two_step_pin', 'verify_token'} & set(response.json()))

    def test_disconnect(self):
        create_whatsapp_config(self.cafe)
        self.client.force_authenticate(self.cafe_user)
        self.assertEqual(self.client.delete(self.url).status_code, 204)
        self.assertFalse(WhatsAppConfiguration.objects.exists())
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertEqual(self.client.delete(self.url).status_code, 404)
        self.assertTrue(BusinessConfiguration.objects.filter(pk=self.cafe.pk).exists())


class MyBusinessAPITests(APITestCase):
    """GET / PUT /api/configuration/business/: a new account creates its business, then edits it."""

    url = reverse('configuration_app:my-business')
    data = {'business_name': 'Mei Bakes', 'location': 'Tiong Bahru', 'description': 'Cakes to order.'}

    @classmethod
    def setUpTestData(cls):
        cls.new_user = BusinessUser.objects.create_user(username='mei', password='123')
        cls.cafe = BusinessConfiguration.objects.create(business_name='Café', location='Singapore')
        cls.cafe_user = BusinessUser.objects.create_user(username='cafe', password='123', business=cls.cafe)

    def test_requires_authentication(self):
        self.assertEqual(self.client.get(self.url).status_code, 401)
        self.assertEqual(self.client.put(self.url, self.data, format='json').status_code, 401)

    def test_a_new_account_creates_its_business(self):
        self.client.force_authenticate(self.new_user)
        self.assertEqual(self.client.get(self.url).status_code, 404)
        response = self.client.put(self.url, self.data, format='json')
        self.assertEqual(response.status_code, 201)
        business = BusinessConfiguration.objects.get(pk=response.json()['id'])
        self.assertEqual((business.business_name, business.location), ('Mei Bakes', 'Tiong Bahru'))
        self.new_user.refresh_from_db()
        self.assertEqual(self.new_user.business, business)
        self.assertEqual(self.client.get(self.url).json(), {'id': business.pk, **self.data})

    def test_then_updates_it(self):
        self.client.force_authenticate(self.cafe_user)
        response = self.client.put(self.url, {**self.data, 'business_name': 'Café Two'}, format='json')
        self.assertEqual(response.status_code, 200)
        self.cafe.refresh_from_db()
        self.assertEqual(self.cafe.business_name, 'Café Two')
        self.assertEqual(BusinessConfiguration.objects.count(), 1)

    def test_validation(self):
        self.client.force_authenticate(self.new_user)
        response = self.client.put(self.url, {'business_name': '', 'description': 'x' * (DESCRIPTION_MAX_LENGTH + 1)},
                                   format='json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(set(response.json()), {'business_name', 'location', 'description'})
        self.assertFalse(BusinessConfiguration.objects.exclude(pk=self.cafe.pk).exists())
        self.new_user.refresh_from_db()
        self.assertIsNone(self.new_user.business)

    def test_the_business_id_cannot_be_chosen(self):
        self.client.force_authenticate(self.new_user)
        response = self.client.put(self.url, {**self.data, 'id': self.cafe.pk}, format='json')
        self.assertEqual(response.status_code, 201)
        self.assertNotEqual(response.json()['id'], self.cafe.pk)


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

@override_settings(META_GRAPH_API_URL='https://graph.example/v26.0')
class MetaApiTests(SimpleTestCase):
    def check(self, status=200, body=None, error=None, raw=None):
        """Runs phone_number_info against a fake Meta; returns its result (or raises)."""
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

        return meta_api.phone_number_info('106540352242922', 'EAAGtoken', 'appsecret', transport=httpx.MockTransport(handler))

    @staticmethod
    def meta_error(code, message='Error', status=400):
        return {'status': status, 'body': {'error': {'message': message, 'type': 'OAuthException', 'code': code}}}

    def test_request(self):
        self.check()
        request = self.requests[0]
        url = urlsplit(str(request.url))
        self.assertEqual(f'{url.scheme}://{url.netloc}{url.path}', 'https://graph.example/v26.0/106540352242922')
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

    def test_refused_is_a_message_for_the_owner(self):
        for code, message in ((190, 'Error validating access token'), (100, 'Object with ID does not exist'),
                              (10, 'Application does not have permission')):
            with self.subTest(code=code), self.assertRaises(meta_api.MetaSignupError) as ctx:
                self.check(**self.meta_error(code, message))
            self.assertEqual(str(ctx.exception), f"Meta didn't give us access to this phone number: {message}")

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

    @override_settings(META_APP_SECRET='our-app-secret')
    @patch('configuration_app.meta_api.send_text_message', return_value='wamid.out2')
    def test_embedded_signup_connections_send_with_our_app_secret(self, send):
        create_whatsapp_config(self.florist, phone_number_id='222', waba_id='9', connection_method='embedded_signup')
        self.send({'to': '+6591234567', 'text': 'Hi'}, business_id=self.florist.pk)
        self.assertEqual(send.call_args.args[2], 'our-app-secret')

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


@override_settings(META_GRAPH_API_URL='https://graph.example/v26.0')
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
        self.assertEqual((request.method, f'{url.scheme}://{url.netloc}{url.path}'), ('POST', 'https://graph.example/v26.0/106540352242922/messages'))
        self.assertEqual(request.headers['Authorization'], 'Bearer EAAGtoken')
        self.assertEqual(parse_qs(url.query)['appsecret_proof'], [meta_api.appsecret_proof('EAAGtoken', 'appsecret')])
        self.assertEqual(json.loads(request.content), {
            'messaging_product': 'whatsapp', 'recipient_type': 'individual', 'to': '6591234567',
            'type': 'text', 'text': {'preview_url': False, 'body': 'Hello!'},
        })

    def test_errors(self):
        with self.assertRaises(meta_api.MetaSendError):
            self.send(400, {'error': {'message': 'Invalid parameter', 'code': 100}})
        for status, body in ((500, {'error': {'message': 'oops'}}), (429, {'error': {'message': 'slow down', 'code': 4}}),
                             (400, {'error': {'message': 'Spam rate limit hit', 'code': 131048}}), (200, {})):
            with self.subTest(status=status), self.assertRaises(meta_api.MetaUnavailableError):
                self.send(status, body)
        with self.assertRaises(meta_api.MetaUnavailableError):
            self.send(error=httpx.ConnectError('down'))



# --- WhatsApp Embedded Signup (embedded_signup.py, meta_api's signup calls) ----------------------

PLATFORM_APP_SECRET = 'platform-app-secret-0123456789abcdef'
SIGNUP_TOKEN = 'EAABusinessTokenFromSignup'
SIGNUP_WABA_ID = '524126980791429'
SIGNUP_PHONE_NUMBER_ID = '106540352242922'
SIGNUP_TOKEN_EXPIRES = datetime(2026, 12, 23, 6, 0, tzinfo=UTC)
SIGNUP_REQUEST = {'code': 'AQBhlXsct-code', 'waba_id': SIGNUP_WABA_ID, 'phone_number_id': SIGNUP_PHONE_NUMBER_ID}


@override_settings(
    META_GRAPH_API_URL='https://graph.example/v26.0', META_APP_ID='1147422487864729', META_APP_SECRET=PLATFORM_APP_SECRET
)
class EmbeddedSignupMetaApiTests(SimpleTestCase):
    def fake_meta(self, status=200, body=None):
        self.requests = []

        def handler(request):
            self.requests.append(request)
            return httpx.Response(status, json=body if body is not None else {'success': True})

        return httpx.MockTransport(handler)

    def last(self):
        request = self.requests[-1]
        url = urlsplit(str(request.url))
        return request, url.path, parse_qs(url.query)

    def test_exchange_code(self):
        body = {'access_token': SIGNUP_TOKEN, 'token_type': 'bearer', 'expires_in': 5184000}  # 60 days
        before = timezone.now()
        token = meta_api.exchange_code('the-code', transport=self.fake_meta(body=body))
        self.assertEqual(token.access_token, SIGNUP_TOKEN)
        self.assertTrue(before + timedelta(days=60) <= token.expires_time <= timezone.now() + timedelta(days=60))
        request, path, query = self.last()
        self.assertEqual(len(self.requests), 1)
        self.assertEqual((request.method, path), ('GET', '/v26.0/oauth/access_token'))
        self.assertEqual(
            query, {'client_id': ['1147422487864729'], 'client_secret': [PLATFORM_APP_SECRET], 'code': ['the-code']}
        )
        self.assertNotIn('Authorization', request.headers)

    def test_exchange_code_without_expires_in(self):
        token = meta_api.exchange_code('the-code', transport=self.fake_meta(body={'access_token': SIGNUP_TOKEN}))
        self.assertEqual(token, meta_api.BusinessToken(SIGNUP_TOKEN, None))  # unknown: no warning
        self.assertEqual(len(self.requests), 1)

    def test_exchange_code_refused(self):
        transport = self.fake_meta(400, {'error': {'message': 'This authorization code has expired.', 'code': 100}})
        with self.assertRaisesMessage(meta_api.MetaSignupError, meta_api.EXPIRED_CODE_MESSAGE):
            meta_api.exchange_code('old', transport=transport)

    def test_exchange_code_meta_down(self):
        with self.assertRaises(meta_api.MetaUnavailableError):
            meta_api.exchange_code('code', transport=self.fake_meta(503, {'error': {'message': 'down'}}))

    def test_register_phone_number(self):
        pin_set = meta_api.register_phone_number(SIGNUP_PHONE_NUMBER_ID, SIGNUP_TOKEN, PLATFORM_APP_SECRET, '123456',
                                                 transport=self.fake_meta())
        self.assertTrue(pin_set)
        request, path, query = self.last()
        self.assertEqual((request.method, path), ('POST', f'/v26.0/{SIGNUP_PHONE_NUMBER_ID}/register'))
        self.assertEqual(json.loads(request.content), {'messaging_product': 'whatsapp', 'pin': '123456'})
        self.assertEqual(request.headers['Authorization'], f'Bearer {SIGNUP_TOKEN}')
        self.assertEqual(query['appsecret_proof'], [meta_api.appsecret_proof(SIGNUP_TOKEN, PLATFORM_APP_SECRET)])

    def test_register_already_registered_number_is_fine(self):
        body = {'error': {'message': 'Two step verification PIN mismatch', 'code': meta_api.PIN_MISMATCH_ERROR_CODE}}
        with self.assertLogs('configuration_app.meta_api', 'INFO'):
            pin_set = meta_api.register_phone_number(
                '1', SIGNUP_TOKEN, PLATFORM_APP_SECRET, '123456', transport=self.fake_meta(400, body)
            )
        self.assertFalse(pin_set)

    def test_register_refused(self):
        body = {'error': {'message': 'Phone number not verified', 'code': 133010}}
        with self.assertRaisesMessage(meta_api.MetaSignupError, 'Phone number not verified'):
            meta_api.register_phone_number('1', SIGNUP_TOKEN, PLATFORM_APP_SECRET, '123456',
                                           transport=self.fake_meta(400, body))

    def test_subscribe_app(self):
        meta_api.subscribe_app(SIGNUP_WABA_ID, SIGNUP_TOKEN, PLATFORM_APP_SECRET, transport=self.fake_meta())
        request, path, _ = self.last()
        self.assertEqual((request.method, path), ('POST', f'/v26.0/{SIGNUP_WABA_ID}/subscribed_apps'))
        self.assertEqual(request.content, b'')

    def test_subscribe_app_with_override(self):
        meta_api.subscribe_app(SIGNUP_WABA_ID, SIGNUP_TOKEN, PLATFORM_APP_SECRET,
                               override_callback_uri='https://ingester.example/webhook/7', verify_token='vt',
                               transport=self.fake_meta())
        request, _, _ = self.last()
        self.assertEqual(
            json.loads(request.content), {'override_callback_uri': 'https://ingester.example/webhook/7', 'verify_token': 'vt'}
        )

    def test_subscribe_app_refused(self):
        body = {'error': {'message': 'Callback verification failed', 'code': 2200}}
        for status, response in ((400, body), (200, {'success': False})):
            with self.subTest(status=status), self.assertRaises(meta_api.MetaSignupError):
                meta_api.subscribe_app('1', SIGNUP_TOKEN, PLATFORM_APP_SECRET, transport=self.fake_meta(status, response))

    def test_unsubscribe_app(self):
        meta_api.unsubscribe_app(SIGNUP_WABA_ID, SIGNUP_TOKEN, PLATFORM_APP_SECRET, transport=self.fake_meta())
        request, path, _ = self.last()
        self.assertEqual((request.method, path), ('DELETE', f'/v26.0/{SIGNUP_WABA_ID}/subscribed_apps'))


@override_settings(
    MESSAGING_INGESTER_PUBLIC_URL='https://ingester.example', META_APP_ID='1147422487864729',
    META_APP_SECRET=PLATFORM_APP_SECRET,
)
class EmbeddedSignupAPITests(APITestCase):
    url = reverse('configuration_app:whatsapp-embedded-signup')
    whatsapp_url = reverse('configuration_app:whatsapp-configuration')

    @classmethod
    def setUpTestData(cls):
        cls.cafe = BusinessConfiguration.objects.create(business_name='Café', location='Singapore')
        cls.florist = BusinessConfiguration.objects.create(business_name='Florist', location='Singapore')
        cls.cafe_user = BusinessUser.objects.create_user(username='cafe', password='123', business=cls.cafe)
        cls.no_business_user = BusinessUser.objects.create_user(username='nobiz', password='123')

    def setUp(self):
        # Fake every Meta call (tests never call the real Meta).
        self.meta = {}
        for name, value in (
            ('exchange_code', meta_api.BusinessToken(SIGNUP_TOKEN, SIGNUP_TOKEN_EXPIRES)),
            ('phone_number_info', META_INFO),
            ('register_phone_number', True),
            ('subscribe_app', None),
            ('unsubscribe_app', None),
        ):
            patcher = patch.object(meta_api, name, return_value=value)
            self.meta[name] = patcher.start()
            self.addCleanup(patcher.stop)

    def connect(self, data=None, user=None):
        self.client.force_authenticate(user or self.cafe_user)
        return self.client.post(self.url, data or SIGNUP_REQUEST, format='json')

    def saved(self) -> WhatsAppConfiguration:
        return WhatsAppConfiguration.objects.get(business=self.cafe)

    def test_connects_and_sets_up_the_webhook(self):
        response = self.connect()
        self.assertEqual(response.status_code, 201)
        config = self.saved()
        self.assertEqual(
            (config.phone_number_id, config.access_token, config.waba_id, config.connection_method),
            (SIGNUP_PHONE_NUMBER_ID, SIGNUP_TOKEN, SIGNUP_WABA_ID, 'embedded_signup'),
        )
        # Our App Secret isn't copied into the connection: it's used from the settings.
        self.assertEqual((config.app_secret, config.effective_app_secret), ('', PLATFORM_APP_SECRET))
        self.assertEqual((config.display_phone_number, config.verified_name), ('+65 9123 4567', 'Café Pte Ltd'))
        self.assertEqual(config.access_token_expires_time, SIGNUP_TOKEN_EXPIRES)
        self.meta['exchange_code'].assert_called_once_with('AQBhlXsct-code')
        self.meta['phone_number_info'].assert_called_once_with(SIGNUP_PHONE_NUMBER_ID, SIGNUP_TOKEN, PLATFORM_APP_SECRET)
        pin = self.meta['register_phone_number'].call_args.args[3]
        self.assertRegex(pin, r'^\d{6}$')
        plain, override = self.meta['subscribe_app'].call_args_list
        self.assertEqual(plain.args, (SIGNUP_WABA_ID, SIGNUP_TOKEN, PLATFORM_APP_SECRET))
        self.assertEqual(
            override.kwargs,
            {'override_callback_uri': f'https://ingester.example/webhook/{self.cafe.pk}', 'verify_token': config.verify_token},
        )
        body = response.json()
        self.assertEqual((body['connection_method'], body['waba_id']), ('embedded_signup', SIGNUP_WABA_ID))
        self.assertEqual(body['access_token_expires_time'], '2026-12-23T06:00:00Z')
        self.assertNotIn('access_token', body)
        self.assertNotIn('app_secret', body)

    def test_replaces_a_manual_connection_keeping_the_verify_token(self):
        old = create_whatsapp_config(self.cafe, phone_number_id='999')
        response = self.connect()
        self.assertEqual(response.status_code, 200)
        config = self.saved()
        self.assertEqual((config.pk, config.verify_token), (old.pk, old.verify_token))
        self.assertEqual((config.phone_number_id, config.connection_method), (SIGNUP_PHONE_NUMBER_ID, 'embedded_signup'))
        self.meta['unsubscribe_app'].assert_not_called()

    def test_reconnecting_with_another_waba_unsubscribes_the_old_one(self):
        create_whatsapp_config(self.cafe, waba_id='111', connection_method='embedded_signup', access_token='old-token')
        self.connect()
        self.meta['unsubscribe_app'].assert_called_once_with('111', 'old-token', PLATFORM_APP_SECRET)

    def test_access(self):
        self.assertEqual(self.client.post(self.url, SIGNUP_REQUEST, format='json').status_code, 401)
        self.assertEqual(self.connect(user=self.no_business_user).status_code, 403)
        self.meta['exchange_code'].assert_not_called()

    @override_settings(META_APP_SECRET='')
    def test_not_configured_is_503(self):
        self.assertEqual(self.connect().status_code, 503)
        self.meta['exchange_code'].assert_not_called()

    def test_validates_the_request(self):
        response = self.connect({'code': '', 'waba_id': '12a', 'phone_number_id': ''})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(set(response.json()), {'code', 'waba_id', 'phone_number_id'})
        self.meta['exchange_code'].assert_not_called()

    def test_meta_refusing_a_step_is_400_and_saves_nothing(self):
        self.meta['exchange_code'].side_effect = meta_api.MetaSignupError(meta_api.EXPIRED_CODE_MESSAGE)
        response = self.connect()
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {'non_field_errors': [meta_api.EXPIRED_CODE_MESSAGE]})
        self.assertFalse(WhatsAppConfiguration.objects.exists())

    def test_number_meta_does_not_give_access_to_is_400(self):
        self.meta['phone_number_info'].side_effect = meta_api.MetaSignupError(
            "Meta didn't give us access to this phone number: Unknown number."
        )
        response = self.connect()
        self.assertEqual(response.status_code, 400)
        self.assertIn('Unknown number.', response.json()['non_field_errors'][0])
        self.meta['register_phone_number'].assert_not_called()

    def test_meta_unavailable_is_503(self):
        self.meta['register_phone_number'].side_effect = meta_api.MetaUnavailableError('timeout')
        self.assertEqual(self.connect().status_code, 503)
        self.assertFalse(WhatsAppConfiguration.objects.exists())

    def test_number_of_another_business_is_400(self):
        create_whatsapp_config(self.florist, phone_number_id=SIGNUP_PHONE_NUMBER_ID)
        response = self.connect()
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {'phone_number_id': [PHONE_NUMBER_TAKEN_MESSAGE]})
        self.meta['register_phone_number'].assert_not_called()
        self.assertFalse(WhatsAppConfiguration.objects.filter(business=self.cafe).exists())

    def test_webhook_failure_removes_a_new_connection(self):
        self.meta['subscribe_app'].side_effect = [None, meta_api.MetaSignupError('Callback verification failed')]
        response = self.connect()
        self.assertEqual(response.status_code, 400)
        self.assertFalse(WhatsAppConfiguration.objects.exists())

    def test_webhook_failure_restores_the_previous_connection(self):
        create_whatsapp_config(self.cafe, phone_number_id='999', display_phone_number='+65 8000 0000')
        self.meta['subscribe_app'].side_effect = meta_api.MetaUnavailableError('timeout')
        self.assertEqual(self.connect().status_code, 503)
        config = self.saved()
        self.assertEqual(
            (config.phone_number_id, config.access_token, config.app_secret, config.connection_method, config.waba_id),
            ('999', TEST_ACCESS_TOKEN, TEST_APP_SECRET, 'manual', ''),
        )
        self.assertEqual(config.display_phone_number, '+65 8000 0000')

    def test_disconnecting_unsubscribes_embedded_signup_connections(self):
        self.connect()
        self.assertEqual(self.client.delete(self.whatsapp_url).status_code, 204)
        self.meta['unsubscribe_app'].assert_called_once_with(SIGNUP_WABA_ID, SIGNUP_TOKEN, PLATFORM_APP_SECRET)
        self.assertFalse(WhatsAppConfiguration.objects.exists())

    def test_disconnecting_still_works_when_meta_refuses_to_unsubscribe(self):
        self.connect()
        self.meta['unsubscribe_app'].side_effect = meta_api.MetaUnavailableError('timeout')
        self.assertEqual(self.client.delete(self.whatsapp_url).status_code, 204)
        self.assertFalse(WhatsAppConfiguration.objects.exists())

    def test_disconnecting_a_manual_connection_does_not_call_meta(self):
        create_whatsapp_config(self.cafe)
        self.client.force_authenticate(self.cafe_user)
        self.assertEqual(self.client.delete(self.whatsapp_url).status_code, 204)
        self.meta['unsubscribe_app'].assert_not_called()

    def test_two_step_pin_is_saved_encrypted(self):
        self.connect()
        pin = self.meta['register_phone_number'].call_args.args[3]
        config = self.saved()
        self.assertEqual(config.two_step_pin, pin)
        with connection.cursor() as cursor:
            cursor.execute('SELECT two_step_pin FROM configuration_app_whatsappconfiguration WHERE id = %s', [config.pk])
            self.assertNotIn(pin, cursor.fetchone()[0])

    def test_number_already_registered_with_an_unknown_pin(self):
        self.meta['register_phone_number'].return_value = False
        self.connect()
        self.assertEqual(self.saved().two_step_pin, '')

    def test_reconnecting_the_same_number_keeps_its_known_pin(self):
        self.connect()
        pin = self.saved().two_step_pin
        self.meta['register_phone_number'].return_value = False  # registered with that PIN: Meta refuses a new one
        self.assertEqual(self.connect().status_code, 200)
        self.assertEqual(self.saved().two_step_pin, pin)

    def test_reconnecting_clears_what_meta_reported(self):
        create_whatsapp_config(
            self.cafe, waba_id=SIGNUP_WABA_ID, connection_method='embedded_signup', status='disconnected',
            status_updated_time=timezone.now(),
        )
        self.assertEqual(self.connect().status_code, 200)
        config = self.saved()
        self.assertEqual((config.status, config.status_updated_time), ('connected', None))

    def test_reconnecting_renews_the_token_and_its_expiry(self):
        create_whatsapp_config(
            self.cafe, phone_number_id=SIGNUP_PHONE_NUMBER_ID, waba_id=SIGNUP_WABA_ID, connection_method='embedded_signup',
            access_token='old-token', access_token_expires_time=timezone.now() - timedelta(days=1),
        )
        self.assertEqual(self.connect().status_code, 200)
        config = self.saved()
        self.assertEqual((config.access_token, config.access_token_expires_time), (SIGNUP_TOKEN, SIGNUP_TOKEN_EXPIRES))
        self.meta['unsubscribe_app'].assert_not_called()  # same WABA

    def test_webhook_failure_restores_the_previous_expiry(self):
        expires = timezone.now() + timedelta(days=2)
        create_whatsapp_config(self.cafe, access_token_expires_time=expires)
        self.meta['subscribe_app'].side_effect = meta_api.MetaUnavailableError('timeout')
        self.assertEqual(self.connect().status_code, 503)
        self.assertEqual(self.saved().access_token_expires_time, expires)



class ConnectionHealthTests(SimpleTestCase):
    NOW = datetime(2026, 10, 24, 12, 0, tzinfo=UTC)

    def health(self, expires, status='connected'):
        return WhatsAppConfiguration(access_token_expires_time=expires, status=status).health(now=self.NOW)

    def test_the_token_s_expiry(self):
        for expires, health in (
            (None, ConnectionHealth.OK),  # never expires (or unknown, e.g. manual connections)
            (self.NOW + timedelta(days=30), ConnectionHealth.OK),
            (self.NOW + timedelta(days=7, seconds=1), ConnectionHealth.OK),
            (self.NOW + timedelta(days=7), ConnectionHealth.EXPIRING_SOON),
            (self.NOW + timedelta(minutes=1), ConnectionHealth.EXPIRING_SOON),
            (self.NOW, ConnectionHealth.EXPIRED),
            (self.NOW - timedelta(days=1), ConnectionHealth.EXPIRED),
        ):
            with self.subTest(expires=expires):
                self.assertEqual(self.health(expires), health)

    def test_what_meta_reported_comes_first(self):
        for status in ('disconnected', 'banned'):
            with self.subTest(status=status):
                self.assertEqual(self.health(self.NOW - timedelta(days=1), status), status)
                self.assertEqual(self.health(None, status), status)


class EmbeddedSignupModelTests(TestCase):
    def test_embedded_signup_needs_a_waba_id(self):
        cafe = BusinessConfiguration.objects.create(business_name='Café', location='Singapore')
        with self.assertRaises(IntegrityError), transaction.atomic():
            create_whatsapp_config(cafe, connection_method=WhatsAppConnectionMethod.EMBEDDED_SIGNUP)

    def test_status_must_be_known(self):
        cafe = BusinessConfiguration.objects.create(business_name='Café', location='Singapore')
        with self.assertRaises(IntegrityError), transaction.atomic():
            create_whatsapp_config(cafe, status='suspended')
        self.assertEqual(create_whatsapp_config(cafe).status, WhatsAppConnectionStatus.CONNECTED)

    def test_only_manual_connections_store_an_app_secret(self):
        cafe = BusinessConfiguration.objects.create(business_name='Café', location='Singapore')
        for overrides in ({'app_secret': ''}, {'connection_method': 'embedded_signup', 'waba_id': '1', 'app_secret': 'x'}):
            with self.subTest(overrides=overrides), self.assertRaises(IntegrityError), transaction.atomic():
                create_whatsapp_config(cafe, **overrides)

    @override_settings(META_APP_SECRET='ours')
    def test_effective_app_secret(self):
        self.assertEqual(WhatsAppConfiguration(app_secret='theirs').effective_app_secret, 'theirs')
        embedded = WhatsAppConfiguration(connection_method='embedded_signup', app_secret='')
        self.assertEqual(embedded.effective_app_secret, 'ours')

    def test_connection_method_must_be_known(self):
        cafe = BusinessConfiguration.objects.create(business_name='Café', location='Singapore')
        with self.assertRaises(IntegrityError), transaction.atomic():
            create_whatsapp_config(cafe, connection_method='carrier_pigeon')


@override_settings(
    INTERNAL_API_KEY=TEST_INTERNAL_KEY, META_APP_SECRET=TEST_APP_SECRET, META_APP_WEBHOOK_VERIFY_TOKEN='app-verify-token'
)
class InternalWhatsAppAppWebhookAPITests(APITestCase):
    """Our Meta app's default webhook (messaging-ingester's /webhook): handshake and signature checks."""

    def post(self, name, key=TEST_INTERNAL_KEY, **kwargs):
        headers = {INTERNAL_API_KEY_HEADER: key, **kwargs.pop('headers', {})}
        return self.client.post(reverse(f'internal:whatsapp-app-{name}'), headers=headers, **kwargs)

    def test_verify_token(self):
        for token, valid in (('app-verify-token', True), ('wrong', False), ('', False)):
            with self.subTest(token=token):
                response = self.post('verify-token', data={'verify_token': token}, format='json')
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json(), {'valid': valid, 'phone_number_id': None})

    def test_verify_signature(self):
        for signature, valid in ((meta_signature(TEST_PAYLOAD), True), (meta_signature(TEST_PAYLOAD, 'other'), False)):
            with self.subTest(valid=valid):
                response = self.post(
                    'verify-signature', data=TEST_PAYLOAD, content_type='application/octet-stream',
                    headers={SIGNATURE_HEADER: signature},
                )
                self.assertEqual(response.json(), {'valid': valid, 'phone_number_id': None})

    def test_requires_the_internal_api_key(self):
        response = self.post('verify-token', key='wrong', data={'verify_token': 'app-verify-token'}, format='json')
        self.assertEqual(response.status_code, 403)

    @override_settings(META_APP_SECRET='', META_APP_WEBHOOK_VERIFY_TOKEN='')
    def test_not_configured_is_404(self):
        self.assertEqual(self.post('verify-token', data={'verify_token': 'x'}, format='json').status_code, 404)
        response = self.post(
            'verify-signature', data=TEST_PAYLOAD, content_type='application/octet-stream',
            headers={SIGNATURE_HEADER: meta_signature(TEST_PAYLOAD)},
        )
        self.assertEqual(response.status_code, 404)


@override_settings(INTERNAL_API_KEY=TEST_INTERNAL_KEY, META_APP_ID='1147422487864729')
class InternalWhatsAppAccountUpdatesAPITests(APITestCase):
    """Meta's account_update events (our app's webhook, forwarded by messaging-ingester) → connection status."""

    url = reverse('internal:whatsapp-app-account-updates')

    @classmethod
    def setUpTestData(cls):
        cls.cafe = BusinessConfiguration.objects.create(business_name='Café', location='Singapore')
        cls.florist = BusinessConfiguration.objects.create(business_name='Florist', location='Singapore')
        cls.bakery = BusinessConfiguration.objects.create(business_name='Bakery', location='Singapore')
        cls.cafe_user = BusinessUser.objects.create_user(username='cafe', password='123', business=cls.cafe)
        cls.cafe_config = create_whatsapp_config(cls.cafe, waba_id='111', connection_method='embedded_signup')
        cls.florist_config = create_whatsapp_config(
            cls.florist, phone_number_id='222', waba_id='222', connection_method='embedded_signup'
        )
        cls.manual_config = create_whatsapp_config(cls.bakery, phone_number_id='333')  # no WABA: never matched

    def report(self, *updates, key=TEST_INTERNAL_KEY):
        return self.client.post(
            self.url, {'updates': list(updates)}, format='json', headers={INTERNAL_API_KEY_HEADER: key}
        )

    def status(self, config=None):
        return WhatsAppConfiguration.objects.get(pk=(config or self.cafe_config).pk).status

    def test_disconnecting_events(self):
        for event in ('PARTNER_APP_UNINSTALLED', 'PARTNER_REMOVED', 'ACCOUNT_DELETED', 'ACCOUNT_OFFBOARDED'):
            with self.subTest(event=event):
                WhatsAppConfiguration.objects.update(status='connected')
                with self.assertLogs('configuration_app.account_updates', 'INFO'):
                    response = self.report({'waba_id': '111', 'event': event})
                self.assertEqual((response.status_code, response.json()), (200, {'changed': 1}))
                self.assertEqual(self.status(), 'disconnected')
                self.assertEqual(self.status(self.florist_config), 'connected')
                self.assertEqual(self.status(self.manual_config), 'connected')

    def test_our_app_uninstalled(self):
        with self.assertLogs('configuration_app.account_updates', 'INFO'):
            response = self.report(
                {'waba_id': '111', 'event': 'PARTNER_APP_UNINSTALLED', 'partner_app_id': '999'},  # another app
                {'waba_id': '222', 'event': 'PARTNER_APP_UNINSTALLED', 'partner_app_id': '1147422487864729'},
            )
        self.assertEqual(response.json(), {'changed': 1})
        self.assertEqual(self.status(), 'connected')
        self.assertEqual(self.status(self.florist_config), 'disconnected')
        self.assertIsNotNone(WhatsAppConfiguration.objects.get(pk=self.florist_config.pk).status_updated_time)

    def test_banned(self):
        banned = {'waba_id': '111', 'event': 'DISABLED_UPDATE', 'ban_state': 'DISABLE'}
        with self.assertLogs('configuration_app.account_updates', 'INFO'):
            self.report({**banned, 'ban_state': 'SCHEDULE_FOR_DISABLE'})  # only scheduled: nothing yet
            self.assertEqual(self.status(), 'connected')
            self.assertEqual(self.report(banned).json(), {'changed': 1})
            self.assertEqual(self.status(), 'banned')

    def test_nothing_sets_it_back_automatically(self):
        WhatsAppConfiguration.objects.filter(pk=self.cafe_config.pk).update(status='banned')
        with self.assertLogs('configuration_app.account_updates', 'INFO'):
            response = self.report({'waba_id': '111', 'event': 'DISABLED_UPDATE', 'ban_state': 'REINSTATE'},
                                   {'waba_id': '111', 'event': 'ACCOUNT_RECONNECTED'})
        self.assertEqual(response.json(), {'changed': 0})
        self.assertEqual(self.status(), 'banned')  # reconnecting with Facebook resets it

    def test_redelivered_and_other_events_change_nothing(self):
        uninstalled = {'waba_id': '111', 'event': 'PARTNER_APP_UNINSTALLED'}
        with self.assertLogs('configuration_app.account_updates', 'INFO'):
            self.assertEqual(self.report(uninstalled).json(), {'changed': 1})
            self.assertEqual(self.report(uninstalled).json(), {'changed': 0})  # Meta redelivered it
            response = self.report(
                {'waba_id': '222', 'event': 'ACCOUNT_VIOLATION'},
                {'waba_id': '222', 'event': 'PARTNER_APP_INSTALLED'},
                {'waba_id': '555', 'event': 'ACCOUNT_DELETED'},  # not connected here
            )
        self.assertEqual(response.json(), {'changed': 0})
        self.assertEqual(self.status(self.florist_config), 'connected')

    def test_the_owner_sees_why(self):
        with self.assertLogs('configuration_app.account_updates', 'INFO'):
            self.report({'waba_id': '111', 'event': 'DISABLED_UPDATE', 'ban_state': 'DISABLE'})
        self.client.force_authenticate(self.cafe_user)
        body = self.client.get(reverse('configuration_app:whatsapp-configuration')).json()
        self.assertEqual((body['status'], body['health']), ('banned', 'banned'))
        self.assertIn('Meta disabled your WhatsApp Business account', body['status_reason'])
        self.assertIsNotNone(body['status_updated_time'])

    def test_access_and_validation(self):
        self.assertEqual(self.report({'waba_id': '111', 'event': 'ACCOUNT_DELETED'}, key='wrong').status_code, 403)
        response = self.report({'waba_id': 'not-digits', 'event': ''})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.status(), 'connected')


class ConnectionStatusModelTests(SimpleTestCase):
    def test_status_reason(self):
        self.assertEqual(WhatsAppConfiguration(status='connected').status_reason, '')
        self.assertIn('disconnected from us', WhatsAppConfiguration(status='disconnected').status_reason)
        self.assertIn('Meta disabled', WhatsAppConfiguration(status='banned').status_reason)


class AppSecretMigrationTests(TransactionTestCase):
    """configuration_app 0008–0009: Embedded Signup connections stop storing a copy of our App Secret."""

    before = [('configuration_app', '0007_whatsappconfiguration_access_token_expires_time')]
    after = [('configuration_app', '0009_whatsappconfiguration_app_secret_constraints')]

    def migrate(self, targets):
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(targets)
        return executor.loader.project_state(targets).apps

    def tearDown(self):
        self.migrate(MigrationExecutor(connection).loader.graph.leaf_nodes())

    @override_settings(META_APP_SECRET=PLATFORM_APP_SECRET)
    def test_copies_are_dropped_and_restored(self):
        apps = self.migrate(self.before)
        Business = apps.get_model('configuration_app', 'BusinessConfiguration')
        Old = apps.get_model('configuration_app', 'WhatsAppConfiguration')
        common = {'access_token': 'token', 'verify_token': 'vt'}
        Old.objects.create(business=Business.objects.create(business_name='A', location='SG'), phone_number_id='1',
                           app_secret='their-own', **common)
        Old.objects.create(business=Business.objects.create(business_name='B', location='SG'), phone_number_id='2',
                           app_secret=PLATFORM_APP_SECRET, connection_method='embedded_signup', waba_id='9', **common)

        apps = self.migrate(self.after)
        secrets = dict(apps.get_model('configuration_app', 'WhatsAppConfiguration').objects.values_list('phone_number_id', 'app_secret'))
        self.assertEqual(secrets, {'1': 'their-own', '2': ''})

        apps = self.migrate(self.before)  # reversible: the copy comes back from the settings
        secrets = dict(apps.get_model('configuration_app', 'WhatsAppConfiguration').objects.values_list('phone_number_id', 'app_secret'))
        self.assertEqual(secrets, {'1': 'their-own', '2': PLATFORM_APP_SECRET})

