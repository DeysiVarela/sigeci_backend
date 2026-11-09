import json
from django.test import TestCase, Client
from django.urls import reverse
from .models import Article


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
