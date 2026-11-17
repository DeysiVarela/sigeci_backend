import json
from django.test import TestCase, Client, override_settings
from django.urls import reverse
from datetime import date
from rest_framework.test import APITestCase
from django.core.management import call_command
from accounts.models import Profile, User
from .models import Article, ArticleAttached, ArticleReviewer, Topic


class ArticleCrudTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.article = Article.objects.create(
            article_subject="IA en la Medicina",
            article_description="Investigación de modelos convolucionales",
            topic_id=1,
            article="Contenido completo del artículo científico.",
            article_date="2026-03-15",
        )

    def test_list_articles(self):
        response = self.client.get("/api/v1/articles/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["article_subject"], "IA en la Medicina")

    def test_detail_article(self):
        response = self.client.get(f"/api/v1/articles/{self.article.article_id}/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["article_id"], self.article.article_id)

    def test_create_article_via_method_url(self):
        payload = {
            "article_subject": "Seguridad Informática",
            "article_description": "Criptografía asimétrica",
            "topic_id": 2,
            "article": "Cuerpo del documento técnico.",
            "article_date": "2026-04-01",
        }
        response = self.client.post(
            "/api/v1/articles/create/",
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["article_subject"], "Seguridad Informática")
        self.assertTrue(Article.objects.filter(article_subject="Seguridad Informática").exists())

    def test_update_article_via_method_url(self):
        payload = {
            "article_subject": "IA en Medicina Actualizada",
        }
        response = self.client.post(
            f"/api/v1/articles/{self.article.article_id}/update/",
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.article.refresh_from_db()
        self.assertEqual(self.article.article_subject, "IA en Medicina Actualizada")

    def test_delete_article_via_method_url(self):
        response = self.client.post(f"/api/v1/articles/{self.article.article_id}/delete/")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Article.objects.filter(pk=self.article.article_id).exists())


@override_settings(CAPTCHA_REQUIRED=False)
class EvaluationAssignmentTests(APITestCase):
    def setUp(self):
        call_command("seed_accounts")
        self.member = self.make_user("jurado@sigeci.test", "MEMBER")
        self.other_member = self.make_user("otro@sigeci.test", "MEMBER")
        self.topic = Topic.objects.create(topic_subject="Inteligencia Artificial")
        self.article = Article.objects.create(
            article_subject="Artículo asignado",
            article_description="Resumen científico",
            topic_id=self.topic,
            article="Contenido",
            article_created_by=self.member,
        )
        self.attachment = ArticleAttached.objects.create(
            article=self.article,
            article_attached_url="https://storage.example.test/signed-article.pdf",
        )
        self.review = ArticleReviewer.objects.create(
            article=self.article,
            article_attached=self.attachment,
            user=self.member,
            status="PENDING",
            evaluation_deadline=date(2026, 12, 1),
        )
        self.other_review = ArticleReviewer.objects.create(
            article=self.article,
            article_attached=self.attachment,
            user=self.other_member,
            status="PENDING",
        )

    def make_user(self, email, profile_name):
        user = User(
            user_name="Jur",
            user_lastname="ado",
            user_email=email,
            profile=Profile.objects.get(profile_name=profile_name),
        )
        user.set_password("Clave.Segura1")
        user.save()
        return user

    def authenticate(self, user):
        response = self.client.post(
            "/api/auth/login/",
            {"email": user.user_email, "password": "Clave.Segura1"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {response.data['access']}"
        )

    def test_member_only_sees_own_assignments(self):
        self.authenticate(self.member)
        response = self.client.get("/api/evaluations/assigned/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["id"], self.review.article_reviewer_id)
        self.assertEqual(response.data[0]["pdfSignedUrl"], "https://storage.example.test/signed-article.pdf")

    def test_member_cannot_view_another_members_review(self):
        self.authenticate(self.member)
        response = self.client.get(
            f"/api/evaluations/assigned/{self.other_review.article_reviewer_id}/"
        )
        self.assertEqual(response.status_code, 404)

    def test_verdict_requires_comments_and_persists(self):
        self.authenticate(self.member)
        url = f"/api/evaluations/assigned/{self.review.article_reviewer_id}/verdict/"

        missing_comments = self.client.post(url, {"verdict": "APROBADO"}, format="json")
        self.assertEqual(missing_comments.status_code, 400)

        approved = self.client.post(
            url,
            {"verdict": "APROBADO", "comments": "Metodología sólida y resultados reproducibles."},
            format="json",
        )
        self.assertEqual(approved.status_code, 200)
        self.review.refresh_from_db()
        self.assertEqual(self.review.status, "APPROVED")
        self.assertEqual(self.review.comment, "Metodología sólida y resultados reproducibles.")

        repeated = self.client.post(
            url,
            {"verdict": "RECHAZADO", "comments": "Nueva intención no permitida."},
            format="json",
        )
        self.assertEqual(repeated.status_code, 409)
