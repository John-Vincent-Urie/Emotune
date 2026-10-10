"""Correct the artist spelling of "Happier" to "Marshmello & Bastille".

The seed (0008) copied a typo from docs/music.md ("Bastill"). The song was
already matched to its Spotify track by 0009, so only the artist text changes.
"""
from django.db import migrations

TITLE = 'Happier'
TYPO = 'Marshmello & Bastill'
FIXED = 'Marshmello & Bastille'


def fix_artist(apps, schema_editor):
    Song = apps.get_model('api', 'Song')
    Song.objects.filter(title=TITLE, artist=TYPO).update(artist=FIXED)


def restore_typo(apps, schema_editor):
    Song = apps.get_model('api', 'Song')
    Song.objects.filter(title=TITLE, artist=FIXED).update(artist=TYPO)


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0009_store_remaining_spotify_matches'),
    ]

    operations = [
        migrations.RunPython(fix_artist, restore_typo),
    ]
