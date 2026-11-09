"""SCRUM-120: registro público (POST /api/auth/register/) con rol AUTHOR forzado."""
import os
from unittest.mock import patch

from django.db import IntegrityError
from django.test import override_settings

from . import tests as base
from .models import Profile, User

URL = "/api/auth/register/"


class RegisterTests(base.BaseCase):
    def body(self, **extra):
        data = {
            "name": "Ana", "lastname": "Paz", "email": "ana@t.co",
            "password": base.PWD, "captchaToken": "tok",
        }
        data.update(extra)
        return data

    def register(self, **extra):
        return self.client.post(URL, self.body(**extra), format="json")

    # ---- CA-04 / CA-05: endpoint público que crea siempre un AUTHOR
    def test_creates_an_author_account(self):
        r = self.register()
        self.assertEqual(r.status_code, 201)
        user = User.objects.get(user_email="ana@t.co")
        self.assertEqual(user.profile.profile_name, "AUTHOR")
        self.assertTrue(user.user_active)
        self.assertFalse(user.user_delete)
        self.assertEqual(user.user_provider, "ACCOUNT")
        self.assertIsNone(user.user_created_by)
        self.assertEqual(r.data["user"]["profile_name"], "AUTHOR")

    def test_is_public_even_with_a_bad_authorization_header(self):
        self.client.credentials(HTTP_AUTHORIZATION="Bearer basura")
        self.assertEqual(self.register().status_code, 201)

    def test_works_with_and_without_trailing_slash(self):
        self.assertEqual(self.client.post("/api/auth/register", self.body(), format="json").status_code, 201)
        self.assertEqual(self.register(email="otra@t.co").status_code, 201)

    def test_role_or_profile_fields_are_rejected(self):
        admin_id = Profile.objects.get(profile_name="ADMIN").pk
        for field, value in (
            ("profile", admin_id), ("profile_id", admin_id), ("profile_name", "ADMIN"),
            ("role", "ADMIN"), ("rol", "ADMIN"), ("perfil", "ADMIN"), ("user_role", "ADMIN"),
        ):
            with self.subTest(field=field):
                r = self.register(**{field: value})
                self.assertEqual(r.status_code, 400)
                self.assertIn("profile", r.data)
                self.assertFalse(User.objects.filter(user_email="ana@t.co").exists())

    def test_empty_role_fields_are_ignored_and_the_role_is_still_author(self):
        r = self.register(profile="", role=None)
        self.assertEqual(r.status_code, 201)
        self.assertEqual(User.objects.get(user_email="ana@t.co").profile.profile_name, "AUTHOR")

    def test_new_author_has_no_user_management_permissions(self):
        self.register()
        self.auth("ana@t.co")
        self.assertEqual(self.client.get("/api/users/").status_code, 403)
        self.assertNotIn("user", self.client.get("/api/auth/me/").data["permissions"])

    def test_missing_author_profile_returns_503_and_creates_nothing(self):
        Profile.objects.filter(profile_name="AUTHOR").delete()
        self.assertEqual(self.register().status_code, 503)
        self.assertFalse(User.objects.filter(user_email="ana@t.co").exists())

    # ---- CA-06: correo ya registrado
    def test_duplicate_email_returns_409_without_duplicating(self):
        self.assertEqual(self.register().status_code, 201)
        r = self.register()
        self.assertEqual(r.status_code, 409)
        self.assertIn("ya está registrado", r.data["detail"])
        self.assertEqual(User.objects.filter(user_email__iexact="ana@t.co").count(), 1)

    def test_duplicate_email_ignores_case_and_does_not_touch_the_existing_account(self):
        r = self.register(email="ADMIN@T.CO")
        self.assertEqual(r.status_code, 409)
        self.admin.refresh_from_db()
        self.assertEqual(self.admin.profile.profile_name, "ADMIN")
        self.assertTrue(self.admin.check_password(base.PWD))  # la contraseña existente no cambió

    def test_concurrent_duplicate_is_also_409(self):
        with patch.object(User, "save", side_effect=IntegrityError("unique")):
            self.assertEqual(self.register().status_code, 409)

    # ---- CA-04 / CA-03 (validación en el servidor)
    def test_validation_errors_return_400_and_persist_nothing(self):
        cases = {
            "sin nombre": {"name": ""},
            "nombre solo espacios": {"name": "   "},
            "nombre muy largo": {"name": "x" * 61},
            "sin apellido": {"lastname": ""},
            "correo inválido": {"email": "no-es-correo"},
            "contraseña débil": {"password": "123"},
        }
        for label, extra in cases.items():
            with self.subTest(label):
                r = self.register(**extra)
                self.assertEqual(r.status_code, 400)
                self.assertEqual(User.objects.filter(user_email="ana@t.co").count(), 0)

    def test_only_name_lastname_email_and_password_are_used(self):
        """Mismos datos que crear usuario (sin rol): lo demás se ignora; la confirmación es de la pantalla."""
        r = self.register(confirmPassword="otra-cosa", active=False, is_staff=True)
        self.assertEqual(r.status_code, 201)
        user = User.objects.get(user_email="ana@t.co")
        self.assertTrue(user.user_active)
        self.assertTrue(user.check_password(base.PWD))

    def test_missing_fields_are_required(self):
        for field in ("name", "lastname", "email", "password"):
            with self.subTest(field):
                data = self.body()
                data.pop(field)
                self.assertEqual(self.client.post(URL, data, format="json").status_code, 400)

    # ---- CA-07: contraseña cifrada (hash de Django, PBKDF2) y nunca expuesta
    def test_password_is_hashed_with_django_pbkdf2_and_never_returned(self):
        r = self.register()
        stored = User.objects.get(user_email="ana@t.co").user_password
        self.assertTrue(stored.startswith("pbkdf2_sha256$"), stored[:12])
        self.assertNotIn(base.PWD, stored)
        body = r.content.decode()
        self.assertNotIn(base.PWD, body)
        self.assertNotIn("password", body.lower())
        self.assertNotIn("pbkdf2", body.lower())

    def test_can_log_in_after_registering(self):
        self.register()
        self.assertEqual(self.login("ana@t.co").status_code, 200)
        self.assertEqual(self.login("ana@t.co", "Otra.Clave9").status_code, 401)


