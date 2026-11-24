import os
from unittest.mock import patch
"""SCRUM-129: auto-eliminación de cuenta (POST /api/users/me/delete/). Ejecutar: python manage.py test accounts.tests_me_delete"""
import json

from django.core.cache import cache
from rest_framework.test import APIClient

from .models import Profile, ProfileAction, User
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
        self.assertIsNotNone(self.member.user_updated_at)

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


class MyAccountDeletePermissionTests(BaseCase):
    """Seguridad en el backend: la matriz decide, no basta con conocer la URL."""

    def test_all_seeded_roles_can_delete_their_own_account(self):
        for role in ("MEMBER", "AUTHOR"):
            with self.subTest(role=role):
                email = f"{role.lower()}@x.co"
                user = make_user(email, role)
                client = APIClient()
                access = client.post("/api/auth/login/", {"email": email, "password": PWD}, format="json").data["access"]
                client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
                self.assertEqual(client.post(URL, {"password": PWD}, format="json").status_code, 200)
                user.refresh_from_db()
                self.assertTrue(user.user_delete)

    def test_without_matrix_permission_is_403_and_nothing_changes(self):
        # Se le quita me:delete al rol AUTHOR (p. ej. una BD sin la fila de la matriz): falla cerrado
        ProfileAction.objects.filter(
            profile__profile_name="AUTHOR", profile_action_action="me"
        ).update(profile_action_permissions="view")
        autor = make_user("autor@t.co", "AUTHOR")
        self.auth("autor@t.co")

        r = self.client.post(URL, {"password": PWD}, format="json")
        self.assertEqual(r.status_code, 403)
        autor.refresh_from_db()
        self.assertTrue(autor.user_active)
        self.assertFalse(autor.user_delete)

    def test_permission_is_checked_before_password(self):
        """Sin permiso no se llega ni a validar la contraseña (no sirve para adivinarla)."""
        ProfileAction.objects.filter(profile__profile_name="AUTHOR", profile_action_action="me").delete()
        make_user("autor@t.co", "AUTHOR")
        self.auth("autor@t.co")
        r = self.client.post(URL, {"password": "mala"}, format="json")
        self.assertEqual(r.status_code, 403)
        self.assertNotIn("password", r.data)

    def test_multi_role_user_gets_permission_from_any_role(self):
        ProfileAction.objects.filter(
            profile__profile_name="AUTHOR", profile_action_action="me"
        ).update(profile_action_permissions="view")
        user = make_user("multi@t.co", "AUTHOR")
        user.profiles.add(Profile.objects.get(profile_name="MEMBER"))  # MEMBER sí conserva me:delete
        self.auth("multi@t.co")
        self.assertEqual(self.client.post(URL, {"password": PWD}, format="json").status_code, 200)

    def test_cannot_delete_somebody_elses_account(self):
        """La ruta no recibe id; ni con un id en la URL ni en el cuerpo se afecta a otra cuenta."""
        self.auth("member@t.co")
        self.assertEqual(self.client.post(f"/api/users/{self.admin.pk}/delete/", {"password": PWD}, format="json").status_code, 404)
        self.client.post(URL, {"password": PWD, "id": self.admin.pk, "user_id": self.admin.pk}, format="json")
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.user_active)
        self.assertFalse(self.admin.user_delete)


@patch.dict(os.environ, {"RECAPTCHA_SECRET_KEY": ""})
class MyAccountDeleteKillsV1SessionTests(BaseCase):
    """Los endpoints /api/v1 (decorador require_permission) también deben cortar al usuario eliminado."""

    def _v1_login(self, email):
        r = self.client.post("/api/v1/auth/login", json.dumps({"email": email, "password": PWD}), content_type="application/json")
        self.assertEqual(r.status_code, 200, r.content)
        return json.loads(r.content)["data"]["token"]

    def test_v1_token_stops_working_after_self_delete(self):
        user = make_user("autor@t.co", "AUTHOR")
        token = self._v1_login("autor@t.co")
        headers = {"HTTP_AUTHORIZATION": f"Bearer {token}", "HTTP_PROFILE": str(Profile.objects.get(profile_name="AUTHOR").pk)}

        self.assertEqual(self.client.get("/api/v1/article", **headers).status_code, 200)

        drf = APIClient()
        drf.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        self.assertEqual(drf.post(URL, {"password": PWD}, format="json").status_code, 200)

        self.assertEqual(self.client.get("/api/v1/article", **headers).status_code, 401)
        user.refresh_from_db()
        self.assertIsNotNone(user.user_seed_token)
