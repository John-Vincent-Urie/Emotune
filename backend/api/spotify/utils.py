"""
Small, stateless helper functions shared across the Spotify collaborator
classes (auth, search, recommendations, personalization, playback).

Every function here is a pure function of its arguments -- none of them
depend on Spotify credentials, HTTP clients, or other instance state, which
is exactly why they were pulled out of SpotifyService instead of staying as
methods on one of the collaborator classes.
"""
import re
from urllib.parse import urlparse
import logging

from django.conf import settings

from .constants import SUPPORTED_SPOTIFY_ITEM_TYPES

logger = logging.getLogger('api.spotify_service')

def _normalize_scopes(scopes):
    if isinstance(scopes, str):
        values = scopes.split()
    elif isinstance(scopes, (list, tuple, set)):
        values = list(scopes)
    else:
        values = []

    ordered = []
    seen = set()
    for value in values:
        scope = str(value or '').strip()
        if not scope or scope in seen:
            continue
        seen.add(scope)
        ordered.append(scope)
    return ordered

def _required_playback_scopes():
    configured = getattr(settings, 'SPOTIFY_REQUIRED_PLAYBACK_SCOPES', '')
    normalized = _normalize_scopes(configured)
    if normalized:
        return normalized
    return [
        'streaming',
        'user-modify-playback-state',
        'user-read-playback-state',
        'user-read-currently-playing',
        'app-remote-control',
    ]

def _requested_scopes():
    return _normalize_scopes(getattr(settings, 'SPOTIFY_SCOPE', ''))

def _personalization_scope_map():
    return {
        'top_tracks': 'user-top-read',
        'saved_tracks': 'user-library-read',
        'recently_played': 'user-read-recently-played',
    }

def _token_payload_summary(payload):
    payload = payload if isinstance(payload, dict) else {}
    return {
        'scope': _normalize_scopes(payload.get('scope')),
        'expires_in': _safe_int(payload.get('expires_in'), 0),
        'has_access_token': bool(str(payload.get('access_token') or '').strip()),
        'has_refresh_token': bool(str(payload.get('refresh_token') or '').strip()),
        'token_type': str(payload.get('token_type') or '').strip() or None,
    }

def _parse_response_json(response):
    try:
        return response.json()
    except ValueError:
        return None

def _extract_error_details(payload, response_text=''):
    error_code = None
    error_message = ''

    if isinstance(payload, dict):
        error_value = payload.get('error')
        if isinstance(error_value, dict):
            error_code = error_value.get('reason') or error_value.get('status')
            error_message = str(error_value.get('message') or '').strip()
        elif error_value is not None:
            error_code = error_value
            error_message = str(error_value).strip()

        if not error_message:
            error_message = str(payload.get('error_description') or '').strip()
        if error_code is None and payload.get('error_description'):
            error_code = payload.get('error')

    if not error_message:
        error_message = str(response_text or '').strip()

    return {
        'error_code': str(error_code).strip() or None,
        'error_message': error_message[:1000] or None,
    }

