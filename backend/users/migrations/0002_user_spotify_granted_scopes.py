from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('users', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='spotify_granted_scopes',
            field=models.JSONField(blank=True, default=list),
        ),
    ]
