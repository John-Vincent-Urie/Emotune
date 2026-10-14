"""Store Spotify matches for songs the first seed could not match.

On 2026-10-10 each of the 27 unmatched songs was searched once on Spotify
(exact title + artist, no retries). 17 came back as matches; one of those --
"Merry-Go-Round - Piano Solo Ver." -- is a different version of the song, not
the approved recording, so it was left out. The 16 below are stored; the other
11 songs stay listed without a play button (and with a Spotify search link).

Only songs that still have no Spotify id are touched. title/artist are the
approved docs/music.md spellings, which is how the seed stored them.
"""
from django.db import migrations

MATCHES = [{'title': 'Salamin-Salamin',
  'artist': 'BINI',
  'spotify_track_id': '1iIJtD9hkzw4ZHfR7ND9yb',
  'spotify_url': 'https://open.spotify.com/track/1iIJtD9hkzw4ZHfR7ND9yb',
  'album': 'Talaarawan',
  'image': 'https://i.scdn.co/image/ab67616d0000b27369c364be39f1f1f81a8faa03',
  'duration_ms': 230218},
 {'title': '1-800-273-8255',
  'artist': 'Logic ft. Alessia Cara & Khalid',
  'spotify_track_id': '5tz69p7tJuGPeMGwNTxYuV',
  'spotify_url': 'https://open.spotify.com/track/5tz69p7tJuGPeMGwNTxYuV',
  'album': 'Everybody',
  'image': 'https://i.scdn.co/image/ab67616d0000b273cfdf40cf325b609a52457805',
  'duration_ms': 250173},
 {'title': 'Lonely',
  'artist': 'Justin Bieber & benny blanco',
  'spotify_track_id': '3S8jK1mGzQi24ilFb45DAZ',
  'spotify_url': 'https://open.spotify.com/track/3S8jK1mGzQi24ilFb45DAZ',
  'album': 'Justice',
  'image': 'https://i.scdn.co/image/ab67616d0000b273e6f407c7f3a0ec98845e4431',
  'duration_ms': 149189},
 {'title': 'Under Pressure',
  'artist': 'Queen & David Bowie',
  'spotify_track_id': '2nrG5UtAcqXbYttu7MXP1p',
  'spotify_url': 'https://open.spotify.com/track/2nrG5UtAcqXbYttu7MXP1p',
  'album': 'Hot Space',
  'image': 'https://i.scdn.co/image/ab67616d0000b27344c0a9843fac69db4d56d14e',
  'duration_ms': 248440},
 {'title': 'No One Noticed',
  'artist': 'The Marías',
  'spotify_track_id': '3siwsiaEoU4Kuuc9WKMUy5',
  'spotify_url': 'https://open.spotify.com/track/3siwsiaEoU4Kuuc9WKMUy5',
  'album': 'Submarine',
  'image': 'https://i.scdn.co/image/ab67616d0000b2738aa339341a0b0c813909c831',
  'duration_ms': 236906},
 {'title': 'This Side of Paradise',
  'artist': 'Coyote Theory',
  'spotify_track_id': '79EkGysjP2dL5GdpeQjRxT',
  'spotify_url': 'https://open.spotify.com/track/79EkGysjP2dL5GdpeQjRxT',
  'album': 'Color',
  'image': 'https://i.scdn.co/image/ab67616d0000b273d45404b4c5a5444cb06c9f7b',
  'duration_ms': 242010},
 {'title': 'Wake Me Up',
  'artist': 'Avicii',
  'spotify_track_id': '0nrRP2bk19rLc0orkWPQk2',
  'spotify_url': 'https://open.spotify.com/track/0nrRP2bk19rLc0orkWPQk2',
  'album': 'True',
  'image': 'https://i.scdn.co/image/ab67616d0000b273e14f11f796cef9f9a82691a7',
  'duration_ms': 247426},
 {'title': 'Versace on the Floor',
  'artist': 'Bruno Mars',
  'spotify_track_id': '0kN8xEmgMW9mh7UmDYHlJP',
  'spotify_url': 'https://open.spotify.com/track/0kN8xEmgMW9mh7UmDYHlJP',
  'album': '24K Magic',
  'image': 'https://i.scdn.co/image/ab67616d0000b273232711f7d66a1e19e89e28c5',
  'duration_ms': 261240},
 {'title': 'All I Do Is Win',
  'artist': 'DJ Khaled',
  'spotify_track_id': '5NEKjqTQPKiqOiOG8YxLdS',
  'spotify_url': 'https://open.spotify.com/track/5NEKjqTQPKiqOiOG8YxLdS',
  'album': 'Victory',
  'image': 'https://i.scdn.co/image/ab67616d0000b273fb87b874d265126523504ecd',
  'duration_ms': 232506},
 {'title': 'Surprise Yourself',
  'artist': 'Jack Garratt',
  'spotify_track_id': '6YaC65M3ujeROidG3b09J0',
  'spotify_url': 'https://open.spotify.com/track/6YaC65M3ujeROidG3b09J0',
  'album': 'Phase (Deluxe)',
  'image': 'https://i.scdn.co/image/ab67616d0000b273ee053a3589ea64a4a4d00dc8',
  'duration_ms': 260866},
 {'title': 'Dynamite',
  'artist': 'BTS',
  'spotify_track_id': '5QDLhrAOJJdNAmCTJ8xMyW',
  'spotify_url': 'https://open.spotify.com/track/5QDLhrAOJJdNAmCTJ8xMyW',
  'album': 'BE',
  'image': 'https://i.scdn.co/image/ab67616d0000b273c07d5d2fdc02ae252fcd07e5',
  'duration_ms': 199053},
 {'title': 'Ilaw sa Daan',
  'artist': 'IV of Spades',
  'spotify_track_id': '652CegYwXhnFnVz3SgGzTO',
  'spotify_url': 'https://open.spotify.com/track/652CegYwXhnFnVz3SgGzTO',
  'album': 'Ilaw Sa Daan',
  'image': 'https://i.scdn.co/image/ab67616d0000b273b13006f2f66d1cb3583c2de1',
  'duration_ms': 242790},
 {'title': 'Happier',
  'artist': 'Marshmello & Bastill',
  'spotify_track_id': '7BqHUALzNBTanL6OvsqmC1',
  'spotify_url': 'https://open.spotify.com/track/7BqHUALzNBTanL6OvsqmC1',
  'album': 'Happier',
  'image': 'https://i.scdn.co/image/ab67616d0000b273dd0a40eecd4b13e4c59988da',
  'duration_ms': 214289},
 {'title': 'The Day You Said Goodnight',
  'artist': 'Hale',
  'spotify_track_id': '2cjp6qXf56En6dSHKfF8NE',
  'spotify_url': 'https://open.spotify.com/track/2cjp6qXf56En6dSHKfF8NE',
  'album': 'Hale',
  'image': 'https://i.scdn.co/image/ab67616d0000b273a19b960b94edfffba8705234',
  'duration_ms': 291320},
 {'title': 'Kahit Ayaw Mo Na',
  'artist': 'This Band',
  'spotify_track_id': '3QPsTiJBaPHx607Dcl0CX1',
  'spotify_url': 'https://open.spotify.com/track/3QPsTiJBaPHx607Dcl0CX1',
  'album': 'Kahit Ayaw Mo Na',
  'image': 'https://i.scdn.co/image/ab67616d0000b273f4f5bfd50eb853fff40c34fb',
  'duration_ms': 243015},
 {'title': 'Whatever It Takes',
  'artist': 'Imagine Dragons',
  'spotify_track_id': '6Qn5zhYkTa37e91HC1D7lb',
  'spotify_url': 'https://open.spotify.com/track/6Qn5zhYkTa37e91HC1D7lb',
  'album': 'Evolve',
  'image': 'https://i.scdn.co/image/ab67616d0000b2735675e83f707f1d7271e5cf8a',
  'duration_ms': 201240}]


def store(apps, schema_editor):
    Song = apps.get_model('api', 'Song')
    for row in MATCHES:
        Song.objects.filter(
            title=row['title'], artist=row['artist'], spotify_track_id__isnull=True,
        ).update(**{key: value for key, value in row.items() if key not in ('title', 'artist')})


def unstore(apps, schema_editor):
    Song = apps.get_model('api', 'Song')
    for row in MATCHES:
        Song.objects.filter(
            title=row['title'], artist=row['artist'], spotify_track_id=row['spotify_track_id'],
        ).update(spotify_track_id=None, spotify_url=None, album='', image='', duration_ms=0)


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0008_seed_therapist_songs'),
    ]

    operations = [
        migrations.RunPython(store, unstore),
    ]
