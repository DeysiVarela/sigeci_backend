"""Eliminación lógica de usuarios (SCRUM-16 CA-05): pierde el acceso, pero su registro se conserva."""
from unittest.mock import patch

from rest_framework.test import APIClient

from . import tests as base
from .models import Profile, User


class SoftDeleteTests(base.BaseCase):
    def setUp(self):
        super().setUp()
        self.victim = base.make_user("borrar@t.co", "AUTHOR")
        self.auth("admin@t.co")

    def delete(self):
        return self.client.delete(f"/api/users/{self.victim.pk}/")

    def test_delete_marks_the_user_as_deleted_and_keeps_the_row(self):
        self.assertEqual(self.delete().status_code, 204)
        row = User.objects.get(pk=self.victim.pk)  # la fila se conserva
        self.assertTrue(row.user_delete)
        self.assertFalse(row.user_active)

    def test_deleted_user_disappears_from_the_api(self):
        self.delete()
        self.assertEqual(self.client.get(f"/api/users/{self.victim.pk}/").status_code, 404)
        emails = [u["email"] for u in self.client.get("/api/users/?page_size=100").data["results"]]
        self.assertNotIn("borrar@t.co", emails)

    def test_deleting_twice_returns_404(self):
        self.delete()
        self.assertEqual(self.delete().status_code, 404)

    def test_deleted_user_cannot_log_in(self):
        self.delete()
        self.assertEqual(self.login("borrar@t.co").status_code, 401)

    def test_token_of_a_deleted_user_stops_working(self):
        token = self.login("borrar@t.co").data["access"]
        other = APIClient()
        other.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        self.assertEqual(other.get("/api/auth/me/").status_code, 200)
        self.delete()
        self.assertEqual(other.get("/api/auth/me/").status_code, 401)

    def test_deleted_user_does_not_receive_a_recovery_pin(self):
        self.delete()
        with patch("accounts.views.send_recovery_pin_email") as sender:
            r = self.client.post("/api/auth/password/forgot/", {"email": "borrar@t.co"}, format="json")
        self.assertEqual(r.status_code, 200)
        sender.assert_not_called()

    def test_references_to_the_deleted_user_stay_intact(self):
        other = base.make_user("otro@t.co", "MEMBER")
        other.user_created_by = self.victim
        other.save()
        self.delete()
        other.refresh_from_db()
        self.assertEqual(other.user_created_by_id, self.victim.pk)

    def test_email_of_a_deleted_user_stays_reserved(self):
        self.delete()
        body = {
            "name": "Nuevo", "lastname": "Usuario", "email": "borrar@t.co", "password": base.PWD,
            "profile": Profile.objects.get(profile_name="AUTHOR").pk,
        }
        self.assertEqual(self.client.post("/api/users/", body, format="json").status_code, 400)
