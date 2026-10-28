
import os
from unittest.mock import MagicMock, patch
from urllib.error import URLError

from django.test import TestCase


class AuthApiTests(TestCase):

    def test_health_endpoint(self):
        response = self.client.get('/health')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'status': 'ok'})

    def test_login_requires_credentials_and_captcha(self):
        response = self.client.post(
            '/api/auth/login',
            data={},
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('obligatorios', response.json()['message'])

    @patch.dict(os.environ, {'RECAPTCHA_SECRET_KEY': 'test-secret'})
    def test_login_rejects_invalid_captcha(self):
        with patch(
            'auth_api.views._verify_captcha',
            return_value=False,
        ):
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

    @patch.dict(os.environ, {
        'RECAPTCHA_SECRET_KEY': 'test-secret',
        'DEMO_USER_EMAIL': 'demo@sigeci.local',
        'DEMO_USER_PASSWORD': 'DemoPass123!',
    })
    @patch('auth_api.views.urlopen')
    def test_valid_captcha_allows_login(self, mock_urlopen):
        google_response = MagicMock()
        google_response.__enter__.return_value.read.return_value = (
            b'{"success": true}'
        )
        mock_urlopen.return_value = google_response

        response = self.client.post(
            '/api/auth/login',
            data={
                'identifier': 'demo@sigeci.local',
                'password': 'DemoPass123!',
                'captchaToken': 'valid-token',
            },
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()['message'],
            'Inicio de sesión exitoso.',
        )
        mock_urlopen.assert_called_once()

    @patch.dict(os.environ, {'RECAPTCHA_SECRET_KEY': 'test-secret'})
    @patch(
        'auth_api.views.urlopen',
        side_effect=URLError('provider unavailable'),
    )
    def test_provider_unavailable_rejects_login(self, mock_urlopen):
        response = self.client.post(
            '/api/auth/login',
            data={
                'identifier': 'demo@sigeci.local',
                'password': 'DemoPass123!',
                'captchaToken': 'some-token',
            },
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('CAPTCHA', response.json()['message'])
        mock_urlopen.assert_called_once()

    @patch.dict(os.environ, {}, clear=True)
    def test_missing_secret_returns_service_unavailable(self):
        response = self.client.post(
            '/api/auth/login',
            data={
                'identifier': 'demo@sigeci.local',
                'password': 'DemoPass123!',
                'captchaToken': 'some-token',
            },
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 503)
        self.assertNotIn(
            'secret',
            response.json()['message'].lower(),
        )

    def test_missing_captcha_token_is_rejected(self):
        response = self.client.post(
            '/api/auth/login',
            data={
                'identifier': 'demo@sigeci.local',
                'password': 'DemoPass123!',
            },
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('CAPTCHA', response.json()['message'])
