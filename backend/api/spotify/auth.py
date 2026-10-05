"""
Spotify OAuth / token handling: authorization URL construction, code
exchange, token refresh, client-credentials tokens, and the low-level
authenticated request helpers every other Spotify collaborator relies on.
"""
import base64
import logging
from datetime import timedelta
from urllib.parse import urlencode

import requests
from django.conf import settings
from django.utils import timezone

from .. import http_client
from .utils import (
    _build_failure_response,
    _build_request_exception_failure_response,
    _classify_upstream_failure,
    _compact_failure,
    _extract_error_details,
    _normalize_scopes,
    _parse_response_json,
    _parse_retry_after,
    _token_payload_summary,
)
from .constants import SPOTIFY_AUTH_URL, SPOTIFY_TOKEN_URL, SPOTIFY_API_BASE

logger = logging.getLogger('api.spotify_service')


class SpotifyAuthError(Exception):
    def __init__(self, status_code, query, response_text=''):
        self.status_code = status_code
        self.query = query
        self.response_text = response_text
        super().__init__(f"Spotify auth failed with status {status_code} for query {query!r}")




class SpotifyAuthClient:
    def __init__(self, service, client_id, client_secret, redirect_uri, request_timeout_seconds):
        self.service = service
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.request_timeout_seconds = request_timeout_seconds
        self._client_token = None
        self._client_token_expires_at = None

    def get_auth_url(self, state=None, redirect_uri=None):
        """Generate Spotify OAuth URL"""
        resolved_redirect_uri = redirect_uri or self.redirect_uri
        params = {
            'client_id': self.client_id,
            'response_type': 'code',
            'redirect_uri': resolved_redirect_uri,
            'scope': settings.SPOTIFY_SCOPE,
        }
        if state:
            params['state'] = state
        return f"{SPOTIFY_AUTH_URL}?{urlencode(params)}"

    def exchange_code(self, code, redirect_uri=None):
        """Exchange auth code for tokens"""
        resolved_redirect_uri = redirect_uri or self.redirect_uri
        auth = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode()
        try:
            response = http_client.post(
                SPOTIFY_TOKEN_URL,
                headers={
                    'Authorization': f'Basic {auth}',
                    'Content-Type': 'application/x-www-form-urlencoded',
                },
                data={
                    'grant_type': 'authorization_code',
                    'code': code,
                    'redirect_uri': resolved_redirect_uri,
                },
                timeout=self.request_timeout_seconds,
            )
        except requests.RequestException as error:
            return _build_request_exception_failure_response(
                error,
                endpoint='/api/token',
                source='authorization_code',
                operation='Spotify token exchange',
            )

        payload = _parse_response_json(response)
        if response.ok and isinstance(payload, dict):
            logger.info(
                "Spotify token exchange status=%s redirect_uri=%s payload=%s",
                response.status_code,
                resolved_redirect_uri,
                _token_payload_summary(payload),
            )
            return payload

        details = _extract_error_details(payload, response.text)
        classification = _classify_upstream_failure(
            response.status_code,
            error_message=details.get('error_message') or '',
            response_text=response.text,
            endpoint='/api/token',
        )
        logger.warning(
            "Spotify token exchange failed status=%s redirect_uri=%s body=%s",
            response.status_code,
            resolved_redirect_uri,
            response.text[:1000],
        )
        return {
            'ok': False,
            'status_code': response.status_code,
            'reason': classification['reason'],
            'error': details.get('error_message') or 'Spotify token exchange failed.',
            'error_code': details.get('error_code'),
            'response_text': response.text[:1000],
            'response_json': payload,
            'recommended_action': classification['recommended_action'],
        }

    def refresh_token(self, refresh_token):
        """Refresh an access token"""
        auth = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode()
        try:
            response = http_client.post(
                SPOTIFY_TOKEN_URL,
                headers={
                    'Authorization': f'Basic {auth}',
                    'Content-Type': 'application/x-www-form-urlencoded',
                },
                data={
                    'grant_type': 'refresh_token',
                    'refresh_token': refresh_token,
                },
                timeout=self.request_timeout_seconds,
            )
        except requests.RequestException as error:
            return _build_request_exception_failure_response(
                error,
                endpoint='/api/token',
                source='refresh_token',
                operation='Spotify token refresh',
            )

        payload = _parse_response_json(response)
        if response.ok and isinstance(payload, dict):
            logger.info(
                "Spotify token refresh status=%s payload=%s",
                response.status_code,
                _token_payload_summary(payload),
            )
            return payload

        error_details = _extract_error_details(payload, response.text)
        logger.warning(
            "Spotify token refresh failed status=%s body=%s",
            response.status_code,
            response.text[:1000],
        )
        return _build_failure_response(
            status_code=response.status_code,
            error_message=(
                error_details['error_message']
                or 'Spotify token refresh failed.'
            ),
            response_text=response.text[:1000],
            response_json=payload,
            error_code=error_details['error_code'],
            endpoint='/api/token',
            source='refresh_token',
        )

    def get_client_token_details(self):
        """Get app-level token with structured error details."""
        if not self.client_id or not self.client_secret:
            logger.warning("Spotify client credentials are not configured")
            return {
                'ok': False,
                'status_code': None,
                'data': None,
                'error': 'Spotify client credentials are not configured.',
                'error_code': None,
                'reason': 'client_credentials_missing',
                'response_text': None,
                'response_json': None,
                'endpoint': '/api/token',
                'source': 'client_credentials',
                'retryable': False,
                'recommended_action': (
                    'Configure SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET on the backend.'
                ),
            }

        if (
            self._client_token
            and self._client_token_expires_at
            and self._client_token_expires_at > timezone.now()
        ):
            return {
                'ok': True,
                'status_code': 200,
                'token': self._client_token,
                'expires_at': self._client_token_expires_at.isoformat(),
                'source': 'client_credentials_cache',
                'cached': True,
            }

        auth = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode()
        try:
            response = http_client.post(
                SPOTIFY_TOKEN_URL,
                headers={
                    'Authorization': f'Basic {auth}',
                    'Content-Type': 'application/x-www-form-urlencoded',
                },
                data={'grant_type': 'client_credentials'},
                timeout=self.request_timeout_seconds,
            )
        except requests.RequestException as error:
            return _build_request_exception_failure_response(
                error,
                endpoint='/api/token',
                source='client_credentials',
                operation='Spotify client token request',
            )

        payload = _parse_response_json(response)
        if response.ok and isinstance(payload, dict):
            access_token = payload.get('access_token')
            expires_in = int(payload.get('expires_in', 3600))
            if access_token:
                self._client_token = access_token
                self._client_token_expires_at = timezone.now() + timedelta(
                    seconds=max(expires_in - 60, 60)
                )
                logger.info(
                    "Spotify client credentials token acquired expires_in=%s",
                    expires_in,
                )
                return {
                    'ok': True,
                    'status_code': response.status_code,
                    'token': access_token,
                    'expires_at': self._client_token_expires_at.isoformat(),
                    'source': 'client_credentials',
                    'cached': False,
                }

        error_details = _extract_error_details(payload, response.text)
        logger.warning(
            "Spotify client token request failed status=%s error=%s body=%s",
            response.status_code,
            error_details['error_message'],
            response.text[:1000],
        )
        return _build_failure_response(
            status_code=response.status_code,
            error_message=(
                error_details['error_message']
                or 'Spotify client token request failed.'
            ),
            response_text=response.text[:1000],
            response_json=payload,
            error_code=error_details['error_code'],
            endpoint='/api/token',
            source='client_credentials',
        )

    def get_client_token(self):
        """Get app-level token (no user auth required)."""
        token_details = self.service.get_client_token_details()
        if token_details.get('ok'):
            return token_details.get('token')
        return None

    def ensure_valid_token_with_details(self, user):
        """Ensure the user's Spotify token is valid and return debug metadata."""
        details = {
            'access_token': None,
            'refresh_attempted': False,
            'refresh_succeeded': False,
            'refresh_error': None,
            'refresh_failure': None,
            'granted_scopes': _normalize_scopes(user.spotify_granted_scopes),
        }

        if not user.is_spotify_connected:
            details['refresh_error'] = 'spotify_not_connected'
            return details

        access_token = str(user.spotify_access_token or '').strip()
        refresh_token = str(user.spotify_refresh_token or '').strip()
        now = timezone.now()
        token_expired = (
            not access_token
            or (user.spotify_token_expires and user.spotify_token_expires <= now)
        )

        if not token_expired:
            details['access_token'] = access_token
            return details

        if not refresh_token:
            logger.warning(
                "Spotify token refresh skipped for user %s because no refresh token is stored",
                user.id,
            )
            details['refresh_error'] = 'missing_refresh_token'
            return details

        details['refresh_attempted'] = True
        token_data = self.service.refresh_token(refresh_token)
        if not isinstance(token_data, dict):
            token_data = {}
        if token_data.get('ok') is False:
            refresh_failure = _compact_failure(token_data, source='refresh_token')
            logger.warning(
                "Spotify token refresh failed for user %s reason=%s error=%s",
                user.id,
                refresh_failure.get('reason'),
                refresh_failure.get('error'),
            )
            details['refresh_error'] = (
                refresh_failure.get('reason') or 'token_refresh_failed'
            )
            details['refresh_failure'] = refresh_failure
            return details

        new_access_token = str(token_data.get('access_token') or '').strip()
        if not new_access_token:
            logger.warning(
                "Spotify token refresh failed for user %s because no access token was returned",
                user.id,
            )
            details['refresh_error'] = 'missing_access_token_in_refresh_response'
            details['refresh_failure'] = {
                'source': 'refresh_token',
                'status_code': token_data.get('status_code'),
                'reason': 'missing_access_token_in_refresh_response',
                'error': (
                    token_data.get('error')
                    or 'Spotify token refresh did not return an access token.'
                ),
                'error_code': token_data.get('error_code'),
                'recommended_action': (
                    token_data.get('recommended_action')
                    or 'Reconnect Spotify in EmoTune because the stored Spotify session '
                    'could not be refreshed.'
                ),
            }
            return details

        user.spotify_access_token = new_access_token
        new_refresh_token = str(token_data.get('refresh_token') or '').strip()
        if new_refresh_token:
            user.spotify_refresh_token = new_refresh_token
        new_scopes = _normalize_scopes(token_data.get('scope'))
        if new_scopes:
            user.spotify_granted_scopes = new_scopes
        expires_in = int(token_data.get('expires_in') or 3600)
        user.spotify_token_expires = now + timedelta(seconds=expires_in)
        update_fields = [
            'spotify_access_token',
            'spotify_refresh_token',
            'spotify_token_expires',
            'updated_at',
        ]
        if new_scopes:
            update_fields.append('spotify_granted_scopes')
        user.save(update_fields=update_fields)
        details.update({
            'access_token': new_access_token,
            'refresh_succeeded': True,
            'granted_scopes': _normalize_scopes(user.spotify_granted_scopes),
        })
        return details

    def ensure_valid_token(self, user):
        """Ensure user's Spotify token is valid, refresh if needed."""
        return self.service.ensure_valid_token_with_details(user)['access_token']

    def _spotify_request(
        self,
        method,
        token,
        path,
        params=None,
        json_body=None,
        data=None,
        timeout_seconds=None,
    ):
        """Call a Spotify Web API endpoint and return a debug-friendly payload."""
        try:
            response = http_client.request(
                method,
                f"{SPOTIFY_API_BASE}{path}",
                headers={'Authorization': f'Bearer {token}'},
                params=params,
                json=json_body,
                data=data,
                timeout=timeout_seconds or self.request_timeout_seconds,
            )
        except requests.RequestException as error:
            return _build_request_exception_failure_response(
                error,
                endpoint=path,
                operation=f'Spotify {method} {path}',
            )

        payload = _parse_response_json(response)
        response_text = response.text or ''
        # A successful search body is multiple KB of JSON, and one pool refresh
        # makes ~500 of these calls, so the body would bury every other line in
        # the log. Keep it at DEBUG for when someone is actually debugging a
        # response; the failure branch below still reports the parsed error at
        # WARNING.
        logger.info(
            "Spotify %s %s status=%s bytes=%s",
            method,
            path,
            response.status_code,
            len(response_text),
        )
        logger.debug(
            "Spotify %s %s body=%s",
            method,
            path,
            response_text[:1500],
        )

        if 200 <= response.status_code < 300:
            return {
                'ok': True,
                'status_code': response.status_code,
                'data': payload,
                'response_text': response_text,
                'response_json': payload,
                'error': None,
                'error_code': None,
                'reason': None,
                'endpoint': path,
                'source': 'spotify',
                'retryable': False,
                'recommended_action': None,
            }

        error_details = _extract_error_details(payload, response_text)
        error_message = error_details['error_message'] or response_text[:300]

        logger.warning(
            "Spotify %s %s failed with status %s: %s",
            method,
            path,
            response.status_code,
            error_message,
        )
        return _build_failure_response(
            status_code=response.status_code,
            error_message=error_message or 'Spotify request failed.',
            response_text=response_text,
            response_json=payload,
            error_code=error_details['error_code'],
            endpoint=path,
            retry_after=_parse_retry_after(response.headers.get('Retry-After')),
        )

    def _spotify_get(self, token, path, params=None, timeout_seconds=None):
        return self.service._spotify_request(
            'GET',
            token,
            path,
            params=params,
            timeout_seconds=timeout_seconds,
        )

    def _spotify_put(self, token, path, json_body=None):
        return self.service._spotify_request('PUT', token, path, json_body=json_body)

    def _spotify_post(self, token, path, params=None, json_body=None):
        return self.service._spotify_request(
            'POST',
            token,
            path,
            params=params,
            json_body=json_body,
        )
