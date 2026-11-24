from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from accounts.models import Profile, User
from article.models import Article, Topic


class Command(BaseCommand):
    help = (
        "Crea un autor y dos artículos de prueba para subir versiones (SCRUM-30/31/33). "
        "SOLO DESARROLLO: se niega a correr con DEBUG apagado y nunca modifica artículos existentes."
    )

    def add_arguments(self, parser):
        parser.add_argument("--email", default="autor1@correo.com")
        parser.add_argument("--password", default="Password123!")

    def handle(self, *args, **opts):
        if not settings.DEBUG:
            raise CommandError("seed_version_tests solo se puede ejecutar en desarrollo (DJANGO_DEBUG=True).")

        author_profile = Profile.objects.filter(profile_name="AUTHOR").first()
        if author_profile is None:
            raise CommandError("No existe el perfil AUTHOR: ejecuta primero `python manage.py seed_accounts`.")

        user, created = User.objects.get_or_create(
            user_email=opts["email"].lower(),
            defaults=dict(user_name="Autor", user_lastname="Uno"),
        )
        if created:  # a un usuario que ya existía NO se le cambia la contraseña
            user.set_password(opts["password"])
            user.user_provider = User.PROVIDER_ACCOUNT
            user.save()
        user.profiles.add(author_profile)

        topic, _ = Topic.objects.get_or_create(topic_subject="Pruebas")
        ids = []
        for subject in ("Prueba versión corregida", "Prueba versión final"):
            # por título y por autor: nunca se pisa un artículo ajeno ni se fijan ids a mano
            article, _ = Article.objects.get_or_create(
                article_subject=subject,
                article_created_by=user,
                defaults=dict(topic_id=topic, article="Contenido de prueba"),
            )
            ids.append(article.article_id)
        self.stdout.write(self.style.SUCCESS(f"Listo: {user.user_email} (id {user.pk}) y artículos {ids}."))
