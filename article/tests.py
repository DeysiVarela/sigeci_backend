import json
from django.test import TestCase, Client, override_settings
from django.urls import reverse
from datetime import date, time
from rest_framework.test import APITestCase
from django.core.cache import cache
from django.core.management import call_command
from accounts.models import Profile, User
from .models import Article, ArticleAttached, ArticleReviewer, Event, Schedule, Topic


@override_settings(CAPTCHA_REQUIRED=False)
class ArticleCrudTests(TestCase):
    def setUp(self):
        cache.clear()  # el login tiene límite de 10/min (throttle 'auth'); se reinicia por test
        self.client = Client()
        call_command("seed_accounts")
        self.topic = Topic.objects.create(topic_subject="Inteligencia Artificial")
        admin_profile = Profile.objects.get(profile_name="ADMIN")
        self.admin = User(
            user_name="Admin",
            user_lastname="SIGECI",
            user_email="admin.article@test.local",
        )
        self.admin.set_password("Clave.Segura1")
        self.admin.save()
        self.admin.profiles.add(admin_profile)
        login = self.client.post(
            "/api/auth/login/",
            {"email": self.admin.user_email, "password": "Clave.Segura1"},
            content_type="application/json",
        )
        self.assertEqual(login.status_code, 200)
        self.access = login.json()["access"]
        self.auth_headers = {
            "HTTP_AUTHORIZATION": f"Bearer {self.access}",
            "HTTP_PROFILE": str(admin_profile.profile_id),
        }
        self.article = Article.objects.create(
            article_subject="IA en la Medicina",
            article_description="Investigación de modelos convolucionales",
            topic_id=self.topic,
            article="Contenido completo del artículo científico.",
            article_date="2026-03-15",
            article_created_by=self.admin,
        )

    def test_list_articles(self):
        response = self.client.get("/api/v1/article/", **self.auth_headers)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        articles = data["data"]
        self.assertTrue(any(a["article_subject"] == "IA en la Medicina" for a in articles))

    def test_detail_article(self):
        response = self.client.get(f"/api/v1/article/{self.article.article_id}/", **self.auth_headers)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["data"]["article_id"], self.article.article_id)

    def test_create_article_via_method_url(self):
        payload = {
            "article_subject": "Seguridad Informática",
            "article_description": "Criptografía asimétrica",
            "topic_id": self.topic.topic_id,
            "article": "Cuerpo del documento técnico.",
            "article_date": "2026-04-01",
            "main_author_affiliation": "Universidad del Valle",
            "coauthors": [
                {"name": "Ana", "lastname": "Pérez", "affiliation": "Universidad Nacional", "email": "Ana.Perez@test.local"},
            ],
        }
        response = self.client.post(
            "/api/v1/article/create/",
            data=json.dumps(payload),
            content_type="application/json",
            **self.auth_headers,
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["data"]["article_subject"], "Seguridad Informática")
        self.assertTrue(Article.objects.filter(article_subject="Seguridad Informática").exists())
        authors = data["data"]["authors"]
        self.assertEqual(len(authors), 2)
        self.assertTrue(authors[0]["is_corresponding"])
        self.assertEqual(authors[0]["email"], self.admin.user_email)
        self.assertEqual(authors[0]["affiliation"], "Universidad del Valle")
        self.assertFalse(authors[1]["is_corresponding"])
        self.assertEqual(authors[1]["email"], "ana.perez@test.local")

    def _create_payload(self, **extra):
        payload = {
            "article_subject": "Artículo con autores",
            "topic_id": self.topic.topic_id,
            "article": "Contenido.",
            "main_author_affiliation": "Universidad del Valle",
        }
        payload.update(extra)
        return payload

    def _post_create(self, payload):
        return self.client.post(
            "/api/v1/article/create/",
            data=json.dumps(payload),
            content_type="application/json",
            **self.auth_headers,
        )

    def test_create_article_validates_authors(self):
        invalid_cases = {
            "sin afiliación del autor principal": self._create_payload(main_author_affiliation=""),
            "coautor sin correo": self._create_payload(coauthors=[{"name": "Ana", "affiliation": "UV"}]),
            "correo repetido": self._create_payload(coauthors=[
                {"name": "Ana", "affiliation": "UV", "email": "ana@test.local"},
                {"name": "Ana Bis", "affiliation": "UN", "email": "ANA@test.local"},
            ]),
            "autor principal como coautor": self._create_payload(coauthors=[
                {"name": "Yo mismo", "affiliation": "UV", "email": self.admin.user_email},
            ]),
        }
        for case, payload in invalid_cases.items():
            with self.subTest(case=case):
                self.assertEqual(self._post_create(payload).status_code, 400)
        self.assertFalse(Article.objects.filter(article_subject="Artículo con autores").exists())

    def test_update_article_replaces_coauthors_and_keeps_main_author(self):
        created = self._post_create(self._create_payload(
            coauthors=[{"name": "Ana", "affiliation": "UV", "email": "ana@test.local"}]
        )).json()["data"]
        response = self.client.put(
            f"/api/v1/article/{created['article_id']}/update/",
            data=json.dumps({"coauthors": [{"name": "Luis", "affiliation": "UN", "email": "luis@test.local"}]}),
            content_type="application/json",
            **self.auth_headers,
        )
        self.assertEqual(response.status_code, 200)
        authors = response.json()["data"]["authors"]
        self.assertEqual([a["email"] for a in authors], [self.admin.user_email, "luis@test.local"])
        self.assertEqual(authors[0]["affiliation"], "Universidad del Valle")

    def test_update_article_via_method_url(self):
        payload = {
            "article_subject": "IA en Medicina Actualizada",
        }
        response = self.client.post(
            f"/api/v1/article/{self.article.article_id}/update/",
            data=json.dumps(payload),
            content_type="application/json",
            **self.auth_headers,
        )
        self.assertEqual(response.status_code, 200)
        self.article.refresh_from_db()
        self.assertEqual(self.article.article_subject, "IA en Medicina Actualizada")

    def test_delete_article_via_method_url(self):
        response = self.client.post(
            f"/api/v1/article/{self.article.article_id}/delete/",
            **self.auth_headers,
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Article.objects.filter(pk=self.article.article_id).exists())


