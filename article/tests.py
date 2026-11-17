from rest_framework.test import APITestCase
from rest_framework import status
from django.core.management import call_command
from accounts.models import User, Profile
from .models import Article, Topic, ArticleReviewer

class ArticleAvalTests(APITestCase):
    def setUp(self):
        # NUEVO: Llenamos la base de datos con los perfiles (ADMIN, MEMBER, AUTHOR)
        call_command("seed_accounts")

        # Creamos un tópico
        self.topic = Topic.objects.create(topic_subject="Ciencias")
        
        # Creamos un usuario autor
        self.author = User.objects.create(user_name="Autor", user_lastname="Test", user_email="autor@test.com")
        self.author.profiles.add(Profile.objects.get(profile_name="AUTHOR"))
        
        # Creamos un artículo
        self.article = Article.objects.create(
            article_subject="Artículo de prueba",
            article_description="Descripción",
            topic_id=self.topic,
            article="Contenido",
            article_created_by=self.author
        )

        # Creamos un usuario evaluador (MEMBER)
        self.reviewer = User.objects.create(user_name="Revisor", user_lastname="Test", user_email="revisor@test.com")
        self.reviewer.profiles.add(Profile.objects.get(profile_name="MEMBER"))
        
        # Asignamos al revisor al artículo
        self.reviewer_assignment = ArticleReviewer.objects.create(
            article=self.article,
            user=self.reviewer,
            status="IN_REVIEW"
        )

    def test_emit_aval_as_assigned_reviewer(self):
        self.client.force_authenticate(user=self.reviewer)
        url = f"/api/articles/{self.article.article_id}/aval-presentation/"
        response = self.client.post(url, {"comment": "Buen trabajo, aprobado."}, format="json")
        
        # Ahora esperamos un PDF (status 200 y tipo de contenido application/pdf)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertIn(f"Aval_Articulo_{self.article.article_id}.pdf", response['Content-Disposition'])

        # Validar que en la BD se guardó el estado
        self.reviewer_assignment.refresh_from_db()
        self.assertEqual(self.reviewer_assignment.status, "FOR_PRESENTATION")
        self.assertEqual(self.reviewer_assignment.comment, "Buen trabajo, aprobado.")

    def test_emit_aval_as_unauthorized_author(self):
        self.client.force_authenticate(user=self.author)
        url = f"/api/articles/{self.article.article_id}/aval-presentation/"
        response = self.client.post(url, {}, format="json")
        
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_get_corrected_version(self):
        self.client.force_authenticate(user=self.reviewer)
        url = f"/api/articles/{self.article.article_id}/corrected-version/"
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["article_id"], self.article.article_id)