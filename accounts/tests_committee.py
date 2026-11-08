"""MEMBER = miembro del comité científico: gestiona usuarios, pero no crea ni toca administradores."""
from . import tests as base
from .models import Profile, User


class CommitteeMemberTests(base.BaseCase):
    def setUp(self):
        super().setUp()
        self.author = base.make_user("autor@t.co", "AUTHOR")
        self.auth("member@t.co")  # self.member es MEMBER (comité)

    def pid(self, name):
        return Profile.objects.get(profile_name=name).pk

    def new_user(self, email, profile):
        return {"name": "Ana", "lastname": "Paz", "email": email, "password": base.PWD, "profile": self.pid(profile)}

    def test_can_list_users(self):
        self.assertEqual(self.client.get("/api/users/").status_code, 200)

    def test_can_create_users_with_non_admin_roles(self):
        for i, role in enumerate(("AUTHOR", "MEMBER")):
            r = self.client.post("/api/users/", self.new_user(f"nuevo{i}@t.co", role), format="json")
            self.assertEqual(r.status_code, 201, role)
            self.assertEqual(r.data["profile_name"], role)

    def test_cannot_create_admin_users(self):
        r = self.client.post("/api/users/", self.new_user("admin2@t.co", "ADMIN"), format="json")
        self.assertEqual(r.status_code, 403)
        self.assertFalse(User.objects.filter(user_email="admin2@t.co").exists())

    def test_cannot_assign_admin_role_to_existing_user(self):
        r = self.client.patch(f"/api/users/{self.author.pk}/", {"profile": self.pid("ADMIN")}, format="json")
        self.assertEqual(r.status_code, 403)
        self.author.refresh_from_db()
        self.assertEqual(self.author.profile.profile_name, "AUTHOR")

    def test_can_edit_change_role_deactivate_and_delete_non_admin_users(self):
        url = f"/api/users/{self.author.pk}/"
        self.assertEqual(self.client.patch(url, {"name": "Nuevo"}, format="json").status_code, 200)
        self.assertEqual(self.client.patch(url, {"profile": self.pid("MEMBER")}, format="json").status_code, 200)
        self.assertEqual(self.client.patch(url, {"active": False}, format="json").status_code, 200)
        self.assertEqual(self.client.delete(url).status_code, 204)

    def test_cannot_modify_or_delete_admin_accounts(self):
        url = f"/api/users/{self.admin.pk}/"
        self.assertEqual(self.client.patch(url, {"name": "X"}, format="json").status_code, 403)
        self.assertEqual(self.client.patch(url, {"active": False}, format="json").status_code, 403)
        self.assertEqual(self.client.delete(url).status_code, 403)
        self.admin.refresh_from_db()
        self.assertEqual(self.admin.user_name, "N")
        self.assertTrue(self.admin.user_active)
        self.assertFalse(self.admin.user_delete)

    def test_author_still_cannot_manage_users(self):
        self.auth("autor@t.co")
        self.assertEqual(self.client.get("/api/users/").status_code, 403)

    def test_admin_can_still_create_admin_users(self):
        self.auth("admin@t.co")
        r = self.client.post("/api/users/", self.new_user("admin2@t.co", "ADMIN"), format="json")
        self.assertEqual(r.status_code, 201)
