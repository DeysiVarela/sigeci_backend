"""Evidencia CRUD / filtros / permisos / recuperación (CA-07). Ejecutar: python manage.py test accounts"""
import os
from unittest.mock import patch

from django.core.management import call_command
from django.test import override_settings
from django.core.cache import cache
from rest_framework.test import APITestCase
from rest_framework.throttling import ScopedRateThrottle

from notifications.services import PinEmailError

from .models import PasswordResetPin, Profile, User

PWD = "Clave.Segura1"


def make_user(email, profile_name, active=True, password=PWD):
    u = User(user_name="N", user_lastname="L", user_email=email,
             profile=Profile.objects.get(profile_name=profile_name), user_active=active)
    u.set_password(password)
    u.save()
    return u


@override_settings(CAPTCHA_REQUIRED=False)  # los tests de captcha lo activan explícitamente
class BaseCase(APITestCase):
    def setUp(self):
        cache.clear()
        # Los tests hacen muchas peticiones seguidas: se relajan los límites de throttling
        ScopedRateThrottle.THROTTLE_RATES = {"auth": "1000/min", "password_reset": "1000/min"}
        call_command("seed_accounts")
        self.admin = make_user("admin@t.co", "ADMIN")
        self.member = make_user("member@t.co", "MEMBER")

    def login(self, email, password=PWD):
        r = self.client.post("/api/auth/login/", {"email": email, "password": password}, format="json")
        return r

    def auth(self, email):
        r = self.login(email)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {r.data['access']}")


class AuthTests(BaseCase):
    def test_login_ok_and_bad(self):
        self.assertEqual(self.login("admin@t.co").status_code, 200)
        self.assertEqual(self.login("admin@t.co", "mala").status_code, 401)
        self.assertEqual(self.login("noexiste@t.co").status_code, 401)

    def test_login_response_has_no_secrets(self):
        r = self.login("admin@t.co")
        self.assertNotIn("password", str(r.data).lower().replace("permissions", ""))

    def test_requires_token(self):
        self.assertEqual(self.client.get("/api/users/").status_code, 401)


class UserCrudTests(BaseCase):
    def test_member_is_forbidden_even_calling_endpoint_directly(self):
        self.auth("member@t.co")
        self.assertEqual(self.client.get("/api/users/").status_code, 403)
        self.assertEqual(self.client.post("/api/users/", {}, format="json").status_code, 403)

    def test_create_validations_and_unique_email(self):
        self.auth("admin@t.co")
        pid = Profile.objects.get(profile_name="AUTHOR").pk
        body = {"name": "Ana", "lastname": "Paz", "email": "ana@t.co", "password": PWD, "profile": pid}
        r = self.client.post("/api/users/", body, format="json")
        self.assertEqual(r.status_code, 201)
        self.assertNotIn("password", r.data)
        self.assertTrue(User.objects.get(user_email="ana@t.co").user_password.startswith(("pbkdf2", "argon", "bcrypt")))
        self.assertEqual(self.client.post("/api/users/", body, format="json").status_code, 400)
        weak = dict(body, email="b@t.co", password="123")
        self.assertEqual(self.client.post("/api/users/", weak, format="json").status_code, 400)
        self.assertFalse(User.objects.filter(user_email="b@t.co").exists())

    def test_list_pagination_and_filters(self):
        self.auth("admin@t.co")
        make_user("x@t.co", "MEMBER", active=False)
        r = self.client.get("/api/users/?page_size=2")
        self.assertEqual(r.data["count"], 3)
        self.assertEqual(len(r.data["results"]), 2)
        member_id = Profile.objects.get(profile_name="MEMBER").pk
        self.assertEqual(self.client.get(f"/api/users/?profile={member_id}").data["count"], 2)
        self.assertEqual(self.client.get("/api/users/?active=false").data["count"], 1)
        self.assertEqual(self.client.get(f"/api/users/?profile={member_id}&active=false").data["count"], 1)

    def test_soft_delete_and_self_delete_blocked(self):
        self.auth("admin@t.co")
        self.assertEqual(self.client.delete(f"/api/users/{self.admin.pk}/").status_code, 400)
        self.assertEqual(self.client.delete(f"/api/users/{self.member.pk}/").status_code, 204)
        self.member.refresh_from_db()
        self.assertTrue(self.member.user_delete)
        self.assertFalse(self.member.user_active)
        self.assertEqual(self.client.get(f"/api/users/{self.member.pk}/").status_code, 404)
        self.assertEqual(self.login("member@t.co").status_code, 401)

    def test_update_role_and_status(self):
        self.auth("admin@t.co")
        author = Profile.objects.get(profile_name="AUTHOR").pk
        r = self.client.patch(f"/api/users/{self.member.pk}/", {"profile": author, "active": False}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["profile_name"], "AUTHOR")
        self.assertFalse(r.data["active"])


