# SCRUM-31: código de verificación único por artículo.
# Cada artículo EXISTENTE recibe su propio UUID (un AddField con default=uuid4 daría el mismo a todos).
import uuid

from django.db import migrations, models


def fill_unique_codes(apps, schema_editor):
    Article = apps.get_model("article", "Article")
    for article in Article.objects.filter(verification_code__isnull=True).iterator():
        article.verification_code = uuid.uuid4()
        article.save(update_fields=["verification_code"])


class Migration(migrations.Migration):

    dependencies = [
        ("article", "0008_event_schedule"),
    ]

    operations = [
        migrations.AddField(
            model_name="article",
            name="verification_code",
            field=models.UUIDField(blank=True, editable=False, null=True),
        ),
        migrations.RunPython(fill_unique_codes, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="article",
            name="verification_code",
            field=models.UUIDField(blank=True, default=uuid.uuid4, editable=False, null=True, unique=True),
        ),
    ]
