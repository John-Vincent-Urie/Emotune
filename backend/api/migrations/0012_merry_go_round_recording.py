"""Link "Merry-Go-Round of Life" (Joe Hisaishi) to an official Spotify recording.

The original Howl's Moving Castle soundtrack recording is not on Spotify. With
the user's approval this stores Joe Hisaishi's own 2023 official re-recording
with the Royal Philharmonic Orchestra (released as a single), found by the
single search done for 0011 -- no new search. It is not a cover or a piano
version. Title and artist stay as in docs/music.md.
"""
from django.db import migrations

TITLE = 'Merry-Go-Round of Life'
ARTIST = 'Joe Hisaishi'
RECORDING = {'spotify_track_id': '1CHswVnHopmeIly3bTSnmF',
 'spotify_url': 'https://open.spotify.com/track/1CHswVnHopmeIly3bTSnmF',
 'album': "Merry-Go-Round of Life (from 'Howl’s Moving Castle')",
 'image': 'https://i.scdn.co/image/ab67616d0000b273787d1b8194bcf8709df4bb64',
 'duration_ms': 164931}


def store_recording(apps, schema_editor):
    Song = apps.get_model('api', 'Song')
    Song.objects.filter(title=TITLE, artist=ARTIST, spotify_track_id__isnull=True).update(**RECORDING)


def clear_recording(apps, schema_editor):
    Song = apps.get_model('api', 'Song')
    Song.objects.filter(
        title=TITLE, artist=ARTIST, spotify_track_id=RECORDING['spotify_track_id'],
    ).update(spotify_track_id=None, spotify_url=None, album='', image='', duration_ms=0)


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0011_correct_titles_and_store_matches'),
    ]

    operations = [
        migrations.RunPython(store_recording, clear_recording),
    ]
