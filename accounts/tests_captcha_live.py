"""
Pruebas del CAPTCHA CONTRA GOOGLE (red real). NO corren por defecto.

    RUN_LIVE_CAPTCHA_TESTS=1 python manage.py test accounts.tests_captcha_live

Opcional: RECAPTCHA_TEST_SECRET=<clave secreta de PRUEBA que Google publica en su
documentación> para comprobar el camino de aceptación sin resolver el widget.
"""
import json
import os
import unittest
import urllib.parse
import urllib.request
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from accounts.captcha import verify_captcha

LIVE = os.getenv("RUN_LIVE_CAPTCHA_TESTS") == "1"
SITEVERIFY_URL = "https://www.google.com/recaptcha/api/siteverify"


def _siteverify(secret, token):
    data = urllib.parse.urlencode({"secret": secret, "response": token}).encode()
    req = urllib.request.Request(SITEVERIFY_URL, data=data, method="POST")
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.load(resp)


@unittest.skipUnless(LIVE, "Defina RUN_LIVE_CAPTCHA_TESTS=1 para probar contra Google")
class RecaptchaLiveTests(SimpleTestCase):
    def test_google_endpoint_rejects_invalid_secret(self):
        """Hay conexión con Google y el endpoint responde con error para una clave inválida."""
        result = _siteverify("invalid-secret", "invalid-token")
        self.assertFalse(result["success"])
        self.assertTrue(result.get("error-codes"))

    @override_settings(CAPTCHA_REQUIRED=True)
    def test_real_secret_rejects_fake_token(self):
        """Con la clave real del equipo, un token inventado debe ser rechazado."""
        if not os.getenv("RECAPTCHA_SECRET_KEY"):
            self.skipTest("RECAPTCHA_SECRET_KEY no está configurada")
        self.assertFalse(verify_captcha("token-falso"))

    @unittest.skipUnless(os.getenv("RECAPTCHA_TEST_SECRET"), "Defina RECAPTCHA_TEST_SECRET")
    @override_settings(CAPTCHA_REQUIRED=True)
    def test_google_test_secret_accepts_any_token(self):
        """Con la clave de prueba de Google, la verificación real debe aceptar el token."""
        with patch.dict(os.environ, {"RECAPTCHA_SECRET_KEY": os.environ["RECAPTCHA_TEST_SECRET"]}):
            self.assertTrue(verify_captcha("cualquier-token"))
