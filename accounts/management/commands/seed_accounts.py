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
        "me": ["view", "delete"],  # "me": mi propia cuenta (view = /auth/me, delete = SCRUM-129)
    },
    # MEMBER = miembro del comité científico: gestiona usuarios, salvo cuentas y rol de
    # administrador (regla en users/views.py y users/serializers.py).
    "MEMBER": {
        "user": ["view", "create", "update", "delete", "active", "inactive"],
        "user_role": ["update"],
        "article": ["view", "download"],
        "event": ["view", "create", "update"],
        "application": ["view"],
        "evaluation": ["view", "update"],
        "me": ["view", "delete"],
    },
    "AUTHOR": {
        "article": ["view", "create", "update", "download"],
        "event": ["view"],
        "application": ["view", "create", "update"],
        "me": ["view", "delete"],
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
                # Convención del equipo: una fila por (perfil, recurso) con "|".
                joined = "|".join(perms)
                existing = list(
                    ProfileAction.objects.filter(
                        profile=profile, profile_action_action=resource
                    ).order_by("profile_action_id")
                )
                if existing:
                    main_row, extra_rows = existing[0], existing[1:]
                    for row in extra_rows:
                        row.delete()
                    main_row.profile_action_permissions = joined
                    main_row.profile_action_active = True
                    main_row.profile_action_delete = False
                    main_row.save()
                else:
                    ProfileAction.objects.create(
                        profile=profile,
                        profile_action_action=resource,
                        profile_action_permissions=joined,
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
                user_email=email.lower()
            )
            admin.set_password(password)
            admin.save()
            admin.profiles.add(Profile.objects.get(profile_name="ADMIN"))
            self.stdout.write(self.style.SUCCESS(f"Administrador {email} creado."))