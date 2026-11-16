"""SCRUM-138: múltiples roles por usuario."""  
from . import tests as base  
from .models import Profile, User  


class MultiRoleTests(base.BaseCase):  
    def setUp(self):
        super().setUp()
        self.auth("admin@t.co")

    def pid(self, name):
        return Profile.objects.get(profile_name=name).pk

    def body(self, email, roles):
        return {"name": "Ana", "lastname": "Paz", "email": email, "password": base.PWD,
                "profiles": [self.pid(r) for r in roles]}

    def names(self, user):
        return sorted(user.profiles.values_list("profile_name", flat=True))

    def test_create_with_two_roles_and_edit_down_to_one(self):
        r = self.client.post("/api/users/", self.body("dos@t.co", ("AUTHOR", "MEMBER")), format="json")
        self.assertEqual(r.status_code, 201)
        self.assertEqual(sorted(p["name"] for p in r.data["profiles"]), ["AUTHOR", "MEMBER"])
        uid = r.data["id"]
        r = self.client.patch(f"/api/users/{uid}/", {"profiles": [self.pid("AUTHOR")]}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.names(User.objects.get(pk=uid)), ["AUTHOR"])

    def test_empty_or_non_list_profiles_are_rejected(self):
        for value in ([], self.pid("AUTHOR"), None):
            with self.subTest(value=value):
                body = self.body("x@t.co", ("AUTHOR",))
                body["profiles"] = value
                self.assertEqual(self.client.post("/api/users/", body, format="json").status_code, 400)
        self.assertFalse(User.objects.filter(user_email="x@t.co").exists())

    def test_permissions_are_the_union_of_all_roles(self):
        user = base.make_user("multi@t.co", "AUTHOR")
        user.profiles.add(Profile.objects.get(profile_name="MEMBER"))
        perms = user.permissions_map()
        self.assertEqual(sorted(user.profiles.values_list("profile_name", flat=True)), ["AUTHOR", "MEMBER"])
        self.assertTrue(user.has_perm_on("user", "view"))  # lo da MEMBER
        self.assertTrue(user.has_perm_on("article", "create"))  # lo da AUTHOR
        for action, plist in perms.items():
            self.assertEqual(len(plist), len(set(plist)), action)  # sin duplicados

    def test_non_admin_cannot_assign_admin_among_several_roles(self):
        self.auth("member@t.co")
        r = self.client.post("/api/users/", self.body("a2@t.co", ("AUTHOR", "ADMIN")), format="json")
        self.assertEqual(r.status_code, 403)
        self.assertFalse(User.objects.filter(user_email="a2@t.co").exists())

    def test_admin_cannot_change_their_own_roles(self):
        r = self.client.patch(
            f"/api/users/{self.admin.pk}/", {"profiles": [self.pid("ADMIN"), self.pid("MEMBER")]}, format="json"
        )
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.names(User.objects.get(pk=self.admin.pk)), ["ADMIN"])

    def test_unchanged_roles_do_not_need_role_permission(self):
        # el frontend puede reenviar los mismos roles sin que cuente como "cambiar roles"
        self.auth("member@t.co")
        author = base.make_user("autor@t.co", "AUTHOR")
        r = self.client.patch(f"/api/users/{author.pk}/", {"name": "Nuevo", "profiles": [self.pid("AUTHOR")]}, format="json")
        self.assertEqual(r.status_code, 200)

    def test_filter_by_profile_does_not_duplicate_multi_role_users(self):
        user = base.make_user("multi@t.co", "AUTHOR")
        user.profiles.add(Profile.objects.get(profile_name="MEMBER"))
        r = self.client.get(f"/api/users/?profile={self.pid('MEMBER')}")
        emails = [u["email"] for u in r.data["results"]]
        self.assertEqual(emails.count("multi@t.co"), 1)
        self.assertEqual(r.data["count"], len(emails))

    def test_public_register_still_creates_a_single_author_role(self):
        self.client.credentials()
        r = self.client.post("/api/auth/register", {"name": "Ana", "lastname": "Paz", "email": "reg@t.co",
                                                    "password": base.PWD}, format="json")
        self.assertEqual(r.status_code, 201)
        self.assertEqual(self.names(User.objects.get(user_email="reg@t.co")), ["AUTHOR"])