class PasswordRecoveryTests(BaseCase):
    """El envío del correo es de notifications; aquí se intercepta para leer el PIN."""

    def forgot(self, email):
        with patch("accounts.views.send_recovery_pin_email") as sender:
            r = self.client.post("/api/auth/password/forgot/", {"email": email}, format="json")
        return r, sender

    def test_full_flow_and_pin_single_use(self):
        r1, sender = self.forgot("member@t.co")
        r2, sender2 = self.forgot("nadie@t.co")
        self.assertEqual(r1.data, r2.data)  # no revela si el correo existe
        sender2.assert_not_called()
        pin = sender.call_args.args[1]
        new = "Nueva.Clave9"
        ok = self.client.post("/api/auth/password/reset/", {"email": "member@t.co", "pin": pin, "password": new}, format="json")
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(self.login("member@t.co", new).status_code, 200)
        self.assertEqual(self.login("member@t.co", PWD).status_code, 401)
        again = self.client.post("/api/auth/password/reset/", {"email": "member@t.co", "pin": pin, "password": "Otra.Clave9"}, format="json")
        self.assertEqual(again.status_code, 400)

    def test_wrong_pin_and_attempt_limit(self):
        _, sender = self.forgot("member@t.co")
        real = sender.call_args.args[1]
        wrong = "000000" if real != "000000" else "111111"
        for _ in range(5):
            r = self.client.post("/api/auth/password/reset/", {"email": "member@t.co", "pin": wrong, "password": "Nueva.Clave9"}, format="json")
            self.assertEqual(r.status_code, 400)
        r = self.client.post("/api/auth/password/reset/", {"email": "member@t.co", "pin": real, "password": "Nueva.Clave9"}, format="json")
        self.assertEqual(r.status_code, 400)  # bloqueado tras 5 intentos

    def test_pin_stored_hashed(self):
        _, sender = self.forgot("member@t.co")
        self.assertNotEqual(PasswordResetPin.objects.first().pin_hash, sender.call_args.args[1])

    def test_email_failure_does_not_leak(self):
        with patch("accounts.views.send_recovery_pin_email", side_effect=PinEmailError("x")):
            r = self.client.post("/api/auth/password/forgot/", {"email": "member@t.co"}, format="json")
        self.assertEqual(r.status_code, 200)


class LoginContractTests(BaseCase):
    """Contrato final: POST /api/auth/login { identifier, password, captchaToken }"""

    def post(self, url, body):
        return self.client.post(url, body, format="json")

    def test_identifier_with_and_without_trailing_slash(self):
        body = {"identifier": "admin@t.co", "password": PWD}
        self.assertEqual(self.post("/api/auth/login", body).status_code, 200)
        self.assertEqual(self.post("/api/auth/login/", body).status_code, 200)

    def test_email_alias_still_works(self):
        self.assertEqual(self.post("/api/auth/login/", {"email": "admin@t.co", "password": PWD}).status_code, 200)

    def test_missing_identifier(self):
        self.assertEqual(self.post("/api/auth/login/", {"password": PWD}).status_code, 400)

    def test_captcha_not_enforced_when_disabled(self):
        r = self.post("/api/auth/login", {"identifier": "admin@t.co", "password": PWD, "captchaToken": ""})
        self.assertEqual(r.status_code, 200)

    @override_settings(CAPTCHA_REQUIRED=True)
    @patch.dict(os.environ, {"RECAPTCHA_SECRET_KEY": "secret"})
    def test_captcha_required_when_enabled(self):
        r = self.post("/api/auth/login", {"identifier": "admin@t.co", "password": PWD})
        self.assertEqual(r.status_code, 400)

    @override_settings(CAPTCHA_REQUIRED=True)
    @patch.dict(os.environ, {"RECAPTCHA_SECRET_KEY": ""})
    def test_captcha_unavailable_without_secret(self):
        body = {"identifier": "admin@t.co", "password": PWD, "captchaToken": "tok"}
        self.assertEqual(self.post("/api/auth/login", body).status_code, 503)

    @override_settings(CAPTCHA_REQUIRED=True)
    @patch.dict(os.environ, {"RECAPTCHA_SECRET_KEY": "secret"})
    def test_captcha_rejected_and_accepted(self):
        body = {"identifier": "admin@t.co", "password": PWD, "captchaToken": "tok"}
        with patch("accounts.captcha._verify_captcha", return_value=False):
            self.assertEqual(self.post("/api/auth/login", body).status_code, 400)
        with patch("accounts.captcha._verify_captcha", return_value=True):
            self.assertEqual(self.post("/api/auth/login", body).status_code, 200)

    def test_login_route_is_the_real_one(self):
        """/api/auth/login debe devolver JWT (no el login de demostración de auth_api)."""
        r = self.post("/api/auth/login", {"identifier": "admin@t.co", "password": PWD})
        self.assertIn("access", r.data)