def _classify_upstream_failure(
    status_code,
    error_message='',
    response_text='',
    *,
    endpoint='',
):
    combined_text = ' '.join(
        [str(error_message or '').strip(), str(response_text or '').strip()]
    ).lower()

    if status_code is None:
        return {
            'reason': 'network_error',
            'retryable': True,
            'recommended_action': (
                'Spotify could not be reached from the backend. Check internet access, '
                'firewall settings, and Spotify API availability.'
            ),
        }

    if status_code == 400 and (
        'invalid_client' in combined_text
        or 'invalid client' in combined_text
    ):
        return {
            'reason': 'client_credentials_invalid',
            'retryable': False,
            'recommended_action': (
                'SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET do not match the same '
                'Spotify app. Update the backend .env with the client secret for the '
                'current Spotify app, then restart Django.'
            ),
        }

    if status_code == 400 and (
        'invalid_grant' in combined_text
        or 'authorization code' in combined_text
        or 'redirect uri' in combined_text
        or 'redirect_uri' in combined_text
    ):
        return {
            'reason': 'invalid_grant',
            'retryable': False,
            'recommended_action': (
                'Spotify rejected the authorization code or redirect URI. Make sure '
                'the redirect URI in Spotify Dashboard exactly matches '
                'http://127.0.0.1:8000/api/spotify/callback/, then start Spotify '
                'login again.'
            ),
        }

    if status_code == 401:
        return {
            'reason': 'token_invalid',
            'retryable': False,
            'recommended_action': (
                'Reconnect Spotify in EmoTune because the Spotify access token is '
                'invalid or expired.'
            ),
        }

    if status_code == 403 and (
        'user may not be registered' in combined_text
        or 'user is not registered for this application' in combined_text
        or 'not registered for this application' in combined_text
    ):
        return {
            'reason': 'developer_allowlist_required',
            'retryable': False,
            'recommended_action': (
                'Spotify blocked this account because the app is still in Development '
                'Mode. Add the exact Spotify account to the Spotify Developer Dashboard '
                'user allowlist, then reconnect Spotify in EmoTune.'
            ),
        }

    if status_code == 403 and 'premium' in combined_text:
        return {
            'reason': 'premium_required',
            'retryable': False,
            'recommended_action': (
                'Spotify Premium is required for this playback flow. Log in with a '
                'Premium Spotify account, then reconnect EmoTune.'
            ),
        }

    if status_code == 403 and (
        'scope' in combined_text or 'insufficient client scope' in combined_text
    ):
        return {
            'reason': 'insufficient_scope',
            'retryable': False,
            'recommended_action': (
                'Reconnect Spotify in EmoTune so Spotify can grant the missing scopes.'
            ),
        }

    if status_code == 403:
        return {
            'reason': 'forbidden',
            'retryable': False,
            'recommended_action': (
                'Spotify rejected the request. Check the connected Spotify account and '
                'the Spotify Developer Dashboard configuration.'
            ),
        }

    if status_code == 429:
        return {
            'reason': 'rate_limited',
            'retryable': True,
            'recommended_action': (
                'Spotify rate-limited the request. Wait a moment and try again.'
            ),
        }

    if 500 <= status_code < 600:
        return {
            'reason': 'spotify_unavailable',
            'retryable': True,
            'recommended_action': (
                'Spotify is temporarily unavailable. Try again shortly.'
            ),
        }

    return {
        'reason': 'spotify_request_failed',
        'retryable': status_code >= 500,
        'recommended_action': (
            'Spotify rejected the request. Review the upstream status code and body for '
            'details.'
        ),
    }

def _build_failure_response(
    *,
    status_code,
    error_message,
    response_text=None,
    response_json=None,
    error_code=None,
    endpoint='',
    source='spotify',
):
    classification = _classify_upstream_failure(
        status_code,
        error_message=error_message,
        response_text=response_text,
        endpoint=endpoint,
    )
    return {
        'ok': False,
        'status_code': status_code,
        'data': None,
        'error': error_message or 'Spotify request failed.',
        'error_code': error_code,
        'reason': classification['reason'],
        'response_text': response_text,
        'response_json': response_json,
        'endpoint': endpoint,
        'source': source,
        'retryable': classification['retryable'],
        'recommended_action': classification['recommended_action'],
    }

def _build_request_exception_failure_response(
    error,
    *,
    endpoint,
    source='spotify',
    operation='Spotify request',
):
    error_message = str(error or '').strip() or f'{operation} failed.'
    logger.warning(
        "%s failed endpoint=%s source=%s reason=network_error error=%s",
        operation,
        endpoint,
        source,
        error_message[:1000],
    )
    return _build_failure_response(
        status_code=None,
        error_message=error_message[:1000],
        endpoint=endpoint,
        source=source,
    )

def _developer_allowlist_message():
    return (
        'Spotify blocked this account because the app is still in Development Mode. '
        'Add this exact Spotify account to the Spotify Developer Dashboard user '
        'allowlist, then reconnect Spotify in EmoTune.'
    )

def _has_developer_allowlist_issue(diagnostics):
    diagnostics = diagnostics if isinstance(diagnostics, dict) else {}
    for key in ('account', 'devices', 'currently_playing'):
        section = diagnostics.get(key)
        if not isinstance(section, dict):
            continue
        if (
            section.get('developer_allowlist_required')
            or section.get('error_reason') == 'developer_allowlist_required'
        ):
            return True
    return False

def _compact_failure(result, *, source=None, extra=None):
    result = result if isinstance(result, dict) else {}
    compact = {
        'source': source or result.get('source'),
        'status_code': result.get('status_code'),
        'reason': result.get('reason'),
        'error': result.get('error'),
        'error_code': result.get('error_code'),
        'recommended_action': result.get('recommended_action'),
    }
    if extra:
        compact.update(extra)
    return compact

