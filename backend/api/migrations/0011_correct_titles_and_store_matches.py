"""Correct eight song titles/artists and store their Spotify matches.

The user corrected four titles in the therapist list (Paper Rings, I'm Nilalamig,
Swizz Beatz, Feel It) and asked that four others take Spotify's exact spelling
(Walking On Sunshine, All By Myself, Bang Bang, Merry-Go-Round of Life). Each
was searched once; only the original recording is stored. Merry-Go-Round of
Life is renamed but left unmatched: no result was the original soundtrack
recording (piano and re-recorded versions only). Emotion links and positions
are untouched -- only the Song rows change.
"""
from django.db import migrations

CHANGES = [{'old_title': 'Walking on Sunshine',
  'old_artist': 'Katrina and the Waves',
  'title': 'Walking On Sunshine',
  'artist': 'Katrina & The Waves',
  'spotify_track_id': '05wIrZSwuaVWhcv5FfqeH0',
  'spotify_url': 'https://open.spotify.com/track/05wIrZSwuaVWhcv5FfqeH0',
  'album': 'Katrina & The Waves',
  'image': 'https://i.scdn.co/image/ab67616d0000b273eafaf556eda644a745d0144d',
  'duration_ms': 238733},
 {'old_title': 'All by Myself',
  'old_artist': 'Celine Dion',
  'title': 'All By Myself',
  'artist': 'Céline Dion',
  'spotify_track_id': '0gsl92EMIScPGV1AU35nuD',
  'spotify_url': 'https://open.spotify.com/track/0gsl92EMIScPGV1AU35nuD',
  'album': 'Falling into You',
  'image': 'https://i.scdn.co/image/ab67616d0000b273c6aebd89b2dcda3348649633',
  'duration_ms': 312306},
 {'old_title': 'Bang Bang',
  'old_artist': 'Jessie J, Ariana Grande & Nicki Minaj',
  'title': 'Bang Bang',
  'artist': 'Jessie J, Ariana Grande, Nicki Minaj',
  'spotify_track_id': '2VhPOtIQw2UpQmRVevdviU',
  'spotify_url': 'https://open.spotify.com/track/2VhPOtIQw2UpQmRVevdviU',
  'album': 'Bang Bang',
  'image': 'https://i.scdn.co/image/ab67616d0000b27390ae8b740ee25465d2e46da9',
  'duration_ms': 199373},
 {'old_title': 'Merry-Go-Round',
  'old_artist': 'Joe Hisaishi',
  'title': 'Merry-Go-Round of Life',
  'artist': 'Joe Hisaishi',
  'spotify_track_id': None,
  'spotify_url': None,
  'album': '',
  'image': '',
  'duration_ms': None},
 {'old_title': 'Favorite Rings',
  'old_artist': 'Taylor Swift',
  'title': 'Paper Rings',
  'artist': 'Taylor Swift',
  'spotify_track_id': '4y5bvROuBDPr5fuwXbIBZR',
  'spotify_url': 'https://open.spotify.com/track/4y5bvROuBDPr5fuwXbIBZR',
  'album': 'Lover',
  'image': 'https://i.scdn.co/image/ab67616d0000b273e787cffec20aa2a396a61647',
  'duration_ms': 222400},
 {'old_title': "I'm Nilalangam",
  'old_artist': 'Cesca',
  'title': "I'm Nilalamig",
  'artist': 'Cesca',
  'spotify_track_id': '24p9MRxanu0RTboVEq7auk',
  'spotify_url': 'https://open.spotify.com/track/24p9MRxanu0RTboVEq7auk',
  'album': "I'm Nilalamig",
  'image': 'https://i.scdn.co/image/ab67616d0000b273ab3c0fbfd5becdc64d3a8c42',
  'duration_ms': 309126},
 {'old_title': 'Swiss Beats',
  'old_artist': 'Young Thug',
  'title': 'Swizz Beatz',
  'artist': 'Young Thug',
  'spotify_track_id': '539wfGOsGcRmT1IBVUfiJV',
  'spotify_url': 'https://open.spotify.com/track/539wfGOsGcRmT1IBVUfiJV',
  'album': 'JEFFERY',
  'image': 'https://i.scdn.co/image/ab67616d0000b273d0c72291cd96834e199e1ff8',
  'duration_ms': 196466},
 {'old_title': 'Fill It',
  'old_artist': 'Young Thug',
  'title': 'Feel It',
  'artist': 'Young Thug',
  'spotify_track_id': '2BAmF6QyK5IYEOp1TFmt0u',
  'spotify_url': 'https://open.spotify.com/track/2BAmF6QyK5IYEOp1TFmt0u',
  'album': 'Beautiful Thugger Girls',
  'image': 'https://i.scdn.co/image/ab67616d0000b273419cedff7b313b962a93932e',
  'duration_ms': 236586}]

SPOTIFY_FIELDS = ('spotify_track_id', 'spotify_url', 'album', 'image', 'duration_ms')


def apply_changes(apps, schema_editor):
    Song = apps.get_model('api', 'Song')
    for change in CHANGES:
        updates = {'title': change['title'], 'artist': change['artist']}
        if change['spotify_track_id']:
            updates.update({field: change[field] for field in SPOTIFY_FIELDS})
        Song.objects.filter(
            title=change['old_title'], artist=change['old_artist'], spotify_track_id__isnull=True,
        ).update(**updates)


def revert_changes(apps, schema_editor):
    Song = apps.get_model('api', 'Song')
    for change in CHANGES:
        updates = {'title': change['old_title'], 'artist': change['old_artist']}
        if change['spotify_track_id']:
            updates.update({'spotify_track_id': None, 'spotify_url': None, 'album': '', 'image': '', 'duration_ms': 0})
        Song.objects.filter(title=change['title'], artist=change['artist']).update(**updates)


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0010_fix_happier_artist'),
    ]

    operations = [
        migrations.RunPython(apply_changes, revert_changes),
    ]
