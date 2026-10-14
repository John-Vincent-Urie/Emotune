"""
Spotify catalog search: track search and formatting raw Spotify API search
results into the app's track shape, plus the shared upstream-error helpers.
"""

from .auth import SpotifyAuthError
from .utils import (
    _build_failure_response,
    _clamp_spotify_search_limit,
    _format_tracks,
)


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
            'retry_after': upstream_result.get('retry_after'),
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

