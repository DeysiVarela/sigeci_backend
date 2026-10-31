from getpass import getpass

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts.models import Profile, ProfileAction, User
from accounts.validators import validate_strong_password

# Matriz inicial (propuesta; ajustar con el equipo)
MATRIX = {
    "ADMIN": {
        "user": ["view", "create", "update", "delete", "active", "inactive"],
        "user_role": ["update"],
        "article": ["view", "create", "update", "delete", "active", "inactive", "download"],
        "event": ["view", "create", "update", "delete", "active", "inactive"],
        "application": ["view", "create", "update", "delete", "active", "inactive", "download"],
    },
    "MEMBER": {
        "article": ["view", "download"],
        "event": ["view"],
        "application": ["view"],
    },
    "AUTHOR": {
        "article": ["view", "create", "update", "download"],
        "event": ["view"],
        "application": ["view", "create", "update"],
    },
}


class Command(BaseCommand):
    help = "Crea perfiles, matriz de permisos y (opcional) el primer administrador. Es idempotente."

    def add_arguments(self, parser):
        parser.add_argument("--admin-email")
        parser.add_argument("--admin-name", default="Admin")
        parser.add_argument("--admin-lastname", default="SIGECI")

    @transaction.atomic
    def handle(self, *args, **opts):
        for profile_name, resources in MATRIX.items():
            profile, _ = Profile.objects.get_or_create(profile_name=profile_name)
            for resource, perms in resources.items():
                for perm in perms:
                    ProfileAction.objects.get_or_create(
                        profile=profile, profile_action_action=resource, profile_action_permissions=perm
                    )
        self.stdout.write(self.style.SUCCESS("Perfiles y permisos listos."))

        email = opts["admin_email"]
        if email:
            if User.objects.filter(user_email__iexact=email).exists():
                self.stdout.write("El administrador ya existe; no se modifica.")
                return
            password = getpass("Contraseña del administrador: ")
            try:
                validate_strong_password(password)
            except Exception as exc:  # noqa: BLE001
                raise CommandError(str(exc))
            admin = User(
                user_name=opts["admin_name"], user_lastname=opts["admin_lastname"],
                user_email=email.lower(), profile=Profile.objects.get(profile_name="ADMIN"),
            )
            admin.set_password(password)
            admin.save()
            self.stdout.write(self.style.SUCCESS(f"Administrador {email} creado."))
