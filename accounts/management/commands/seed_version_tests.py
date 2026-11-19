from django.core.management.base import BaseCommand
from accounts.models import User, Profile
from article.models import Topic, Article


class Command(BaseCommand):
    help = "Crea el autor y los artículos de prueba para subir versiones (SCRUM-30/31/33). Solo desarrollo."

    def handle(self, *args, **opts):
        autor, _ = Profile.objects.get_or_create(profile_name="AUTHOR")
        user, _ = User.objects.get_or_create(
            user_email="autor1@correo.com",
            defaults=dict(user_name="Autor", user_lastname="Uno"),
        )
        user.set_password("Password123!")
        user.user_active = True
        user.user_delete = False
        user.user_provider = User.PROVIDER_ACCOUNT
        user.save()
        user.profiles.add(autor)

        topic, _ = Topic.objects.get_or_create(topic_subject="Pruebas")
        for article_id, subject in ((3, "Prueba versión corregida"), (4, "Prueba versión final")):
            Article.objects.update_or_create(
                article_id=article_id,
                defaults=dict(article_subject=subject, topic_id=topic,
                              article="Contenido de prueba", article_created_by=user),
            )
        self.stdout.write(self.style.SUCCESS(
            f"Listo: {user.user_email} (id {user.pk}) y artículos 3 y 4."))