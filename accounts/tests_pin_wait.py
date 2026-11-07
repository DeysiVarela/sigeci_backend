"""Espera de 1 minuto entre solicitudes de PIN y envío solo a correos registrados."""
from datetime import timedelta
from unittest.mock import patch

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from . import tests as base
from .models import PasswordResetPin


class PinWaitTests(base.BaseCase):
    def forgot(self, email="member@t.co"):
        with patch("accounts.views.send_recovery_pin_email") as sender:
            r = self.client.post("/api/auth/password/forgot/", {"email": email}, format="json")
        return r, sender

    def test_first_request_returns_wait_time(self):
        r, sender = self.forgot()
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["retry_after"], settings.PASSWORD_RESET_RESEND_SECONDS)
        sender.assert_called_once()

    def test_second_request_within_wait_is_429_and_sends_nothing(self):
        _, first = self.forgot()
        r, second = self.forgot()
        self.assertEqual(r.status_code, 429)
        self.assertTrue(0 < r.data["retry_after"] <= settings.PASSWORD_RESET_RESEND_SECONDS)
        self.assertEqual(r["Retry-After"], str(r.data["retry_after"]))
        first.assert_called_once()
        second.assert_not_called()
        self.assertEqual(PasswordResetPin.objects.count(), 1)

    def test_wait_also_applies_to_unregistered_emails(self):
        """Misma conducta exista o no el correo: no se revela quién está registrado."""
        self.forgot("nadie@t.co")
        r, _ = self.forgot("nadie@t.co")
        self.assertEqual(r.status_code, 429)

    def test_wait_is_per_email_and_ignores_case(self):
        self.forgot("member@t.co")
        r, _ = self.forgot("MEMBER@t.co")
        self.assertEqual(r.status_code, 429)
        other, sender = self.forgot("admin@t.co")
        self.assertEqual(other.status_code, 200)
        sender.assert_called_once()

    def test_can_request_again_after_the_wait(self):
        self.forgot()
        cache.clear()  # simula que pasó el tiempo de espera
        PasswordResetPin.objects.update(
            created_at=timezone.now() - timedelta(seconds=settings.PASSWORD_RESET_RESEND_SECONDS + 1)
        )
        r, sender = self.forgot()
        self.assertEqual(r.status_code, 200)
        sender.assert_called_once()

    def test_unregistered_email_sends_nothing_and_creates_no_pin(self):
        r, sender = self.forgot("nadie@t.co")
        self.assertEqual(r.status_code, 200)
        sender.assert_not_called()
        self.assertEqual(PasswordResetPin.objects.count(), 0)

    def test_inactive_account_sends_nothing(self):
        base.make_user("off@t.co", "MEMBER", active=False)
        r, sender = self.forgot("off@t.co")
        self.assertEqual(r.status_code, 200)
        sender.assert_not_called()
