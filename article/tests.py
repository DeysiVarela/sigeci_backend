from django.core.management import call_command
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import Profile, User

from .models import Article, ArticleAttached, ArticleReviewer, Topic


def make_user(email, profile, name="Test"):
    user = User.objects.create(user_name=name, user_lastname="User", user_email=email)
    user.profiles.add(Profile.objects.get(profile_name=profile))
    return user


class ArticleSetupMixin:
    def setUp(self):
        call_command("seed_accounts", verbosity=0)
        self.topic = Topic.objects.create(topic_subject="Ciencias")
        self.author = make_user("autor@test.com", "AUTHOR", "Autor")
        self.other_author = make_user("otro@test.com", "AUTHOR", "Otro")
        self.reviewer = make_user("revisor@test.com", "MEMBER", "Revisor")
        self.member = make_user("member@test.com", "MEMBER", "Miembro")
        self.admin = make_user("admin@test.com", "ADMIN", "Admin")
        self.article = Article.objects.create(
            article_subject="Artículo de prueba",
            topic_id=self.topic,
            article="Contenido",
            article_created_by=self.author,
        )
        self.assignment = ArticleReviewer.objects.create(
            article=self.article, user=self.reviewer, status="IN_REVIEW"
        )
        self.aval_url = f"/api/articles/{self.article.article_id}/aval-presentation/"
        self.corrected_url = f"/api/articles/{self.article.article_id}/corrected-version/"


class AvalPresentationTests(ArticleSetupMixin, APITestCase):
    # --- éxito ---
    def test_assigned_reviewer_emits_aval_and_gets_pdf(self):
        self.client.force_authenticate(self.reviewer)
        r = self.client.post(self.aval_url, {"comment": "Buen trabajo."}, format="json")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r["Content-Type"], "application/pdf")
        self.assertTrue(r.content.startswith(b"%PDF"))
        self.assertIn(f"Aval_Articulo_{self.article.article_id}.pdf", r["Content-Disposition"])
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.status, "FOR_PRESENTATION")
        self.assertEqual(self.assignment.comment, "Buen trabajo.")

    def test_audit_fields_are_set(self):  # CA-04
        self.client.force_authenticate(self.reviewer)
        self.client.post(self.aval_url, {}, format="json")
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.article_reviewer_updated_by, self.reviewer)
        self.assertIsNotNone(self.assignment.article_reviewer_updated_at)

    def test_admin_not_assigned_creates_own_row_without_touching_others(self):
        self.client.force_authenticate(self.admin)
        r = self.client.post(self.aval_url, {"comment": "Comité"}, format="json")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.status, "IN_REVIEW")
        row = ArticleReviewer.objects.get(article=self.article, user=self.admin)
        self.assertEqual(row.status, "FOR_PRESENTATION")
        self.assertEqual(row.article_reviewer_created_by, self.admin)
        self.assertEqual(row.article_reviewer_updated_by, self.admin)
        self.assertIsNotNone(row.article_reviewer_updated_at)

    def test_member_not_assigned_can_emit_aval(self):  # CA-03: MEMBER es comité
        self.client.force_authenticate(self.member)
        r = self.client.post(self.aval_url, {}, format="json")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertTrue(ArticleReviewer.objects.filter(article=self.article, user=self.member).exists())

    def test_committee_does_not_overwrite_rejection_of_other_reviewer(self):
        self.assignment.status = "REJECTED"
        self.assignment.comment = "Rechazado"
        self.assignment.save()
        self.client.force_authenticate(self.admin)
        self.client.post(self.aval_url, {"comment": "ok"}, format="json")
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.status, "REJECTED")
        self.assertEqual(self.assignment.comment, "Rechazado")

    def test_committee_with_soft_deleted_row_does_not_500(self):
        ArticleReviewer.objects.create(
            article=self.article, user=self.admin, article_reviewer_delete=True, status="REJECTED"
        )
        self.client.force_authenticate(self.admin)
        r = self.client.post(self.aval_url, {}, format="json")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        row = ArticleReviewer.objects.get(article=self.article, user=self.admin)
        self.assertFalse(row.article_reviewer_delete)
        self.assertEqual(row.status, "FOR_PRESENTATION")

    # --- permisos / error ---
    def test_unauthenticated_gets_401(self):
        self.assertEqual(self.client.post(self.aval_url, {}, format="json").status_code, 401)

    def test_unrelated_author_gets_403(self):
        self.client.force_authenticate(self.other_author)
        self.assertEqual(self.client.post(self.aval_url, {}, format="json").status_code, 403)
        self.assertFalse(ArticleReviewer.objects.filter(user=self.other_author).exists())

    def test_author_cannot_self_aval(self):
        self.client.force_authenticate(self.author)
        self.assertEqual(self.client.post(self.aval_url, {}, format="json").status_code, 403)

    def test_committee_author_cannot_self_aval(self):
        art = Article.objects.create(
            article_subject="Mío", topic_id=self.topic, article="x", article_created_by=self.member
        )
        self.client.force_authenticate(self.member)
        r = self.client.post(f"/api/articles/{art.article_id}/aval-presentation/", {}, format="json")
        self.assertEqual(r.status_code, 403)

    def test_inactive_assignment_of_non_committee_gets_403(self):
        reviewer_author = make_user("ra@test.com", "AUTHOR")
        ArticleReviewer.objects.create(
            article=self.article, user=reviewer_author, article_reviewer_active=False
        )
        self.client.force_authenticate(reviewer_author)
        self.assertEqual(self.client.post(self.aval_url, {}, format="json").status_code, 403)

    def test_inactive_member_profile_is_not_committee(self):
        p = Profile.objects.get(profile_name="MEMBER")
        p.profile_active = False
        p.save()
        self.client.force_authenticate(self.member)
        self.assertEqual(self.client.post(self.aval_url, {}, format="json").status_code, 403)

    def test_nonexistent_article_404(self):
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.post("/api/articles/99999/aval-presentation/", {}, format="json").status_code, 404)

    def test_soft_deleted_article_404(self):
        self.article.article_delete = True
        self.article.save()
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.post(self.aval_url, {}, format="json").status_code, 404)

    # --- validación de entrada ---
    def test_body_as_list_returns_400_not_500(self):
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.post(self.aval_url, [1, 2], format="json").status_code, 400)

    def test_comment_too_long_returns_400(self):
        self.client.force_authenticate(self.admin)
        r = self.client.post(self.aval_url, {"comment": "A" * 1001}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_comment_wrong_type_returns_400(self):
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.post(self.aval_url, {"comment": {"a": 1}}, format="json").status_code, 400)

    # --- transiciones ---
    def test_blocked_states_return_409(self):
        self.client.force_authenticate(self.reviewer)
        for state in ("REJECTED", "FOR_PUBLICATION"):
            self.assignment.status = state
            self.assignment.save()
            r = self.client.post(self.aval_url, {}, format="json")
            self.assertEqual(r.status_code, status.HTTP_409_CONFLICT, state)
            self.assignment.refresh_from_db()
            self.assertEqual(self.assignment.status, state)

    def test_double_post_is_idempotent(self):
        self.client.force_authenticate(self.reviewer)
        self.assertEqual(self.client.post(self.aval_url, {}, format="json").status_code, 200)
        self.assertEqual(self.client.post(self.aval_url, {}, format="json").status_code, 200)
        self.assertEqual(ArticleReviewer.objects.filter(article=self.article, user=self.reviewer).count(), 1)


