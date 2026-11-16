"""SCRUM-129: auto-eliminación de cuenta (POST /api/users/me/delete/). Ejecutar: python manage.py test accounts.tests_me_delete"""
from django.core.cache import cache
from rest_framework.test import APIClient

from .models import User
from .tests import PWD, BaseCase, make_user

URL = "/api/users/me/delete/"


class MyAccountDeleteTests(BaseCase):
    def test_requires_token(self):
        self.assertEqual(self.client.post(URL, {"password": PWD}, format="json").status_code, 401)

    def test_missing_password_is_400(self):
        self.auth("member@t.co")
        r = self.client.post(URL, {}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("password", r.data)
        self.member.refresh_from_db()
        self.assertFalse(self.member.user_delete)

    def test_wrong_password_changes_nothing(self):
        self.auth("member@t.co")
        r = self.client.post(URL, {"password": "mala"}, format="json")
        self.assertEqual(r.status_code, 400)
        self.member.refresh_from_db()
        self.assertTrue(self.member.user_active)
        self.assertFalse(self.member.user_delete)
        self.assertIsNone(self.member.deactivation_reason)

    def test_delete_ok_and_session_is_dead(self):
        r = self.login("member@t.co")
        access, refresh = r.data["access"], r.data["refresh"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

        r = self.client.post(URL, {"password": PWD}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("reactiv", r.data["detail"].lower())  # no existe flujo de reactivación

        self.member.refresh_from_db()
        self.assertTrue(self.member.user_delete)
        self.assertFalse(self.member.user_active)
        self.assertEqual(self.member.deactivation_reason, User.REASON_AUTO_ELIMINADO)
        self.assertEqual(self.member.user_updated_by_id, self.member.pk)

        # El mismo token ya no sirve
        self.assertEqual(self.client.get("/api/users/me").status_code, 401)
        # No puede volver a iniciar sesión
        self.client.credentials()
        self.assertEqual(self.login("member@t.co").status_code, 401)
        # El refresh tampoco renueva
        self.assertEqual(self.client.post("/api/auth/refresh/", {"refresh": refresh}, format="json").status_code, 401)

    def test_record_is_kept_and_hidden_from_admin_list(self):
        self.auth("member@t.co")
        self.client.post(URL, {"password": PWD}, format="json")
        self.assertTrue(User.objects.filter(pk=self.member.pk).exists())  # borrado lógico, no físico

        self.client.credentials()
        self.auth("admin@t.co")
        emails = [u["email"] for u in self.client.get("/api/users/").data["results"]]
        self.assertNotIn("member@t.co", emails)

    def test_last_admin_cannot_delete_but_can_if_there_is_another(self):
        self.auth("admin@t.co")
        r = self.client.post(URL, {"password": PWD}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("único administrador", r.data["detail"])
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.user_active)

        make_user("admin2@t.co", "ADMIN")
        r = self.client.post(URL, {"password": PWD}, format="json")
        self.assertEqual(r.status_code, 200)

    def test_email_stays_reserved_after_self_delete(self):
        """Documenta el comportamiento actual: sin flujo de reactivación, el correo no se puede re-registrar."""
        self.auth("member@t.co")
        self.client.post(URL, {"password": PWD}, format="json")
        r = APIClient().post(
            "/api/auth/register/",
            {"name": "N", "lastname": "L", "email": "member@t.co", "password": "Otra.Clave123"},
            format="json",
        )
        self.assertEqual(r.status_code, 409)

    def test_throttle_limits_password_guessing(self):
        cache.clear()
        self.auth("member@t.co")
        codes = [self.client.post(URL, {"password": f"mala{i}"}, format="json").status_code for i in range(7)]
        self.assertEqual(codes[:5], [400] * 5)
        self.assertEqual(codes[-1], 429)