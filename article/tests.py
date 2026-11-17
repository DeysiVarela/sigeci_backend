from django.core.management import call_command
from django.core.files.uploadedfile import SimpleUploadedFile
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
        # URLs para SCRUM-31
        self.final_submission_url = f"/api/articles/{self.article.article_id}/final-submission/"
        self.aval_publication_url = f"/api/articles/{self.article.article_id}/aval-publication/"


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


# ==============================================================================
# NUEVOS TESTS PARA LA SCRUM-31 (Final Submission & Aval Publication)
# ==============================================================================
class FinalSubmissionAndPublicationTests(ArticleSetupMixin, APITestCase):
    
    def get_mock_files(self):
        pdf = SimpleUploadedFile("test.pdf", b"%PDF-1.4 archivo de prueba", content_type="application/pdf")
        img = SimpleUploadedFile("test.png", b"imagen de prueba", content_type="image/png")
        txt = SimpleUploadedFile("test.txt", b"texto plano", content_type="text/plain")
        return pdf, img, txt

    # --- Tests para final-submission ---
    def test_final_submission_success(self):
        self.client.force_authenticate(self.author)
        pdf, img, _ = self.get_mock_files()
        
        data = {"final_pdf": pdf, "copyright_pdf": img}
        r = self.client.post(self.final_submission_url, data, format="multipart")
        
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.article.refresh_from_db()
        self.assertIsNotNone(self.article.article_copyright_url)
        self.assertTrue(ArticleAttached.objects.filter(article=self.article, article_attached_version="Final").exists())

    def test_final_submission_wrong_author_gets_403(self):
        self.client.force_authenticate(self.other_author)
        pdf, img, _ = self.get_mock_files()
        r = self.client.post(self.final_submission_url, {"final_pdf": pdf, "copyright_pdf": img}, format="multipart")
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)

    def test_final_submission_invalid_file_type_gets_400(self):
        self.client.force_authenticate(self.author)
        _, _, txt = self.get_mock_files()
        r = self.client.post(self.final_submission_url, {"final_pdf": txt, "copyright_pdf": txt}, format="multipart")
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    # --- Tests para aval-publication ---
    def test_aval_publication_success(self):
        # 1. Primero el autor sube el copyright
        self.client.force_authenticate(self.author)
        pdf, img, _ = self.get_mock_files()
        self.client.post(self.final_submission_url, {"final_pdf": pdf, "copyright_pdf": img}, format="multipart")
        
        # 2. El comité da el aval (Usamos self.reviewer en vez de self.admin)
        self.client.force_authenticate(self.reviewer)
        r = self.client.post(self.aval_publication_url, {}, format="json")
        
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r["Content-Type"], "application/pdf")
        self.assertTrue(r.content.startswith(b"%PDF"))
        
        self.article.refresh_from_db()
        self.assertTrue(self.article.is_eligible_for_proceedings)
        self.assertIsNotNone(self.article.verification_code)
        
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.status, "FOR_PUBLICATION")

    def test_aval_publication_blocked_without_copyright(self):
        # Intentamos avalar sin que el autor haya subido nada
        self.client.force_authenticate(self.admin)
        r = self.client.post(self.aval_publication_url, {}, format="json")
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("copyright", r.data["detail"].lower())

    def test_aval_publication_author_cannot_self_aval(self):
        # El autor sube su copyright
        self.client.force_authenticate(self.author)
        pdf, img, _ = self.get_mock_files()
        self.client.post(self.final_submission_url, {"final_pdf": pdf, "copyright_pdf": img}, format="multipart")
        
        # El autor intenta darse el aval a sí mismo
        r = self.client.post(self.aval_publication_url, {}, format="json")
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)


# ==============================================================================
# TESTS SCRUM-30: POST corrected-version (el autor sube su versión corregida)
# ==============================================================================
class CorrectedVersionUploadTests(ArticleSetupMixin, APITestCase):

    def pdf(self, name="corregido.pdf", content=b"%PDF-1.4 corregido"):
        return SimpleUploadedFile(name, content, content_type="application/pdf")

    def test_author_uploads_corrected_version(self):
        self.client.force_authenticate(self.author)
        r = self.client.post(self.corrected_url, {"corrected_pdf": self.pdf()}, format="multipart")
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        att = ArticleAttached.objects.get(article=self.article, article_attached_version="Corregida")
        self.assertEqual(att.article_attached_created_by, self.author)
        self.assertEqual(r.data["corrected_version"]["article_attached_id"], att.article_attached_id)

    def test_uploaded_version_is_returned_by_get(self):
        self.client.force_authenticate(self.author)
        self.client.post(self.corrected_url, {"corrected_pdf": self.pdf()}, format="multipart")
        r = self.client.get(self.corrected_url)
        self.assertEqual(r.data["corrected_version"]["article_attached_version"], "Corregida")

    def test_audit_fields_updated(self):
        self.client.force_authenticate(self.author)
        self.client.post(self.corrected_url, {"corrected_pdf": self.pdf()}, format="multipart")
        self.article.refresh_from_db()
        self.assertEqual(self.article.article_updated_by, self.author)
        self.assertIsNotNone(self.article.article_updated_at)

    def test_unauthenticated_gets_401(self):
        r = self.client.post(self.corrected_url, {"corrected_pdf": self.pdf()}, format="multipart")
        self.assertEqual(r.status_code, 401)

    def test_non_owner_gets_403_and_nothing_saved(self):
        for u in (self.other_author, self.admin, self.member, self.reviewer):
            self.client.force_authenticate(u)
            r = self.client.post(self.corrected_url, {"corrected_pdf": self.pdf()}, format="multipart")
            self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(ArticleAttached.objects.filter(article=self.article).exists())

    def test_non_pdf_gets_400(self):
        self.client.force_authenticate(self.author)
        txt = SimpleUploadedFile("a.txt", b"texto", content_type="text/plain")
        r = self.client.post(self.corrected_url, {"corrected_pdf": txt}, format="multipart")
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("corrected_pdf", r.data)

    def test_empty_and_oversized_gets_400(self):
        self.client.force_authenticate(self.author)
        empty = self.pdf(content=b"")
        r = self.client.post(self.corrected_url, {"corrected_pdf": empty}, format="multipart")
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        big = self.pdf(content=b"0" * (10 * 1024 * 1024 + 1))
        r = self.client.post(self.corrected_url, {"corrected_pdf": big}, format="multipart")
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_missing_file_gets_400(self):
        self.client.force_authenticate(self.author)
        r = self.client.post(self.corrected_url, {}, format="multipart")
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_nonexistent_and_deleted_article_404(self):
        self.client.force_authenticate(self.author)
        r = self.client.post("/api/articles/99999/corrected-version/", {"corrected_pdf": self.pdf()}, format="multipart")
        self.assertEqual(r.status_code, 404)
        self.article.article_delete = True
        self.article.save()
        r = self.client.post(self.corrected_url, {"corrected_pdf": self.pdf()}, format="multipart")
        self.assertEqual(r.status_code, 404)