"""SCRUM-125: /api/users/me (consultar y actualizar mi perfil) y /api/users/me/password/ (cambiar mi contraseña)."""
from unittest.mock import patch

from django.test import override_settings
from rest_framework.test import APIClient

from . import tests as base
from .models import Profile, User

NEW = "Nueva.Clave9"


@override_settings(PASSWORD_CHANGE_RATE="1000/min")
class MyProfileTests(base.BaseCase):
    def setUp(self):
        super().setUp()
        self.me = base.make_user("autor@t.co", "AUTHOR")  # AUTHOR: sin permisos sobre usuarios
        self.auth("autor@t.co")

    def patch_me(self, data, url="/api/users/me"):
        return self.client.patch(url, data, format="json")

    # ---- GET
    def test_get_returns_the_session_user_even_without_user_permissions(self):
        for url in ("/api/users/me", "/api/users/me/"):
            r = self.client.get(url)
            self.assertEqual(r.status_code, 200, url)
            self.assertEqual(r.data["email"], "autor@t.co")
            self.assertEqual(r.data["profile_name"], "AUTHOR")
        body = r.content.decode().lower()
        self.assertNotIn("password", body)
        self.assertNotIn("pbkdf2", body)

    def test_get_has_the_same_shape_as_auth_me_including_permissions(self):
        mine = self.client.get("/api/users/me").data
        self.assertEqual(mine, self.client.get("/api/auth/me/").data)
        self.assertIn("permissions", mine)

    def test_requires_authentication(self):
        anon = APIClient()
        self.assertEqual(anon.get("/api/users/me").status_code, 401)
        self.assertEqual(anon.patch("/api/users/me", {"name": "X"}, format="json").status_code, 401)
        r = anon.put("/api/users/me/password/", {"currentPassword": base.PWD, "newPassword": NEW}, format="json")
        self.assertEqual(r.status_code, 401)

    def test_put_and_delete_are_not_allowed_on_me(self):
        self.assertEqual(self.client.put("/api/users/me", {"name": "X"}, format="json").status_code, 405)
        self.assertEqual(self.client.delete("/api/users/me").status_code, 405)

    def test_me_does_not_break_the_users_crud_routes(self):
        self.auth("admin@t.co")
        self.assertEqual(self.client.get("/api/users/").status_code, 200)
        self.assertEqual(self.client.get(f"/api/users/{self.me.pk}/").status_code, 200)

    # ---- PATCH
    def test_patch_updates_name_lastname_and_email(self):
        r = self.patch_me({"name": "  Laura ", "lastname": "Tascón", "email": "  LAURA@T.CO "})
        self.assertEqual(r.status_code, 200)
        self.me.refresh_from_db()
        self.assertEqual((self.me.user_name, self.me.user_lastname, self.me.user_email), ("Laura", "Tascón", "laura@t.co"))
        self.assertEqual(self.me.user_updated_by_id, self.me.pk)
        self.assertEqual(r.data["email"], "laura@t.co")
        self.assertIn("permissions", r.data)  # para que el frontend pueda refrescar la sesión sin perderlos

    def test_patch_is_partial_and_accepts_the_trailing_slash(self):
        self.assertEqual(self.patch_me({"name": "Solo"}, url="/api/users/me/").status_code, 200)
        self.me.refresh_from_db()
        self.assertEqual((self.me.user_name, self.me.user_lastname, self.me.user_email), ("Solo", "L", "autor@t.co"))

    def test_patch_with_the_own_email_is_allowed(self):
        self.assertEqual(self.patch_me({"email": "AUTOR@t.co"}).status_code, 200)

    def test_patch_with_a_taken_email_is_rejected_and_nothing_changes(self):
        r = self.patch_me({"name": "Cambio", "email": "ADMIN@t.co"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("email", r.data)
        self.me.refresh_from_db()
        self.assertEqual((self.me.user_name, self.me.user_email), ("N", "autor@t.co"))

    def test_patch_validation_errors_persist_nothing(self):
        cases = {
            "nombre vacío": {"name": ""},
            "nombre solo espacios": {"name": "   "},
            "nombre muy largo": {"name": "x" * 61},
            "apellido muy largo": {"lastname": "x" * 61},
            "correo inválido": {"email": "no-es-correo"},
        }
        for label, data in cases.items():
            with self.subTest(label):
                self.assertEqual(self.patch_me(data).status_code, 400)
                self.me.refresh_from_db()
                self.assertEqual((self.me.user_name, self.me.user_lastname, self.me.user_email), ("N", "L", "autor@t.co"))

    def test_patch_cannot_change_role_status_provider_or_password(self):
        admin_id = Profile.objects.get(profile_name="ADMIN").pk
        r = self.patch_me({
            "name": "Ok", "profile": admin_id, "profile_name": "ADMIN", "role": "ADMIN", "rol": "ADMIN",
            "perfil": "ADMIN", "active": False, "user_active": False, "provider": "GMAIL",
            "password": "Hacker.1234", "user_password": "x",
        })
        self.assertEqual(r.status_code, 200)  # lo permitido se aplica; lo demás se descarta
        self.me.refresh_from_db()
        self.assertEqual(self.me.user_name, "Ok")
        self.assertEqual(self.me.profile.profile_name, "AUTHOR")
        self.assertTrue(self.me.user_active)
        self.assertEqual(self.me.user_provider, "ACCOUNT")
        self.assertTrue(self.me.check_password(base.PWD))

    def test_patch_only_touches_the_session_user(self):
        r = self.patch_me({"id": self.admin.pk, "user_id": self.admin.pk, "email": "otro@t.co"})
        self.assertEqual(r.status_code, 200)
        self.admin.refresh_from_db()
        self.me.refresh_from_db()
        self.assertEqual(self.admin.user_email, "admin@t.co")
        self.assertEqual(self.me.user_email, "otro@t.co")


@override_settings(PASSWORD_CHANGE_RATE="1000/min")
class MyPasswordTests(base.BaseCase):
    def setUp(self):
        super().setUp()
        self.me = base.make_user("autor@t.co", "AUTHOR")
        self.auth("autor@t.co")

    def put(self, current=base.PWD, new=NEW, url="/api/users/me/password/", **extra):
        return self.client.put(url, {"currentPassword": current, "newPassword": new, **extra}, format="json")

    def test_changes_the_password(self):
        r = self.put(confirmPassword="se-ignora")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.login("autor@t.co", NEW).status_code, 200)
        self.assertEqual(self.login("autor@t.co", base.PWD).status_code, 401)
        body = r.content.decode()
        self.assertNotIn(NEW, body)
        self.assertNotIn(base.PWD, body)

    def test_works_without_the_trailing_slash(self):
        self.assertEqual(self.put(url="/api/users/me/password").status_code, 200)

    def test_new_password_is_stored_with_django_pbkdf2(self):
        self.put()
        self.me.refresh_from_db()
        self.assertTrue(self.me.user_password.startswith("pbkdf2_sha256$"))
        self.assertNotIn(NEW, self.me.user_password)

    def test_current_session_stays_valid_after_the_change(self):
        """No hay lista de revocación: los tokens ya emitidos siguen sirviendo hasta que venzan."""
        self.put()
        self.assertEqual(self.client.get("/api/users/me").status_code, 200)

    def test_wrong_current_password_is_400_and_never_401(self):
        r = self.put(current="Incorrecta.1")
        self.assertEqual(r.status_code, 400)  # un 401 cerraría la sesión en el frontend
        self.assertIn("currentPassword", r.data)
        self.assertEqual(self.login("autor@t.co", base.PWD).status_code, 200)

    def test_weak_new_password_is_rejected(self):
        for weak in ("123", "sinmayuscula1!", "SINMINUSCULA1!", "SinNumero!!", "SinEspecial1A"):
            with self.subTest(weak):
                r = self.put(new=weak)
                self.assertEqual(r.status_code, 400)
                self.assertIn("newPassword", r.data)
        self.assertEqual(self.login("autor@t.co", base.PWD).status_code, 200)

    def test_new_password_must_differ_from_the_current_one(self):
        r = self.put(new=base.PWD)
        self.assertEqual(r.status_code, 400)
        self.assertIn("newPassword", r.data)

    def test_missing_fields_are_required(self):
        for field in ("currentPassword", "newPassword"):
            with self.subTest(field):
                data = {"currentPassword": base.PWD, "newPassword": NEW}
                data.pop(field)
                self.assertEqual(self.client.put("/api/users/me/password/", data, format="json").status_code, 400)

    def test_only_put_is_allowed(self):
        url = "/api/users/me/password/"
        self.assertEqual(self.client.get(url).status_code, 405)
        self.assertEqual(self.client.patch(url, {}, format="json").status_code, 405)
        self.assertEqual(self.client.post(url, {}, format="json").status_code, 405)

    def test_accounts_without_own_password_cannot_change_it(self):
        self.me.user_provider = User.PROVIDER_GMAIL
        self.me.save()
        self.assertEqual(self.put().status_code, 400)

    def test_other_users_are_not_affected(self):
        self.put()
        self.assertEqual(self.login("admin@t.co", base.PWD).status_code, 200)

    def test_pending_recovery_pins_stop_working(self):
        with patch("accounts.views.send_recovery_pin_email") as sender:
            self.client.post("/api/auth/password/forgot/", {"email": "autor@t.co"}, format="json")
        pin = sender.call_args.args[1]
        self.assertEqual(self.put().status_code, 200)
        r = self.client.post(
            "/api/auth/password/reset/", {"email": "autor@t.co", "pin": pin, "password": "Otra.Clave9"}, format="json"
        )
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.login("autor@t.co", NEW).status_code, 200)


@override_settings(PASSWORD_CHANGE_RATE="3/min")
class MyPasswordThrottleTests(base.BaseCase):
    def test_repeated_wrong_attempts_are_limited(self):
        base.make_user("autor@t.co", "AUTHOR")
        self.auth("autor@t.co")
        codes = [
            self.client.put(
                "/api/users/me/password/", {"currentPassword": "Mala.Clave1", "newPassword": NEW}, format="json"
            ).status_code
            for _ in range(4)
        ]
        self.assertEqual(codes, [400, 400, 400, 429])