@override_settings(REGISTER_RATE="3/min")
class RegisterRateLimitTests(base.BaseCase):
    def test_too_many_registrations_from_the_same_ip_are_limited(self):
        codes = [
            self.client.post(
                URL,
                {"name": "Ana", "lastname": "Paz", "email": f"ana{i}@t.co", "password": base.PWD,
                 "captchaToken": "tok"},
                format="json",
            ).status_code
            for i in range(4)
        ]
        self.assertEqual(codes, [201, 201, 201, 429])


@override_settings(CAPTCHA_REQUIRED=True)
class RegisterCaptchaTests(base.BaseCase):
    """CA-04: el CAPTCHA se valida con el servicio de SCRUM-14 antes de crear la cuenta."""

    def body(self, **extra):
        data = {
            "name": "Ana", "lastname": "Paz", "email": "ana@t.co",
            "password": base.PWD, "captchaToken": "tok",
        }
        data.update(extra)
        return data

    @patch.dict(os.environ, {"RECAPTCHA_SECRET_KEY": "secret"})
    def test_missing_token_is_rejected(self):
        data = self.body()
        data.pop("captchaToken")
        self.assertEqual(self.client.post(URL, data, format="json").status_code, 400)
        self.assertFalse(User.objects.filter(user_email="ana@t.co").exists())

    @patch.dict(os.environ, {"RECAPTCHA_SECRET_KEY": ""})
    def test_unavailable_when_secret_is_not_configured(self):
        self.assertEqual(self.client.post(URL, self.body(), format="json").status_code, 503)
        self.assertFalse(User.objects.filter(user_email="ana@t.co").exists())

    @patch.dict(os.environ, {"RECAPTCHA_SECRET_KEY": "secret"})
    def test_invalid_token_is_rejected_and_valid_token_is_accepted(self):
        with patch("accounts.captcha._verify_captcha", return_value=False):
            self.assertEqual(self.client.post(URL, self.body(), format="json").status_code, 400)
        self.assertFalse(User.objects.filter(user_email="ana@t.co").exists())
        with patch("accounts.captcha._verify_captcha", return_value=True):
            self.assertEqual(self.client.post(URL, self.body(), format="json").status_code, 201)

    @patch.dict(os.environ, {"RECAPTCHA_SECRET_KEY": "secret"})
    def test_form_errors_do_not_consume_the_captcha(self):
        with patch("accounts.captcha._verify_captcha", return_value=True) as verify:
            r = self.client.post(URL, self.body(password="123"), format="json")
        self.assertEqual(r.status_code, 400)
        verify.assert_not_called()

    @patch.dict(os.environ, {"RECAPTCHA_SECRET_KEY": "secret"})
    def test_captcha_is_checked_before_revealing_registered_emails(self):
        """Un bot sin CAPTCHA válido no puede averiguar qué correos existen (no recibe 409)."""
        with patch("accounts.captcha._verify_captcha", return_value=False):
            r = self.client.post(URL, self.body(email="admin@t.co"), format="json")
        self.assertEqual(r.status_code, 400)
