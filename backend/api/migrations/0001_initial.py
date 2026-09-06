import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name='EmotionTrackPool',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('emotion', models.CharField(max_length=50, unique=True)),
                ('tracks', models.JSONField(default=list)),
                ('queries_used', models.JSONField(blank=True, default=list)),
                ('refreshed_at', models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'db_table': 'emotion_track_pools',
                'ordering': ['emotion'],
            },
        ),
    ]
