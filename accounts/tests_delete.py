"""Eliminación física de usuarios (SCRUM-16 CA-05): se borra de la base de datos."""
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.db import IntegrityError
from rest_framework.test import APIClient

from . import tests as base
from .models import Profile, User


class HardDeleteTests(base.BaseCase):
    def setUp(self):
        super().setUp()
        self.victim = base.make_user("borrar@t.co", "AUTHOR")
        self.auth("admin@t.co")

    def test_delete_removes_the_row_from_the_database(self):
        pk = self.victim.pk
        self.assertEqual(self.client.delete(f"/api/users/{pk}/").status_code, 204)
        self.assertFalse(User.objects.filter(pk=pk).exists())
        self.assertEqual(self.client.get(f"/api/users/{pk}/").status_code, 404)

    def test_deleted_user_cannot_log_in_and_email_can_be_reused(self):
        self.client.delete(f"/api/users/{self.victim.pk}/")
        self.assertEqual(self.login("borrar@t.co").status_code, 401)
        body = {
            "name": "Nuevo", "lastname": "Usuario", "email": "borrar@t.co", "password": base.PWD,
            "profile": Profile.objects.get(profile_name="AUTHOR").pk,
        }
        self.assertEqual(self.client.post("/api/users/", body, format="json").status_code, 201)

    def test_token_of_a_deleted_user_stops_working(self):
        token = self.login("borrar@t.co").data["access"]
        other = APIClient()
        other.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        self.assertEqual(other.get("/api/auth/me/").status_code, 200)
        self.client.delete(f"/api/users/{self.victim.pk}/")
        self.assertEqual(other.get("/api/auth/me/").status_code, 401)

    def test_audit_references_to_the_deleted_user_are_cleared(self):
        other = base.make_user("otro@t.co", "MEMBER")
        other.user_created_by = self.victim
        other.save()
        self.client.delete(f"/api/users/{self.victim.pk}/")
        other.refresh_from_db()
        self.assertIsNone(other.user_created_by_id)

    def test_delete_with_related_records_returns_409_and_keeps_the_user(self):
        with patch.object(User, "delete", side_effect=IntegrityError("fk")):
            r = self.client.delete(f"/api/users/{self.victim.pk}/")
        self.assertEqual(r.status_code, 409)
        self.assertIn("Desactívalo", r.data["detail"])
        self.assertTrue(User.objects.filter(pk=self.victim.pk).exists())

    def test_purge_command_lists_without_yes_and_deletes_with_yes(self):
        old = base.make_user("viejo@t.co", "AUTHOR", active=False)
        old.user_delete = True
        old.save()
        call_command("purge_deleted_users", stdout=StringIO())
        self.assertTrue(User.objects.filter(pk=old.pk).exists())
        call_command("purge_deleted_users", "--yes", stdout=StringIO())
        self.assertFalse(User.objects.filter(pk=old.pk).exists())
        self.assertTrue(User.objects.filter(pk=self.victim.pk).exists())  # los demás no se tocan
