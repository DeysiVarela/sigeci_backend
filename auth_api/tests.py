import json
import os
from unittest.mock import MagicMock, patch
from urllib.error import URLError

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
        with patch(
            'auth_api.views._verify_captcha',
            return_value=False,
        ):
            response, body = self.post_login({
                'identifier': 'demo@sigeci.local',
                'password': 'DemoPass123!',
                'captchaToken': 'invalid',
            })

        self.assertEqual(response.status_code, 400)
        self.assertIn('CAPTCHA', body['message'])

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

        response, body = self.post_login({
            'identifier': 'demo@sigeci.local',
            'password': 'DemoPass123!',
            'captchaToken': 'valid-token',
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(body['message'], 'Inicio de sesión exitoso.')
        mock_urlopen.assert_called_once()

    @patch.dict(os.environ, {'RECAPTCHA_SECRET_KEY': 'test-secret'})
    @patch(
        'auth_api.views.urlopen',
        side_effect=URLError('provider unavailable'),
    )
    def test_provider_unavailable_rejects_login(self, mock_urlopen):
        response, body = self.post_login({
            'identifier': 'demo@sigeci.local',
            'password': 'DemoPass123!',
            'captchaToken': 'some-token',
        })

        self.assertEqual(response.status_code, 400)
        self.assertIn('CAPTCHA', body['message'])
        mock_urlopen.assert_called_once()

    @patch.dict(os.environ, {}, clear=True)
    def test_missing_secret_returns_service_unavailable(self):
        response, body = self.post_login({
            'identifier': 'demo@sigeci.local',
            'password': 'DemoPass123!',
            'captchaToken': 'some-token',
        })

        self.assertEqual(response.status_code, 503)
        self.assertNotIn('secret', body['message'].lower())

    def test_missing_captcha_token_is_rejected(self):
        response, body = self.post_login({
            'identifier': 'demo@sigeci.local',
            'password': 'DemoPass123!',
        })

        self.assertEqual(response.status_code, 400)
        self.assertIn('CAPTCHA', body['message'])
