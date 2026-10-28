import json
import os
from unittest.mock import patch

from django.test import RequestFactory, TestCase

from auth_api.views import login


class AuthApiTests(TestCase):
    """
    El login de demostración de auth_api se invoca directamente (no por URL):
    /api/auth/login pertenece ahora al login real de `accounts` (JWT).
    """

    def post_login(self, data):
        request = RequestFactory().post(
            '/api/auth/login',
            data=json.dumps(data),
            content_type='application/json',
        )
        response = login(request)
        return response, json.loads(response.content)

    def test_health_endpoint(self):
        response = self.client.get('/health')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'status': 'ok'})

    def test_login_requires_credentials_and_captcha(self):
        response, body = self.post_login({})
        self.assertEqual(response.status_code, 400)
        self.assertIn('obligatorios', body['message'])

    @patch.dict(os.environ, {'RECAPTCHA_SECRET_KEY': 'test-secret'})
    def test_login_rejects_invalid_captcha(self):
        with patch('auth_api.views._verify_captcha', return_value=False):
            response, body = self.post_login({
                'identifier': 'demo@sigeci.local',
                'password': 'DemoPass123!',
                'captchaToken': 'invalid',
            })
        self.assertEqual(response.status_code, 400)
        self.assertIn('CAPTCHA', body['message'])
