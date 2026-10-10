"""
Spotify endpoint constants.

The curated seed tracks, per-emotion search queries and the docs/music.md
parser that used to live here went with the Spotify search pipeline: the songs
for an emotion now come from the therapist-approved collection in the database
(api/models.py), seeded from docs/music.md by migration.
"""

SUPPORTED_SPOTIFY_ITEM_TYPES = {
    'track',
    'playlist',
    'album',
    'artist',
    'episode',
    'show',
}

SPOTIFY_AUTH_URL = 'https://accounts.spotify.com/authorize'
SPOTIFY_TOKEN_URL = 'https://accounts.spotify.com/api/token'
SPOTIFY_API_BASE = 'https://api.spotify.com/v1'
