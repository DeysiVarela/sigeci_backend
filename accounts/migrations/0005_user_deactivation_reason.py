# SCRUM-129: motivo de baja de la cuenta. Encadenada a la 0004 (merge) de main.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0004_merge_20261122_2228'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='deactivation_reason',
            field=models.CharField(blank=True, choices=[('AUTO_ELIMINADO', 'Auto-eliminado'), ('SUSPENDIDO_POR_ADMIN', 'Suspendido por administrador')], max_length=60, null=True),
        ),
    ]
