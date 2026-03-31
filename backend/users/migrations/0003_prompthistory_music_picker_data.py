from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('users', '0002_user_spotify_granted_scopes'),
    ]

    operations = [
        migrations.AddField(
            model_name='prompthistory',
            name='music_picker_data',
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