def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default

def _clamp_spotify_limit(value, *, default=10, minimum=1, maximum=50):
    normalized = _safe_int(value, default)
    return max(min(normalized, maximum), minimum)

def _clamp_spotify_search_limit(value, *, default=5):
    return _clamp_spotify_limit(
        value,
        default=default,
        minimum=1,
        maximum=10,
    )

def _track_match_key(track):
    if not isinstance(track, dict):
        return None

    title = _canonical_track_title(track.get('name'))
    artist = str(track.get('artist') or '').split(',', 1)[0].strip().lower()
    if not title or not artist:
        return None

    artist = re.sub(r'\s+', ' ', artist).strip()

    if not title or not artist:
        return None
    return f'{artist}|{title}'

def _canonical_track_title(value):
    title = str(value or '').strip().lower()
    if not title:
        return ''
    title = re.sub(r'\s*\([^)]*\)', '', title)
    title = re.sub(
        r'\s*-\s*.*(?:live|acoustic|remix|edit|version|remaster(?:ed)?|anniversary|sped up|slowed(?: down)?|instrumental|karaoke|from ).*',
        '',
        title,
    )
    title = re.sub(r'\s+part\s+\d+\b', '', title)
    title = re.sub(r'\s+', ' ', title).strip()
    return title

def _unique_text_values(values):
    unique_values = []
    seen_values = set()
    for value in values or []:
        normalized = str(value or '').strip()
        if not normalized or normalized in seen_values:
            continue
        seen_values.add(normalized)
        unique_values.append(normalized)
    return unique_values

def _normalize_playable_item(item, default_source='spotify'):
    if not isinstance(item, dict):
        return None

    normalized = dict(item)
    artist_name = str(normalized.get('artist') or '').strip()
    if artist_name.lower() == 'open in spotify':
        return None

    item_id = str(normalized.get('id') or '').strip()
    item_type = str(normalized.get('item_type') or '').strip() or 'track'
    uri = str(normalized.get('uri') or '').strip()
    spotify_url = str(normalized.get('spotify_url') or '').strip()

    if uri.startswith('spotify:'):
        uri_parts = uri.split(':', 2)
        if len(uri_parts) == 3:
            item_type = uri_parts[1] or item_type
            item_id = item_id or uri_parts[2]

    if spotify_url:
        parsed = urlparse(spotify_url)
        path_parts = [part for part in parsed.path.split('/') if part]
        if (
            'spotify.com' in (parsed.netloc or '')
            and len(path_parts) >= 2
            and path_parts[0] in SUPPORTED_SPOTIFY_ITEM_TYPES
        ):
            item_type = item_type or path_parts[0]
            item_id = item_id or path_parts[1]

    if (
        item_id
        and not uri
        and (not item_type or item_type in SUPPORTED_SPOTIFY_ITEM_TYPES)
    ):
        resolved_type = item_type or 'track'
        uri = f'spotify:{resolved_type}:{item_id}'
        item_type = resolved_type
    if (
        item_id
        and not spotify_url
        and (not item_type or item_type in SUPPORTED_SPOTIFY_ITEM_TYPES)
    ):
        resolved_type = item_type or 'track'
        spotify_url = f'https://open.spotify.com/{resolved_type}/{item_id}'
        item_type = resolved_type

    if not uri and not normalized.get('preview_url'):
        return None

    normalized['id'] = item_id or uri or spotify_url or normalized.get('name') or 'spotify-item'
    normalized['item_type'] = item_type
    normalized['name'] = str(normalized.get('name') or 'Spotify recommendation')
    normalized['artist'] = artist_name or 'Spotify'
    normalized['album'] = str(normalized.get('album') or '')
    normalized['image'] = str(normalized.get('image') or '')
    normalized['preview_url'] = normalized.get('preview_url')
    normalized['duration_ms'] = _safe_int(normalized.get('duration_ms'), 0)
    normalized['uri'] = uri
    normalized['spotify_url'] = spotify_url
    normalized.setdefault('recommendation_source', default_source)
    return normalized

