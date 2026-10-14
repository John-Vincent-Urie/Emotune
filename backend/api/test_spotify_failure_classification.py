"""Spotify answers `invalid_client` for two unrelated faults; they need
different advice, because one is a .env problem and the other is a stale link.
"""

from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from api.spotify.utils import _build_failure_response
from api.spotify_service import spotify_service

User = get_user_model()


def _failure(source):
    return _build_failure_response(
        status_code=400,
        error_message='invalid_client',
        response_text='{"error":"invalid_client","error_description":"Invalid client"}',
        endpoint='https://accounts.spotify.com/api/token',
        source=source,
    )


class InvalidClientClassificationTests(TestCase):
    def test_refresh_grant_points_at_reconnecting_not_at_env(self):
        failure = _failure('refresh_token')

        self.assertEqual(failure['reason'], 'refresh_token_rejected')
        action = failure['recommended_action']
        self.assertIn('reconnect spotify', action.lower())
        # The old message sent people to edit .env first, which is the wrong
        # first move when the credentials are actually fine.
        self.assertNotIn('Update the backend .env', action)

    def test_client_credentials_grant_still_points_at_env(self):
        failure = _failure('client_credentials')

        self.assertEqual(failure['reason'], 'client_credentials_invalid')
        self.assertIn('SPOTIFY_CLIENT_SECRET', failure['recommended_action'])

    def test_neither_is_retryable(self):
        for source in ('refresh_token', 'client_credentials'):
            self.assertFalse(_failure(source)['retryable'], source)


class HealthyPlaybackActionTests(TestCase):
    """A working connection must not recommend an action.

    The advice chain used to fall through to a catch-all that told the user to
    go approve playback access, which reads as a fault on a setup that is
    already playing. Both app-side consumers treat any non-empty
    recommended_action as something to show, so healthy means empty.
    """

    def _connected_user(self):
        user = User.objects.create_user(
            username='healthy-playback-user',
            email='healthy-playback@example.com',
            password='password123',
        )
        user.is_spotify_connected = True
        user.spotify_access_token = 'spotify-token'
        user.spotify_refresh_token = 'spotify-refresh'
        user.spotify_granted_scopes = [
            'streaming',
            'user-modify-playback-state',
            'user-read-playback-state',
            'user-read-currently-playing',
            'app-remote-control',
        ]
        user.spotify_token_expires = timezone.now() + timedelta(hours=1)
        user.spotify_id = 'spotify-user-id'
        user.save()
        return user

    def _diagnostics(self, *, is_active):
        user = self._connected_user()
        token_details = {
            'access_token': 'spotify-token',
            'refresh_attempted': False,
            'refresh_succeeded': False,
            'refresh_error': None,
            'granted_scopes': user.spotify_granted_scopes,
        }
        profile = {
            'ok': True,
            'status_code': 200,
            'data': {'id': 'spotify-user-id', 'product': 'premium'},
            'response_text': '{"product":"premium"}',
        }
        playing = {
            'ok': True,
            'status_code': 200,
            'data': {
                'is_playing': True,
                'device': {'id': 'device-1', 'name': 'Redmi 14C'},
                'item': {'id': 'track-1', 'type': 'track', 'name': 'A Track'},
            },
            'response_text': '{"is_playing":true}',
        }
        devices = {
            'ok': True,
            'status_code': 200,
            'data': {'devices': [{
                'id': 'device-1',
                'name': 'Redmi 14C',
                'type': 'Smartphone',
                'is_active': is_active,
                'is_restricted': False,
            }]},
            'response_text': '{"devices":[{"id":"device-1"}]}',
        }

        with patch.object(spotify_service, 'ensure_valid_token_with_details',
                          return_value=token_details), \
             patch.object(spotify_service, 'get_user_profile_result',
                          return_value=profile), \
             patch.object(spotify_service, '_spotify_get',
                          side_effect=[playing, devices]):
            return spotify_service.get_playback_debug_status(user)

    def test_premium_account_with_active_device_recommends_nothing(self):
        diagnostics = self._diagnostics(is_active=True)

        self.assertTrue(diagnostics['spotify_connected'])
        self.assertTrue(diagnostics['devices']['has_active_device'])
        self.assertEqual(diagnostics['oauth']['missing_required_scopes'], [])
        self.assertEqual(diagnostics['recommended_action'], '')

    def test_no_active_device_still_explains_what_to_do(self):
        # The healthy branch must not swallow the genuine problem states.
        diagnostics = self._diagnostics(is_active=False)

        self.assertFalse(diagnostics['devices']['has_active_device'])
        self.assertIn('device', diagnostics['recommended_action'].lower())
