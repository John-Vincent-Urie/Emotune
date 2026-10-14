"""Store the Spotify match for "Awitin Mo at Isasayaw Ko" (VST & Company).

Found by looking up the artist and searching its tracks, since the exact
title search missed: Spotify spells the title "Awitin Mo, Isasayaw ko". This is
VST & Company's own recording at the song's standard length (4:38), from a
2012 hits album; the 1978 original release is not on Spotify, and the 2008
album track is a 9-minute extended version. The Song row takes Spotify's
spelling, as docs/music.md does; its emotion link is unchanged.
"""
from django.db import migrations

OLD_TITLE = 'Awitin Mo at Isasayaw Ko'
ARTIST = 'VST & Company'
RECORDING = {'title': 'Awitin Mo, Isasayaw ko',
 'artist': 'VST & Company',
 'spotify_track_id': '5xFIkvs3t1jhuTUJ5tydte',
 'spotify_url': 'https://open.spotify.com/track/5xFIkvs3t1jhuTUJ5tydte',
 'album': 'OPM Back to Back Hits of VST & Company & Hagibis',
 'image': 'https://i.scdn.co/image/ab67616d0000b273c8a48d568fe0d0d959579c24',
 'duration_ms': 277706}


def store_recording(apps, schema_editor):
    Song = apps.get_model('api', 'Song')
    Song.objects.filter(title=OLD_TITLE, artist=ARTIST, spotify_track_id__isnull=True).update(**RECORDING)


def clear_recording(apps, schema_editor):
    Song = apps.get_model('api', 'Song')
    Song.objects.filter(
        title=RECORDING['title'], artist=ARTIST, spotify_track_id=RECORDING['spotify_track_id'],
    ).update(title=OLD_TITLE, spotify_track_id=None, spotify_url=None, album='', image='', duration_ms=0)


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0012_merry_go_round_recording'),
    ]

    operations = [
        migrations.RunPython(store_recording, clear_recording),
    ]