def _append_unique_tracks(target, seen_keys, candidates, limit):
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        item = _normalize_playable_item(
            candidate,
            default_source=candidate.get('recommendation_source', 'spotify'),
        )
        if not item:
            continue
        item_key = item.get('uri') or item.get('id')
        if not item_key or item_key in seen_keys:
            continue
        seen_keys.add(item_key)
        target.append(item)
        if len(target) >= limit:
            break

def _format_tracks(tracks):
    """Format Spotify tracks into standardized format"""
    formatted = []
    for track in tracks:
        if not track:
            continue
        album = track.get('album', {})
        artists = track.get('artists', [])
        formatted.append({
            'id': track['id'],
            'name': track['name'],
            'artist': ', '.join([a['name'] for a in artists]),
            'album': album.get('name', ''),
            'image': album.get('images', [{}])[0].get('url', '') if album.get('images') else '',
            'preview_url': track.get('preview_url'),
            'duration_ms': track.get('duration_ms', 0),
            'spotify_url': track.get('external_urls', {}).get('spotify', ''),
            'uri': track.get('uri', ''),
            'popularity': _safe_int(track.get('popularity'), 0),
        })
    return formatted

def _format_nested_track_items(
    items,
    *,
    recommendation_source,
    played_at_key=None,
    added_at_key=None,
):
    formatted = []
    for item in items or []:
        track = item.get('track') if isinstance(item, dict) else None
        if not isinstance(track, dict):
            continue
        normalized_tracks = _format_tracks([track])
        if not normalized_tracks:
            continue
        normalized = normalized_tracks[0]
        normalized['recommendation_source'] = recommendation_source
        normalized['catalog_source'] = recommendation_source
        if played_at_key and item.get(played_at_key):
            normalized['spotify_played_at'] = item.get(played_at_key)
        if added_at_key and item.get(added_at_key):
            normalized['spotify_added_at'] = item.get(added_at_key)
        formatted.append(normalized)
    return formatted

def _history_allows_learning(history):
    if history is None:
        return True
    music_picker_data = (
        history.music_picker_data
        if isinstance(history.music_picker_data, dict)
        else {}
    )
    personalization = music_picker_data.get('personalization')
    return not (
        isinstance(personalization, dict)
        and personalization.get('train_session') is False
    )

def _normalize_taste_profile(taste_profile):
    working = taste_profile if isinstance(taste_profile, dict) else {}
    familiarity = str(working.get('familiarity') or 'balanced').strip().lower()
    if familiarity not in {'balanced', 'familiar', 'discovery'}:
        familiarity = 'balanced'
    return {
        'familiarity': familiarity,
        'prefer_instrumental': bool(working.get('prefer_instrumental', False)),
    }

def _taste_discovery_bonus(track, taste_profile):
    familiarity = taste_profile.get('familiarity')
    source = str(track.get('recommendation_source') or '').strip().lower()
    if familiarity == 'discovery':
        if source in {'spotify_catalog', 'curated_fallback'}:
            return 0.14, 'taste:discovery'
        if source in {'spotify_top_tracks', 'spotify_saved_tracks', 'user_preference', 'favorite_track'}:
            return -0.08, 'taste:discovery'
    if familiarity == 'familiar':
        if source in {'spotify_top_tracks', 'spotify_saved_tracks', 'user_preference', 'favorite_track'}:
            return 0.12, 'taste:familiar'
        if source in {'spotify_catalog', 'curated_fallback'}:
            return -0.06, 'taste:familiar'
    return 0.0, None

def _taste_instrumental_bonus(text_blob, taste_profile):
    if not taste_profile.get('prefer_instrumental'):
        return 0.0, None

    normalized_blob = str(text_blob or '').strip().lower()
    instrumental_terms = (
        'instrumental',
        'ambient',
        'piano',
        'study',
        'focus',
        'meditation',
        'sleep',
        'classical',
        'soundtrack',
        'lofi',
        'lo-fi',
    )
    vocal_terms = (
        'feat.',
        'featuring',
        'karaoke',
        'live',
        'remix',
    )

    bonus = 0.0
    if any(term in normalized_blob for term in instrumental_terms):
        bonus += 0.18
    if any(term in normalized_blob for term in vocal_terms):
        bonus -= 0.07
    if bonus > 0:
        return bonus, 'taste:instrumental'
    if bonus < 0:
        return bonus, 'taste:less_instrumental_fit'
    return 0.0, None
