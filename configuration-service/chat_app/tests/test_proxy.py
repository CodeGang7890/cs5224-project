from unittest.mock import patch

import httpx
from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import AccessToken

from auth_app.models import BusinessUser
from configuration_app.models import BusinessConfiguration
from chat_app.models import ChatSession


@override_settings(
    MESSAGING_SERVICE_URL='https://messaging.example.run.app',
    MESSAGING_SERVICE_REQUIRE_ID_TOKEN=True,
)
class SandboxMessageProxyTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.business = BusinessConfiguration.objects.create(business_name='Cafe', location='Singapore')
        cls.other_business = BusinessConfiguration.objects.create(business_name='Florist', location='Singapore')
        cls.user = BusinessUser.objects.create_user(username='cafe', password='local-test', business=cls.business)
        cls.sandbox = ChatSession.objects.create(business=cls.business, is_sandbox=True)
        cls.other_sandbox = ChatSession.objects.create(business=cls.other_business, is_sandbox=True)
        cls.real_session = ChatSession.objects.create(
            business=cls.business, is_sandbox=False, phone_number='+6591234567'
        )

    def url(self, session):
        return reverse('chat_app:sandbox-session-message', args=[session.pk])

    def login(self):
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {AccessToken.for_user(self.user)}')

    @patch('chat_app.views.httpx.post')
    def test_requires_login_before_calling_messaging(self, post):
        response = self.client.post(self.url(self.sandbox), {'message': 'hello'}, format='json')
        self.assertEqual(response.status_code, 401)
        post.assert_not_called()

    @patch('chat_app.views.httpx.post')
    def test_rejects_other_business_and_real_sessions(self, post):
        self.login()
        self.assertEqual(self.client.post(self.url(self.other_sandbox), {'message': 'hi'}, format='json').status_code, 403)
        self.assertEqual(self.client.post(self.url(self.real_session), {'message': 'hi'}, format='json').status_code, 400)
        post.assert_not_called()

    @patch('chat_app.views.httpx.post')
    def test_rejects_invalid_message_before_calling_messaging(self, post):
        self.login()
        response = self.client.post(self.url(self.sandbox), {'message': ''}, format='json')
        self.assertEqual(response.status_code, 400)
        post.assert_not_called()

    @patch('chat_app.views.fetch_id_token', return_value='cloud-run-token')
    @patch('chat_app.views.httpx.post', return_value=httpx.Response(200, json={'reply': 'Hello', 'messages': [], 'debug': {}}))
    def test_forwards_user_jwt_and_cloud_run_id_token(self, post, fetch_id_token):
        self.login()
        response = self.client.post(self.url(self.sandbox), {'message': '  hello  '}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['reply'], 'Hello')
        self.assertEqual(post.call_args.kwargs['json'], {'message': 'hello'})
        self.assertEqual(post.call_args.kwargs['headers']['X-Serverless-Authorization'], 'Bearer cloud-run-token')
        self.assertEqual(post.call_args.kwargs['headers']['Authorization'], self.client._credentials['HTTP_AUTHORIZATION'])
        self.assertEqual(
            post.call_args.args[0],
            f'https://messaging.example.run.app/api/chat/sandbox-sessions/{self.sandbox.pk}/messages/',
        )
        self.assertEqual(fetch_id_token.call_args.args[1], 'https://messaging.example.run.app')

    @patch('chat_app.views.fetch_id_token', return_value='cloud-run-token')
    @patch('chat_app.views.httpx.post', side_effect=httpx.ReadTimeout('timed out'))
    def test_upstream_timeout_returns_504(self, post, fetch_id_token):
        self.login()
        response = self.client.post(self.url(self.sandbox), {'message': 'hello'}, format='json')
        self.assertEqual(response.status_code, 504)
        self.assertIn('timed out', response.json()['detail'])

    @patch('chat_app.views.fetch_id_token', return_value='cloud-run-token')
    @patch('chat_app.views.httpx.post', return_value=httpx.Response(400, json={'message': ['This field may not be blank.']}))
    def test_preserves_messaging_validation_errors(self, post, fetch_id_token):
        self.login()
        response = self.client.post(self.url(self.sandbox), {'message': 'hello'}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {'message': ['This field may not be blank.']})

    @patch('chat_app.views.fetch_id_token', return_value='cloud-run-token')
    @patch('chat_app.views.httpx.post', return_value=httpx.Response(403, text='<html>Cloud Run denied</html>'))
    def test_cloud_run_html_error_is_not_forwarded(self, post, fetch_id_token):
        self.login()
        response = self.client.post(self.url(self.sandbox), {'message': 'hello'}, format='json')
        self.assertEqual(response.status_code, 502)
        self.assertNotIn('Cloud Run denied', response.json()['detail'])
