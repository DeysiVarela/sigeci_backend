# SCRUM-30/31: el comité (ADMIN y MEMBER) emite los avales de presentación/publicación con el permiso
# de matriz evaluation:update. MEMBER ya lo tiene; aquí se le concede a ADMIN sin tocar sus otros permisos.
from django.db import migrations


def grant_admin_evaluation(apps, schema_editor):
    database = schema_editor.connection.alias
    Profile = apps.get_model("accounts", "Profile")
    ProfileAction = apps.get_model("accounts", "ProfileAction")

    admin = Profile.objects.using(database).filter(profile_name="ADMIN").first()
    if admin is None:
        return

    actions = list(
        ProfileAction.objects.using(database)
        .filter(profile_id=admin.pk, profile_action_action="evaluation")
        .order_by("profile_action_id")
    )
    if not actions:
        ProfileAction.objects.using(database).create(
            profile_id=admin.pk,
            profile_action_action="evaluation",
            profile_action_permissions="view|update",
        )
        return

    permissions = []
    for action in actions:
        for permission in action.profile_action_permissions.split("|"):
            if permission and permission not in permissions:
                permissions.append(permission)
    for permission in ("view", "update"):
        if permission not in permissions:
            permissions.append(permission)

    primary_action, *extra_actions = actions
    for action in extra_actions:
        action.delete()
    primary_action.profile_action_permissions = "|".join(permissions)
    primary_action.save(update_fields=["profile_action_permissions"])


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0006_merge_20261124_1258"),
    ]

    operations = [
        migrations.RunPython(grant_admin_evaluation, migrations.RunPython.noop),
    ]
