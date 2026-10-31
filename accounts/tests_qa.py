"""
Cobertura QA adicional de SCRUM-15 (PIN) y SCRUM-16 (usuarios).
Ver docs/trazabilidad-qa-scrum-15-16.md para el mapa criterio -> prueba.
"""
from datetime import timedelta
from unittest.mock import patch

from django.conf import settings
from django.utils import timezone

from . import tests as base
from .models import PasswordResetPin, Profile, ProfileAction


class PinRulesTests(base.BaseCase):
    """SCRUM-15 CA-04 y CA-06: vigencia, longitud, reenvío, cuenta, reglas de clave."""

    def forgot(self, email="member@t.co"):
        with patch("accounts.views.send_recovery_pin_email") as sender:
            r = self.client.post("/api/auth/password/forgot/", {"email": email}, format="json")
        return r, sender

    def reset(self, pin, password="Nueva.Clave9", email="member@t.co"):
        return self.client.post(
            "/api/auth/password/reset/", {"email": email, "pin": pin, "password": password}, format="json"
        )

    def test_expired_pin_is_rejected(self):
        _, sender = self.forgot()
        pin = sender.call_args.args[1]
        PasswordResetPin.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.reset(pin).status_code, 400)
        # la contraseña anterior sigue vigente y la nueva no se aplicó
        self.assertEqual(self.login("member@t.co", base.PWD).status_code, 200)
        self.assertEqual(self.login("member@t.co", "Nueva.Clave9").status_code, 401)

    def test_pin_is_valid_before_expiry(self):
        _, sender = self.forgot()
        pin = sender.call_args.args[1]
        PasswordResetPin.objects.update(expires_at=timezone.now() + timedelta(minutes=1))
        self.assertEqual(self.reset(pin).status_code, 200)

    def test_pin_lifetime_and_length_follow_settings(self):
        _, sender = self.forgot()
        pin = sender.call_args.args[1]
        self.assertEqual(len(pin), settings.PASSWORD_RESET_PIN_LENGTH)
        self.assertTrue(pin.isdigit())
        row = PasswordResetPin.objects.get()
        seconds = (row.expires_at - row.created_at).total_seconds()
        self.assertAlmostEqual(seconds, settings.PASSWORD_RESET_PIN_MINUTES * 60, delta=5)

    def test_resend_within_cooldown_does_not_send_another_pin(self):
        _, first = self.forgot()
        _, second = self.forgot()
        first.assert_called_once()
        second.assert_not_called()
        self.assertEqual(PasswordResetPin.objects.count(), 1)

    def test_resend_after_cooldown_invalidates_previous_pin(self):
        _, first = self.forgot()
        old = first.call_args.args[1]
        PasswordResetPin.objects.update(
            created_at=timezone.now() - timedelta(seconds=settings.PASSWORD_RESET_RESEND_SECONDS + 1)
        )
        _, second = self.forgot()
        new = second.call_args.args[1]
        if old == new:
            self.skipTest("PIN repetido por azar")
        self.assertEqual(self.reset(old).status_code, 400)
        self.assertEqual(self.reset(new).status_code, 200)

    def test_pin_of_another_account_is_rejected(self):
        _, member = self.forgot("member@t.co")
        _, admin = self.forgot("admin@t.co")
        pin_member = member.call_args.args[1]
        if pin_member == admin.call_args.args[1]:
            self.skipTest("PIN repetido por azar")
        self.assertEqual(self.reset(pin_member, email="admin@t.co").status_code, 400)
        self.assertEqual(self.login("admin@t.co", base.PWD).status_code, 200)

    def test_weak_password_is_rejected_without_consuming_pin(self):
        _, sender = self.forgot()
        pin = sender.call_args.args[1]
        self.assertEqual(self.reset(pin, password="123").status_code, 400)
        self.assertEqual(self.reset(pin).status_code, 200)  # el PIN seguía disponible


class UserQaTests(base.BaseCase):
    """SCRUM-16 CA-02, CA-04 y CA-06: validación sin cambios parciales, permisos finos, sin secretos."""

    def test_update_with_duplicate_email_is_rejected_and_not_persisted(self):
        self.auth("admin@t.co")
        r = self.client.patch(
            f"/api/users/{self.member.pk}/", {"name": "Cambio", "email": "admin@t.co"}, format="json"
        )
        self.assertEqual(r.status_code, 400)
        self.member.refresh_from_db()
        self.assertEqual(self.member.user_name, "N")
        self.assertEqual(self.member.user_email, "member@t.co")

    def test_role_change_requires_explicit_permission(self):
        editor = Profile.objects.create(profile_name="EDITOR")
        for perm in ("view", "update"):
            ProfileAction.objects.create(
                profile=editor, profile_action_action="user", profile_action_permissions=perm
            )
        base.make_user("editor@t.co", "EDITOR")
        self.auth("editor@t.co")

        ok = self.client.patch(f"/api/users/{self.member.pk}/", {"name": "Nuevo"}, format="json")
        self.assertEqual(ok.status_code, 200)

        author = Profile.objects.get(profile_name="AUTHOR").pk
        denied = self.client.patch(f"/api/users/{self.member.pk}/", {"profile": author}, format="json")
        self.assertEqual(denied.status_code, 403)
        self.member.refresh_from_db()
        self.assertEqual(self.member.profile.profile_name, "MEMBER")

    def test_responses_never_expose_secrets(self):
        self.auth("admin@t.co")
        bodies = [
            self.client.get("/api/users/").content.decode().lower(),
            self.client.get(f"/api/users/{self.member.pk}/").content.decode().lower(),
            self.client.get("/api/auth/me/").content.decode().lower(),
        ]
        for body in bodies:
            self.assertNotIn("password", body)
            self.assertNotIn("pbkdf2", body)
            self.assertNotIn("pin", body.replace("permissions", ""))