class EventReadTests(APITestCase):
    def setUp(self):
        self.user = User(
            user_name="Usuario",
            user_lastname="Eventos",
            user_email="event-reader@test.local",
        )
        self.user.set_password("Clave.Segura1")
        self.user.save()
        self.client.force_authenticate(user=self.user)

        self.topic = Topic.objects.create(
            topic_subject="Inteligencia Artificial",
            topic_description="Modelos y aplicaciones de IA.",
        )
        self.event = Event.objects.create(
            event_name="Congreso SIGECI",
            event_description="Conferencia académica.",
            event_address="Universidad del Valle",
            event_date="2026-12-10T09:00:00Z",
        )
        Schedule.objects.create(
            event=self.event,
            topic_id=self.topic,
            schedule_hour=time(9, 30),
        )

    def test_list_events(self):
        response = self.client.get("/api/v1/event/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"][0]["event_id"], self.event.event_id)
        self.assertEqual(response.data["data"][0]["event_name"], "Congreso SIGECI")

    def test_plural_event_routes(self):
        list_response = self.client.get("/api/v1/events/")
        detail_response = self.client.get(f"/api/v1/events/{self.event.event_id}/")

        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(detail_response.data["data"]["event_id"], self.event.event_id)

    def test_event_detail_includes_schedule_and_topics(self):
        response = self.client.get(f"/api/v1/event/{self.event.event_id}/")

        self.assertEqual(response.status_code, 200)
        data = response.data["data"]
        self.assertEqual(data["schedule"][0]["schedule_hour"], "09:30:00")
        self.assertEqual(data["schedule"][0]["topic"]["topic_id"], self.topic.topic_id)
        self.assertEqual(data["topics"][0]["topic_subject"], "Inteligencia Artificial")

    def test_event_detail_returns_not_found(self):
        response = self.client.get("/api/v1/event/999999/")

        self.assertEqual(response.status_code, 404)

    def test_event_list_requires_authentication(self):
        self.client.force_authenticate(user=None)

        response = self.client.get("/api/v1/event/")

        self.assertEqual(response.status_code, 401)


