import os
from unittest.mock import patch

from django.test import TestCase


class AuthApiTests(TestCase):
    def test_health_endpoint(self):
        response = self.client.get('/health')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'status': 'ok'})

    def test_login_requires_credentials_and_captcha(self):
        response = self.client.post('/api/auth/login', data={}, content_type='application/json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('obligatorios', response.json()['message'])

    @patch.dict(os.environ, {'RECAPTCHA_SECRET_KEY': 'test-secret'})
    def test_login_rejects_invalid_captcha(self):
        with patch('auth_api.views._verify_captcha', return_value=False):
            response = self.client.post(
                '/api/auth/login',
                data={
                    'identifier': 'demo@sigeci.local',
                    'password': 'DemoPass123!',
                    'captchaToken': 'invalid',
                },
                content_type='application/json',
            )
        self.assertEqual(response.status_code, 400)
        self.assertIn('CAPTCHA', response.json()['message'])
