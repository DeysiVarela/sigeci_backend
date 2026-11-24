from django.db import migrations


def grant_member_event_write_permissions(apps, schema_editor):
    database = schema_editor.connection.alias
    Profile = apps.get_model("accounts", "Profile")
    ProfileAction = apps.get_model("accounts", "ProfileAction")

    member = Profile.objects.using(database).filter(profile_name="MEMBER").first()
    if member is None:
        return

    actions = list(
        ProfileAction.objects.using(database)
        .filter(profile_id=member.pk, profile_action_action="event")
        .order_by("profile_action_id")
    )
    if not actions:
        ProfileAction.objects.using(database).create(
            profile_id=member.pk,
            profile_action_action="event",
            profile_action_permissions="view|create|update",
        )
        return

    permissions = []
    for action in actions:
        for permission in action.profile_action_permissions.split("|"):
            if permission and permission not in permissions:
                permissions.append(permission)
    for permission in ("view", "create", "update"):
        if permission not in permissions:
            permissions.append(permission)

    primary_action, *extra_actions = actions
    for action in extra_actions:
        action.delete()
    primary_action.profile_action_permissions = "|".join(permissions)
    primary_action.save(update_fields=["profile_action_permissions"])


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0004_merge_20261122_2228"),
    ]

    operations = [
        migrations.RunPython(
            grant_member_event_write_permissions,
            migrations.RunPython.noop,
        ),
    ]