class EventWriteTests(APITestCase):
    def setUp(self):
        call_command("seed_accounts")
        self.member = self.make_user("committee-events@test.local", "MEMBER")
        self.author = self.make_user("author-events@test.local", "AUTHOR")
        self.topic = Topic.objects.create(topic_subject="Inteligencia Artificial")
        self.other_topic = Topic.objects.create(topic_subject="Ciberseguridad")
        self.event = Event.objects.create(
            event_name="Evento original",
            event_date="2026-12-10T09:00:00Z",
        )
        Schedule.objects.create(
            event=self.event,
            topic_id=self.topic,
            schedule_hour=time(9, 0),
            application_id=55,
        )

    def make_user(self, email, profile_name):
        user = User(
            user_name="Usuario",
            user_lastname="Eventos",
            user_email=email,
        )
        user.set_password("Clave.Segura1")
        user.save()
        user.profiles.add(Profile.objects.get(profile_name=profile_name))
        return user

    def test_committee_can_create_event_with_schedule(self):
        self.client.force_authenticate(user=self.member)
        response = self.client.post(
            "/api/v1/events/",
            {
                "event_name": "Nuevo congreso",
                "event_description": "Descripción",
                "event_address": "Cali",
                "event_date": "2026-12-12T10:00:00Z",
                "schedule": [{
                    "topic_id": self.topic.topic_id,
                    "schedule_hour": "10:30:00",
                }],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["data"]["schedule"][0]["topic_id"], self.topic.topic_id)
        self.assertEqual(Event.objects.get(event_name="Nuevo congreso").schedule_items.count(), 1)

    def test_committee_can_update_event_and_replace_schedule(self):
        self.client.force_authenticate(user=self.member)
        response = self.client.patch(
            f"/api/v1/events/{self.event.event_id}/",
            {
                "event_name": "Evento actualizado",
                "schedule": [{
                    "schedule_id": self.event.schedule_items.get().schedule_id,
                    "topic_id": self.other_topic.topic_id,
                    "schedule_hour": "11:00:00",
                }],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.event.refresh_from_db()
        self.assertEqual(self.event.event_name, "Evento actualizado")
        self.assertEqual(self.event.schedule_items.count(), 1)
        self.assertEqual(self.event.schedule_items.get().topic_id_id, self.other_topic.topic_id)
        self.assertEqual(self.event.schedule_items.get().application_id, 55)

    def test_author_cannot_create_or_update_events(self):
        self.client.force_authenticate(user=self.author)
        payload = {
            "event_name": "No autorizado",
            "event_date": "2026-12-12T10:00:00Z",
        }

        create_response = self.client.post("/api/v1/events/", payload, format="json")
        update_response = self.client.patch(
            f"/api/v1/events/{self.event.event_id}/",
            {"event_name": "No autorizado"},
            format="json",
        )

        self.assertEqual(create_response.status_code, 403)
        self.assertEqual(update_response.status_code, 403)
        self.assertFalse(Event.objects.filter(event_name="No autorizado").exists())

    def test_invalid_schedule_does_not_create_event(self):
        self.client.force_authenticate(user=self.member)

        response = self.client.post(
            "/api/v1/events/",
            {
                "event_name": "Evento inválido",
                "event_date": "2026-12-12T10:00:00Z",
                "schedule": [{"topic_id": 999999, "schedule_hour": "10:30:00"}],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(Event.objects.filter(event_name="Evento inválido").exists())

    def test_member_has_event_write_permissions(self):
        self.assertTrue(self.member.has_perm_on("event", "create"))
        self.assertTrue(self.member.has_perm_on("event", "update"))


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
        )
        user.set_password("Clave.Segura1")
        user.save()
        user.profiles.add(Profile.objects.get(profile_name=profile_name))
        return user

    def authenticate(self, user):
        cache.clear()  # el login tiene límite de 10/min (throttle 'auth'); se reinicia por test
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

    def test_author_cannot_view_or_verdict(self):
        author = self.make_user("autor@sigeci.test", "AUTHOR")
        self.authenticate(author)

        list_response = self.client.get("/api/evaluations/assigned/")
        self.assertEqual(list_response.status_code, 403)

        verdict_response = self.client.post(
            f"/api/evaluations/assigned/{self.review.article_reviewer_id}/verdict/",
            {"verdict": "APROBADO", "comments": "Comentario válido."},
            format="json",
        )
        self.assertEqual(verdict_response.status_code, 403)

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