from unittest.mock import patch

from django.core import mail
from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, override_settings

from notifications.services import PinEmailError, send_recovery_pin_email


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    EMAIL_HOST_USER="apikey",
    EMAIL_HOST_PASSWORD="fake-test-key",
    DEFAULT_FROM_EMAIL="sigeci-test@example.com",
)
class RecoveryPinEmailTests(SimpleTestCase):

    def test_sends_pin_to_recipient(self):
        send_recovery_pin_email("destinatario@example.com", "123456")

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(
            mail.outbox[0].subject,
            "SIGECI - Recuperación de cuenta",
        )
        self.assertEqual(
            mail.outbox[0].to,
            ["destinatario@example.com"],
        )
        self.assertIn("123456", mail.outbox[0].body)

    def test_rejects_empty_recipient(self):
        with self.assertRaises(ValueError):
            send_recovery_pin_email("", "123456")

    def test_rejects_invalid_email(self):
        with self.assertRaises(ValueError):
            send_recovery_pin_email("esto-no-es-un-correo", "123456")

    def test_rejects_empty_pin(self):
        with self.assertRaises(ValueError):
            send_recovery_pin_email("destinatario@example.com", "")

    @override_settings(EMAIL_HOST_PASSWORD="")
    def test_rejects_missing_smtp_credentials(self):
        with self.assertRaises(ImproperlyConfigured):
            send_recovery_pin_email("destinatario@example.com", "123456")

    @patch(
        "notifications.services.send_mail",
        side_effect=OSError("error simulado"),
    )
    def test_handles_smtp_failure(self, mock_send_mail):
        with self.assertRaises(PinEmailError):
            send_recovery_pin_email(
                "destinatario@example.com",
                "123456",
            )

    @patch("notifications.services.send_mail", return_value=0)
    def test_rejects_unconfirmed_send(self, mock_send_mail):
        with self.assertRaises(PinEmailError):
            send_recovery_pin_email(
                "destinatario@example.com",
                "123456",
            )
