from unittest.mock import patch

import google.auth.exceptions
from django.core.cache import cache
from django.test import SimpleTestCase, override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from configuration_app.models import BusinessConfiguration

from . import firebase
from .accounts import unique_username
from .models import BusinessUser
from .serializers import EMAIL_TAKEN_MESSAGE, USERNAME_TAKEN_MESSAGE


class RateLimitResetMixin:
    """The login / sign-up rate limits count in the cache, which lasts the whole test run: start empty."""

    def setUp(self):
        super().setUp()
        cache.clear()


class AuthAPITests(RateLimitResetMixin, APITestCase):
    login_url = reverse('auth_app:token-obtain')
    refresh_url = reverse('auth_app:token-refresh')
    verify_url = reverse('auth_app:token-verify')
    logout_url = reverse('auth_app:logout')
    me_url = reverse('auth_app:me')

    @classmethod
    def setUpTestData(cls):
        cls.business = BusinessConfiguration.objects.create(business_name='Café', location='Singapore')
        cls.user = BusinessUser.objects.create_user(
            username='cafe',
            password='123',
            email='cafe@example.com',
            first_name='Ada',
            last_name='Tan',
            business=cls.business,
        )

    def login(self, username='cafe', password='123'):
        return self.client.post(self.login_url, {'username': username, 'password': password}, format='json')

    def bearer(self, access):
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {access}')

    # --- Login ----------------------------------------------------------------------

    def test_login_returns_access_and_refresh_tokens(self):
        response = self.login()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(set(response.data), {'access', 'refresh'})

    def test_login_updates_last_login(self):
        self.login()
        self.user.refresh_from_db()
        self.assertIsNotNone(self.user.last_login)

    def test_login_with_wrong_password_fails(self):
        response = self.login(password='wrong')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertNotIn('access', response.data)

    def test_login_inactive_user_fails(self):
        BusinessUser.objects.create_user(username='gone', password='123', is_active=False)
        self.assertEqual(self.login(username='gone').status_code, status.HTTP_401_UNAUTHORIZED)

    def test_login_is_rate_limited_per_client(self):
        for _ in range(30):  # DJANGO_LOGIN_RATE: 30/minute
            self.assertEqual(self.login(password='wrong').status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(self.login().status_code, 429)  # even the right password, for now
        with patch.object(firebase, 'verify_id_token', return_value=firebase.FirebaseIdentity('u', '', '', 'google.com')):
            self.assertEqual(
                self.client.post(reverse('auth_app:firebase-login'), {'id_token': 'x'}, format='json').status_code, 429
            )

    def test_login_requires_username_and_password(self):
        response = self.client.post(self.login_url, {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(set(response.data), {'username', 'password'})

    # --- Using the access token -----------------------------------------------------

    def test_access_token_authenticates_api_requests(self):
        self.bearer(self.login().data['access'])
        self.assertEqual(self.client.get(reverse('product_app:product-list')).status_code, status.HTTP_200_OK)

    def test_invalid_access_token_rejected(self):
        self.bearer('not-a-token')
        response = self.client.get(self.me_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data['code'], 'token_not_valid')

    def test_refresh_token_cannot_be_used_as_access_token(self):
        self.bearer(self.login().data['refresh'])
        self.assertEqual(self.client.get(self.me_url).status_code, status.HTTP_401_UNAUTHORIZED)

    # --- Refresh / verify -----------------------------------------------------------

    def test_refresh_returns_new_tokens_and_rotates(self):
        old_refresh = self.login().data['refresh']
        response = self.client.post(self.refresh_url, {'refresh': old_refresh}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(set(response.data), {'access', 'refresh'})
        self.assertNotEqual(response.data['refresh'], old_refresh)

        # The new access token works...
        self.bearer(response.data['access'])
        self.assertEqual(self.client.get(self.me_url).status_code, status.HTTP_200_OK)
        # ...and the old refresh token is now blacklisted.
        self.client.credentials()
        reuse = self.client.post(self.refresh_url, {'refresh': old_refresh}, format='json')
        self.assertEqual(reuse.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_refresh_with_invalid_token_fails(self):
        response = self.client.post(self.refresh_url, {'refresh': 'garbage'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_verify(self):
        access = self.login().data['access']
        self.assertEqual(
            self.client.post(self.verify_url, {'token': access}, format='json').status_code, status.HTTP_200_OK
        )
        self.assertEqual(
            self.client.post(self.verify_url, {'token': 'garbage'}, format='json').status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    # --- Logout ---------------------------------------------------------------------

    def test_logout_blacklists_refresh_token(self):
        refresh = self.login().data['refresh']
        response = self.client.post(self.logout_url, {'refresh': refresh}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        reuse = self.client.post(self.refresh_url, {'refresh': refresh}, format='json')
        self.assertEqual(reuse.status_code, status.HTTP_401_UNAUTHORIZED)

    # --- Me -------------------------------------------------------------------------

    def test_me_requires_authentication(self):
        self.assertEqual(self.client.get(self.me_url).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_me_returns_profile_with_business_id(self):
        self.bearer(self.login().data['access'])
        response = self.client.get(self.me_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data,
            {
                'id': self.user.pk,
                'username': 'cafe',
                'email': 'cafe@example.com',
                'first_name': 'Ada',
                'last_name': 'Tan',
                'business': self.business.pk,
                'business_name': 'Café',
                'is_staff': False,
                'is_superuser': False,
            },
        )
        self.assertNotIn('password', response.data)

    def test_me_for_user_without_business(self):
        admin = BusinessUser.objects.create_superuser(username='admin', password='123')
        self.client.force_authenticate(admin)
        response = self.client.get(self.me_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(response.data['business'])
        self.assertIsNone(response.data['business_name'])
        self.assertTrue(response.data['is_superuser'])

    def test_me_is_read_only(self):
        self.client.force_authenticate(self.user)
        self.assertEqual(
            self.client.patch(self.me_url, {'username': 'hacked'}, format='json').status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    def test_frontend_origin_can_send_authorization_header(self):
        response = self.client.options(
            self.me_url,
            headers={
                'Origin': 'http://localhost:5173',
                'Access-Control-Request-Method': 'GET',
                'Access-Control-Request-Headers': 'authorization',
            },
        )
        self.assertEqual(response.headers.get('Access-Control-Allow-Origin'), 'http://localhost:5173')
        self.assertIn('authorization', response.headers.get('Access-Control-Allow-Headers', ''))


class SignUpAPITests(RateLimitResetMixin, APITestCase):
    url = reverse('auth_app:signup')
    me_url = reverse('auth_app:me')
    valid = {'username': 'mei', 'email': 'mei@example.com', 'password': 'gentle-otter-42', 'first_name': 'Mei'}

    def test_signs_up_and_logs_in(self):
        response = self.client.post(self.url, self.valid, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(set(response.data), {'access', 'refresh'})
        user = BusinessUser.objects.get(username='mei')
        self.assertTrue(user.check_password('gentle-otter-42'))
        self.assertEqual((user.email, user.first_name, user.business, user.is_staff), ('mei@example.com', 'Mei', None, False))
        self.assertIsNotNone(user.last_login)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {response.data["access"]}')
        me = self.client.get(self.me_url).data
        self.assertEqual((me['username'], me['business']), ('mei', None))

    def test_username_and_email_must_be_free(self):
        BusinessUser.objects.create_user(username='Mei', email='MEI@example.com', password='x')
        response = self.client.post(self.url, self.valid, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['username'], [USERNAME_TAKEN_MESSAGE])
        self.assertEqual(response.data['email'], [EMAIL_TAKEN_MESSAGE])

    def test_password_rules(self):
        for password in ('123', 'password', 'mei@example.com'):
            with self.subTest(password=password):
                response = self.client.post(self.url, {**self.valid, 'password': password}, format='json')
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn('password', response.data)
        self.assertFalse(BusinessUser.objects.exists())

    def test_required_fields(self):
        response = self.client.post(self.url, {'username': 'bad name!'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(set(response.data), {'username', 'email', 'password'})

    def test_rate_limited_per_client(self):
        for _ in range(20):  # DJANGO_SIGNUP_RATE: 20/hour (invalid requests count too)
            self.assertEqual(self.client.post(self.url, {}, format='json').status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.client.post(self.url, self.valid, format='json').status_code, 429)
        self.assertFalse(BusinessUser.objects.exists())

    def test_works_while_logged_in_as_someone_else(self):
        self.client.force_authenticate(BusinessUser.objects.create_user(username='other', password='x'))
        self.assertEqual(self.client.post(self.url, self.valid, format='json').status_code, status.HTTP_201_CREATED)


GOOGLE = firebase.FirebaseIdentity(uid='google-uid-1', email='ada@example.com', name='Ada Tan Wei', provider='google.com')
FACEBOOK = firebase.FirebaseIdentity(uid='facebook-uid-1', email='ada@example.com', name='Ada Tan', provider='facebook.com')


class FirebaseLoginAPITests(RateLimitResetMixin, APITestCase):
    url = reverse('auth_app:firebase-login')

    def login(self, identity=GOOGLE):
        with patch.object(firebase, 'verify_id_token', return_value=identity) as verify:
            response = self.client.post(self.url, {'id_token': 'the-id-token'}, format='json')
        verify.assert_called_once_with('the-id-token')
        return response

    def test_first_login_creates_an_account_without_a_business(self):
        response = self.login()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(set(response.data), {'access', 'refresh', 'created'})
        self.assertTrue(response.data['created'])
        user = BusinessUser.objects.get(firebase_uid='google-uid-1')
        self.assertEqual(
            (user.username, user.email, user.first_name, user.last_name, user.business),
            ('ada', 'ada@example.com', 'Ada', 'Tan Wei', None),
        )
        self.assertFalse(user.has_usable_password())
        self.assertIsNotNone(user.last_login)

    def test_later_logins_use_the_same_account(self):
        self.login()
        response = self.login()
        self.assertFalse(response.data['created'])
        self.assertEqual(BusinessUser.objects.count(), 1)

    def test_never_attached_to_an_existing_account_with_the_same_email(self):
        business = BusinessConfiguration.objects.create(business_name='Café', location='Singapore')
        owner = BusinessUser.objects.create_user(username='ada', password='123', email='ADA@example.com', business=business)
        for identity, username in ((GOOGLE, 'ada2'), (FACEBOOK, 'ada3')):
            with self.subTest(provider=identity.provider):
                self.assertTrue(self.login(identity).data['created'])
                self.assertEqual(BusinessUser.objects.get(firebase_uid=identity.uid).username, username)
        owner.refresh_from_db()
        self.assertIsNone(owner.firebase_uid)

    def test_disabled_account_is_401(self):
        BusinessUser.objects.create_user(username='gone', password='x', firebase_uid='google-uid-1', is_active=False)
        self.assertEqual(self.login().status_code, status.HTTP_401_UNAUTHORIZED)

    def test_invalid_token_is_401(self):
        with patch.object(firebase, 'verify_id_token', side_effect=firebase.InvalidFirebaseToken('expired')):
            response = self.client.post(self.url, {'id_token': 'old'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertFalse(BusinessUser.objects.exists())

    def test_not_configured_or_google_down_is_503(self):
        for error in (firebase.FirebaseNotConfigured(), firebase.FirebaseUnavailable('timeout')):
            with self.subTest(error=type(error).__name__), patch.object(firebase, 'verify_id_token', side_effect=error):
                response = self.client.post(self.url, {'id_token': 'x'}, format='json')
                self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)

    def test_requires_a_token(self):
        self.assertEqual(self.client.post(self.url, {}, format='json').status_code, status.HTTP_400_BAD_REQUEST)


CLAIMS = {
    'iss': 'https://securetoken.google.com/ansera-test',
    'aud': 'ansera-test',
    'sub': 'google-uid-1',
    'email': 'ada@example.com',
    'email_verified': True,
    'name': 'Ada Tan',
    'firebase': {'sign_in_provider': 'google.com', 'identities': {}},
}


@override_settings(FIREBASE_PROJECT_ID='ansera-test')
class VerifyIdTokenTests(SimpleTestCase):
    """firebase.verify_id_token, with google-auth's check patched (never calls Google)."""

    def verify(self, claims=None, error=None):
        with patch('auth_app.firebase.id_token.verify_firebase_token', return_value=claims, side_effect=error) as check:
            identity = firebase.verify_id_token('the-token')
        self.assertEqual(check.call_args.args[0], 'the-token')
        self.assertEqual(check.call_args.kwargs, {'audience': 'ansera-test'})
        return identity

    def test_valid(self):
        self.assertEqual(self.verify(CLAIMS), firebase.FirebaseIdentity('google-uid-1', 'ada@example.com', 'Ada Tan', 'google.com'))

    def test_without_email_or_name(self):
        identity = self.verify({**CLAIMS, 'email': None, 'name': None})
        self.assertEqual((identity.email, identity.name), ('', ''))

    def test_rejected(self):
        for claims in (
            {**CLAIMS, 'iss': 'https://securetoken.google.com/another-project'},
            {**CLAIMS, 'sub': ''},
            {**CLAIMS, 'firebase': {'sign_in_provider': 'password'}},
            {**CLAIMS, 'firebase': {'sign_in_provider': 'anonymous'}},
        ):
            with self.subTest(claims=claims), self.assertRaises(firebase.InvalidFirebaseToken):
                self.verify(claims)
        with self.assertRaises(firebase.InvalidFirebaseToken):
            self.verify(error=ValueError('Token expired'))

    def test_google_unreachable(self):
        with self.assertRaises(firebase.FirebaseUnavailable):
            self.verify(error=google.auth.exceptions.TransportError('timeout'))

    @override_settings(FIREBASE_PROJECT_ID='')
    def test_not_configured(self):
        with self.assertRaises(firebase.FirebaseNotConfigured):
            firebase.verify_id_token('the-token')


class UniqueUsernameTests(APITestCase):
    def test_usernames(self):
        BusinessUser.objects.create_user(username='ada.tan', password='x')
        for seed, username in (
            ('ada.tan@example.com', 'ada.tan2'),
            ('Mei Lin', 'Mei.Lin'),
            ('!!!@example.com', 'user'),
            ('x' * 200 + '@example.com', 'x' * 144),
        ):
            with self.subTest(seed=seed):
                self.assertEqual(unique_username(seed), username)
