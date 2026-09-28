from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from configuration_app.models import BusinessConfiguration

from .models import BusinessUser


class AuthAPITests(APITestCase):
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
