"""
Spotify catalog search: track/artist search, catalog search dispatch, and
formatting raw Spotify API search results into the app's track/artist shape.
"""
import logging

from .auth import SpotifyAuthError
from .utils import (
    _build_failure_response,
    _clamp_spotify_search_limit,
    _compact_failure,
    _format_tracks,
)

logger = logging.getLogger('api.spotify_service')


class SpotifyCatalogSearch:
    def __init__(self, service):
        self.service = service

    def _build_search_result(
        self,
        *,
        query,
        search_type,
        limit,
        upstream_result,
        items,
    ):
        upstream_result = upstream_result if isinstance(upstream_result, dict) else {}
        return {
            'ok': bool(upstream_result.get('ok')),
            'query': query,
            'search_type': search_type,
            'limit': limit,
            'items': items,
            'status_code': upstream_result.get('status_code'),
            'error': upstream_result.get('error'),
            'error_code': upstream_result.get('error_code'),
            'reason': upstream_result.get('reason'),
            'response_text': upstream_result.get('response_text'),
            'response_json': upstream_result.get('response_json'),
            'recommended_action': upstream_result.get('recommended_action'),
        }

    def search_tracks_detailed(
        self,
        query,
        token,
        limit=10,
        timeout_seconds=None,
    ):
        """Search for tracks and return structured upstream details."""
        limit = _clamp_spotify_search_limit(limit, default=10)
        if not token:
            return self.service._build_search_result(
                query=query,
                search_type='track',
                limit=limit,
                upstream_result=_build_failure_response(
                    status_code=None,
                    error_message='No Spotify token is available for track search.',
                    endpoint='/search',
                ),
                items=[],
            )

        upstream_result = self.service._spotify_get(
            token,
            '/search',
            params={'q': query, 'type': 'track', 'limit': limit},
            timeout_seconds=timeout_seconds,
        )
        items = []
        if upstream_result.get('ok'):
            tracks = (upstream_result.get('data') or {}).get('tracks', {}).get('items', [])
            items = _format_tracks(tracks)
        return self.service._build_search_result(
            query=query,
            search_type='track',
            limit=limit,
            upstream_result=upstream_result,
            items=items,
        )

    def search_tracks(
        self,
        query,
        token,
        limit=10,
        timeout_seconds=None,
        raise_on_auth=False,
    ):
        """Search for tracks."""
        result = self.service.search_tracks_detailed(
            query,
            token,
            limit=limit,
            timeout_seconds=timeout_seconds,
        )
        if not result['ok'] and raise_on_auth and result['status_code'] in (401, 403):
            raise SpotifyAuthError(
                result['status_code'],
                query,
                result.get('response_text') or result.get('error') or '',
            )
        return result['items']

    def _get_catalog_token_candidates(self, user=None):
        candidates = []
        failures = []

        client_token_details = self.service.get_client_token_details()
        if client_token_details.get('ok'):
            candidates.append(('client', client_token_details.get('token')))
        else:
            failures.append(_compact_failure(client_token_details, source='client'))

        if user and getattr(user, 'is_spotify_connected', False):
            try:
                user_token_details = self.service.ensure_valid_token_with_details(user)
            except Exception as error:
                logger.exception("Failed to get user Spotify token for catalog requests")
                failures.append({
                    'source': 'user',
                    'status_code': None,
                    'reason': 'token_lookup_failed',
                    'error': str(error),
                    'error_code': None,
                    'recommended_action': (
                        'Reconnect Spotify in EmoTune because the stored Spotify session '
                        'could not be validated.'
                    ),
                })
            else:
                user_token = user_token_details.get('access_token')
                if user_token and all(existing != user_token for _, existing in candidates):
                    candidates.append(('user', user_token))
                elif not user_token:
                    failures.append({
                        'source': 'user',
                        'status_code': None,
                        'reason': user_token_details.get('refresh_error') or 'token_missing',
                        'error': (
                            'No usable Spotify user token is available.'
                        ),
                        'error_code': None,
                        'recommended_action': (
                            'Reconnect Spotify in EmoTune because the Spotify session could '
                            'not be refreshed.'
                        ),
                    })

        return candidates, failures

    def _get_recommendation_tokens(self, user=None):
        """Return recommendation tokens in fallback order."""
        token_candidates, _token_failures = self.service._get_catalog_token_candidates(user=user)
        return token_candidates

    def search_artists_detailed(
        self,
        query,
        token,
        limit=5,
        timeout_seconds=None,
    ):
        """Search for artists and return structured upstream details."""
        limit = _clamp_spotify_search_limit(limit, default=5)
        if not token:
            return self.service._build_search_result(
                query=query,
                search_type='artist',
                limit=limit,
                upstream_result=_build_failure_response(
                    status_code=None,
                    error_message='No Spotify token is available for artist search.',
                    endpoint='/search',
                ),
                items=[],
            )

        upstream_result = self.service._spotify_get(
            token,
            '/search',
            params={'q': query, 'type': 'artist', 'limit': limit},
            timeout_seconds=timeout_seconds,
        )
        items = []
        if upstream_result.get('ok'):
            artists = (upstream_result.get('data') or {}).get('artists', {}).get('items', [])
            items = self.service._format_artists(artists)
        return self.service._build_search_result(
            query=query,
            search_type='artist',
            limit=limit,
            upstream_result=upstream_result,
            items=items,
        )

    def search_catalog(self, query, search_type, *, user=None, limit=20):
        """Search the Spotify catalog using client credentials and user tokens as fallback."""
        search_type = str(search_type or '').strip().lower()
        limit = _clamp_spotify_search_limit(limit, default=20)
        search_fn = (
            self.search_artists_detailed if search_type == 'artist' else self.search_tracks_detailed
        )
        token_candidates, token_failures = self.service._get_catalog_token_candidates(user=user)
        attempts = []
        query = str(query or '').strip()

        if not token_candidates:
            failure = token_failures[0] if token_failures else {
                'status_code': None,
                'reason': 'token_unavailable',
                'error': 'No Spotify token candidates are available for search.',
                'error_code': None,
                'recommended_action': (
                    'Check Spotify client credentials or reconnect Spotify in EmoTune.'
                ),
            }
            return {
                'ok': False,
                'query': query,
                'search_type': search_type,
                'limit': limit,
                'items': [],
                'status_code': failure.get('status_code'),
                'error': failure.get('error'),
                'error_code': failure.get('error_code'),
                'reason': failure.get('reason'),
                'response_text': None,
                'response_json': None,
                'recommended_action': failure.get('recommended_action'),
                'attempts': attempts,
                'token_failures': token_failures,
            }

        last_failure = None
        for token_source, token in token_candidates:
            result = search_fn(query, token, limit=limit)
            attempt = _compact_failure(
                result,
                source=token_source,
                extra={'query': query, 'item_count': len(result.get('items') or [])},
            )
            attempt['ok'] = bool(result.get('ok'))
            attempts.append(attempt)
            if result.get('ok'):
                return {
                    **result,
                    'attempts': attempts,
                    'token_failures': token_failures,
                    'token_source': token_source,
                }
            last_failure = result

        last_failure = last_failure or {}
        return {
            'ok': False,
            'query': query,
            'search_type': search_type,
            'limit': limit,
            'items': [],
            'status_code': last_failure.get('status_code'),
            'error': last_failure.get('error'),
            'error_code': last_failure.get('error_code'),
            'reason': last_failure.get('reason'),
            'response_text': last_failure.get('response_text'),
            'response_json': last_failure.get('response_json'),
            'recommended_action': last_failure.get('recommended_action'),
            'attempts': attempts,
            'token_failures': token_failures,
        }

    def upstream_http_status(self, result):
        """Map Spotify dependency failures to an API HTTP status code."""
        reason = str((result or {}).get('reason') or '').strip()
        if reason in {'network_error', 'rate_limited', 'spotify_unavailable'}:
            return 503
        if reason in {'client_credentials_missing', 'client_credentials_invalid'}:
            return 500
        return 502

    def api_error_payload(self, result, *, default_message):
        """Return a consistent API-safe Spotify error payload."""
        result = result if isinstance(result, dict) else {}
        return {
            'error': default_message,
            'spotify': {
                'status_code': result.get('status_code'),
                'reason': result.get('reason'),
                'message': result.get('error'),
                'error_code': result.get('error_code'),
                'recommended_action': result.get('recommended_action'),
                'response_body': (
                    result.get('response_json')
                    if result.get('response_json') is not None
                    else result.get('response_text')
                ),
                'attempts': result.get('attempts', []),
                'token_failures': result.get('token_failures', []),
            },
        }

    def search_artists(self, query, token, limit=5):
        """Search for artists."""
        return self.service.search_artists_detailed(query, token, limit=limit)['items']

    def _format_artists(self, artists):
        formatted = []
        for artist in artists:
            if not artist:
                continue
            formatted.append({
                'id': artist.get('id'),
                'name': artist.get('name'),
                'image': artist.get('images', [{}])[0].get('url') if artist.get('images') else None,
                'genres': artist.get('genres', []),
                'popularity': artist.get('popularity', 0),
            })
        return formatted
