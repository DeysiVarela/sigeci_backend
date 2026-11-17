from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("article", "0002_article_article_delete_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="articlereviewer",
            name="evaluation_deadline",
            field=models.DateField(blank=True, null=True),
        ),
    ]