class CorrectedVersionTests(ArticleSetupMixin, APITestCase):
    def test_unauthenticated_gets_401(self):
        self.assertEqual(self.client.get(self.corrected_url).status_code, 401)

    def test_author_owner_can_view(self):
        self.client.force_authenticate(self.author)
        r = self.client.get(self.corrected_url)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["article_id"], self.article.article_id)

    def test_assigned_reviewer_can_view(self):
        self.client.force_authenticate(self.reviewer)
        self.assertEqual(self.client.get(self.corrected_url).status_code, 200)

    def test_committee_not_assigned_can_view(self):
        for u in (self.admin, self.member):
            self.client.force_authenticate(u)
            self.assertEqual(self.client.get(self.corrected_url).status_code, 200)

    def test_unrelated_author_gets_403(self):
        self.client.force_authenticate(self.other_author)
        self.assertEqual(self.client.get(self.corrected_url).status_code, 403)

    def test_inactive_assignment_of_non_committee_gets_403(self):
        ra = make_user("ra@test.com", "AUTHOR")
        ArticleReviewer.objects.create(article=self.article, user=ra, article_reviewer_delete=True)
        self.client.force_authenticate(ra)
        self.assertEqual(self.client.get(self.corrected_url).status_code, 403)

    def test_returns_latest_active_attachment(self):
        ArticleAttached.objects.create(article=self.article, article_attached_url="https://x/v1.pdf", article_attached_version="1.0")
        ArticleAttached.objects.create(article=self.article, article_attached_url="https://x/v2.pdf", article_attached_version="2.0")
        ArticleAttached.objects.create(
            article=self.article, article_attached_url="https://x/v3.pdf",
            article_attached_version="3.0", article_attached_delete=True,
        )
        self.client.force_authenticate(self.author)
        r = self.client.get(self.corrected_url)
        self.assertEqual(r.data["corrected_version"]["article_attached_version"], "2.0")

    def test_no_attachments_returns_null(self):
        self.client.force_authenticate(self.author)
        self.assertIsNone(self.client.get(self.corrected_url).data["corrected_version"])

    def test_nonexistent_and_deleted_article_404(self):
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.get("/api/articles/99999/corrected-version/").status_code, 404)
        self.article.article_delete = True
        self.article.save()
        self.assertEqual(self.client.get(self.corrected_url).status_code, 404)