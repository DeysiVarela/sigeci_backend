from django.core.management.base import BaseCommand
from django.db import IntegrityError, transaction

from accounts.models import User


class Command(BaseCommand):
    help = (
        "Elimina de la base de datos los usuarios que quedaron marcados como borrados "
        "(user_delete=True) cuando la eliminación era lógica. Sin --yes solo los lista."
    )

    def add_arguments(self, parser):
        parser.add_argument("--yes", action="store_true", help="Ejecuta el borrado")

    def handle(self, *args, **options):
        users = list(User.objects.filter(user_delete=True).order_by("user_id"))
        if not users:
            self.stdout.write("No hay usuarios marcados como borrados.")
            return

        for u in users:
            self.stdout.write(f"  #{u.pk}  {u.user_email}")

        if not options["yes"]:
            self.stdout.write(self.style.WARNING(
                f"{len(users)} usuario(s) marcados. Para borrarlos de la base de datos: "
                "python manage.py purge_deleted_users --yes"
            ))
            return

        deleted, kept = 0, []
        for u in users:
            try:
                with transaction.atomic():
                    u.delete()
                deleted += 1
            except IntegrityError:
                kept.append(u.user_email)

        self.stdout.write(self.style.SUCCESS(f"Eliminados: {deleted}"))
        if kept:
            self.stdout.write(self.style.WARNING(
                "No se pudieron eliminar por tener registros asociados (siguen marcados como borrados): "
                + ", ".join(kept)
            ))
