import django.db.models.deletion
from django.db import migrations, models


def create_table_if_missing(apps, schema_editor):
    ArticleAuthor = apps.get_model("article", "ArticleAuthor")
    existing_tables = schema_editor.connection.introspection.table_names()
    if ArticleAuthor._meta.db_table not in existing_tables:
        schema_editor.create_model(ArticleAuthor)


def backfill_corresponding_authors(apps, schema_editor):
    """Crea el autor de correspondencia para los artículos sin autores (afiliación vacía)."""
    database = schema_editor.connection.alias
    Article = apps.get_model("article", "Article")
    ArticleAuthor = apps.get_model("article", "ArticleAuthor")

    with_authors = ArticleAuthor.objects.using(database).values_list("article_id", flat=True)
    articles = (
        Article.objects.using(database)
        .select_related("article_created_by")
        .exclude(article_created_by=None)
        .exclude(article_id__in=with_authors)
    )
    rows = []
    for article in articles:
        user = article.article_created_by
        rows.append(ArticleAuthor(
            article_id=article.article_id,
            user_id=user.user_id,
            author_name=(user.user_name or user.user_email)[:60],
            author_lastname=(user.user_lastname or "")[:60],
            author_email=(user.user_email or "").lower(),
            author_affiliation="",
            author_is_corresponding=True,
            author_order=0,
        ))
    ArticleAuthor.objects.using(database).bulk_create(rows)


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0007_admin_evaluation_permissions"),
        ("article", "0009_article_verification_code"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name="ArticleAuthor",
                    fields=[
                        ("article_author_id", models.AutoField(primary_key=True, serialize=False)),
                        ("author_name", models.CharField(max_length=60)),
                        ("author_lastname", models.CharField(blank=True, default="", max_length=60)),
                        ("author_email", models.CharField(max_length=120)),
                        ("author_affiliation", models.CharField(blank=True, default="", max_length=200)),
                        ("author_is_corresponding", models.BooleanField(default=False)),
                        ("author_order", models.SmallIntegerField(default=0)),
                        ("author_created_at", models.DateTimeField(auto_now_add=True)),
                        ("article", models.ForeignKey(db_column="article_id", on_delete=django.db.models.deletion.CASCADE, related_name="authors", to="article.article")),
                        ("user", models.ForeignKey(blank=True, db_column="user_id", null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to="accounts.user")),
                    ],
                    options={
                        "db_table": "article_author",
                        "ordering": ["author_order", "article_author_id"],
                    },
                ),
            ],
            database_operations=[],
        ),
        migrations.RunPython(create_table_if_missing, migrations.RunPython.noop),
        migrations.RunPython(backfill_corresponding_authors, migrations.RunPython.noop),
    ]