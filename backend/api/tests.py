import json
from datetime import timedelta
from io import StringIO
import tempfile
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from unittest.mock import Mock, patch

import numpy as np
import requests
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from api.models import EmotionTrackPool
from api.spotify import pool
from api.llm_music_picker import LLMMusicPicker
from rest_framework_simplejwt.tokens import AccessToken

from api.recommendation_session import build_session_plan
from api.spotify_oauth_state import (
    issue_state as issue_spotify_oauth_state,
    read_state as read_spotify_oauth_state,
)
from api.spotify_service import (
    EMOTION_QUERY_PROFILES,
    MUSIC_PICKER_DOC_EMOTIONS,
    SpotifyAuthError,
    SpotifyService,
    spotify_service,
)
from ml.emotion_classifier import EmotionClassifier
from ml.plutchik_mapper import build_plutchik_profile
from users.models import FavoriteTrack, ListeningSession, PromptHistory, UserPreference


User = get_user_model()


class SpotifyOAuthTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.auth_user = User.objects.create_user(
            username='oauth-caller',
            email='oauth-caller@example.com',
            password='password123',
        )

    def authenticated_client(self, user=None):
        client = APIClient()
        client.force_authenticate(user=user or self.auth_user)
        return client

    def test_app_remote_config_exposes_public_spotify_values(self):
        response = self.client.get('/api/spotify/app-remote-config/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['client_id'], settings.SPOTIFY_CLIENT_ID)
        self.assertEqual(
            response.json()['redirect_uri'],
            'emotune://spotify-auth-callback',
        )

    def test_auth_url_uses_configured_redirect_uri_and_encodes_scope(self):
        response = self.authenticated_client().get(
            '/api/spotify/auth-url/',
            HTTP_HOST='127.0.0.1:8000',
        )

        self.assertEqual(response.status_code, 200)

        auth_url = response.json()['auth_url']
        parsed = urlparse(auth_url)
        params = parse_qs(parsed.query)

        self.assertEqual(parsed.scheme, 'https')
        self.assertEqual(parsed.netloc, 'accounts.spotify.com')
        self.assertEqual(
            params['redirect_uri'][0],
            'http://127.0.0.1:8000/api/spotify/callback/',
        )
        self.assertNotEqual(params['state'][0], str(self.auth_user.id))
        self.assertEqual(
            read_spotify_oauth_state(params['state'][0]),
            self.auth_user.id,
        )
        self.assertIn('user-read-private', params['scope'][0])
        self.assertIn('user-read-email', params['scope'][0])
        self.assertIn('streaming', params['scope'][0])
        self.assertIn('user-modify-playback-state', params['scope'][0])
        self.assertIn('user-read-playback-state', params['scope'][0])
        self.assertIn('user-read-currently-playing', params['scope'][0])
        self.assertIn('user-top-read', params['scope'][0])
        self.assertIn('user-read-recently-played', params['scope'][0])
        self.assertIn('app-remote-control', params['scope'][0])

    @override_settings(SPOTIFY_REDIRECT_URI='')
    def test_auth_url_falls_back_to_request_host_when_redirect_not_configured(self):
        response = self.authenticated_client().get(
            '/api/spotify/auth-url/',
            HTTP_HOST='127.0.0.1:8000',
        )

        self.assertEqual(response.status_code, 200)

        auth_url = response.json()['auth_url']
        parsed = urlparse(auth_url)
        params = parse_qs(parsed.query)

        self.assertEqual(
            params['redirect_uri'][0],
            'http://127.0.0.1:8000/api/spotify/callback/',
        )

    def test_auth_url_requires_authentication(self):
        response = self.client.get(
            '/api/spotify/auth-url/',
            HTTP_HOST='127.0.0.1:8000',
        )

        self.assertEqual(response.status_code, 401)

    def test_auth_url_ignores_a_caller_supplied_user_id(self):
        """The link must belong to whoever holds the token, not to a parameter."""
        victim = User.objects.create_user(
            username='victim',
            email='victim@example.com',
            password='password123',
        )

        response = self.authenticated_client().get(
            '/api/spotify/auth-url/',
            {'user_id': str(victim.id)},
            HTTP_HOST='127.0.0.1:8000',
        )

        self.assertEqual(response.status_code, 200)
        state = parse_qs(urlparse(response.json()['auth_url']).query)['state'][0]
        self.assertEqual(read_spotify_oauth_state(state), self.auth_user.id)

    @patch('api.views.spotify_service.exchange_code')
    def test_callback_refuses_a_guessed_state(self, mock_exchange_code):
        """A raw user id used to be a valid state, which let anyone link an
        account they do not own. It must now be rejected outright."""
        victim = User.objects.create_user(
            username='guessed-state-victim',
            email='guessed-state@example.com',
            password='password123',
        )

        response = self.client.get(
            '/api/spotify/callback/',
            {'code': 'attacker-code', 'state': str(victim.id)},
            HTTP_HOST='127.0.0.1:8000',
        )

        self.assertEqual(response.status_code, 400)
        victim.refresh_from_db()
        self.assertFalse(victim.is_spotify_connected)
        # Rejected before the handshake, so no Spotify code is spent on it.
        mock_exchange_code.assert_not_called()

    @patch('api.views.spotify_service.exchange_code')
    def test_callback_refuses_a_state_with_a_tampered_signature(self, mock_exchange_code):
        victim = User.objects.create_user(
            username='tampered-state-victim',
            email='tampered-state@example.com',
            password='password123',
        )
        state = issue_spotify_oauth_state(victim)

        response = self.client.get(
            '/api/spotify/callback/',
            {'code': 'attacker-code', 'state': state[:-1] + ('A' if state[-1] != 'A' else 'B')},
            HTTP_HOST='127.0.0.1:8000',
        )

        self.assertEqual(response.status_code, 400)
        victim.refresh_from_db()
        self.assertFalse(victim.is_spotify_connected)
        mock_exchange_code.assert_not_called()

    @patch('api.spotify_oauth_state.state_max_age_seconds', return_value=0)
    @patch('api.views.spotify_service.exchange_code')
    def test_callback_refuses_an_expired_state(self, mock_exchange_code, _max_age):
        user = User.objects.create_user(
            username='expired-state',
            email='expired-state@example.com',
            password='password123',
        )

        response = self.client.get(
            '/api/spotify/callback/',
            {'code': 'spotify-code', 'state': issue_spotify_oauth_state(user)},
            HTTP_HOST='127.0.0.1:8000',
        )

        self.assertEqual(response.status_code, 400)
        user.refresh_from_db()
        self.assertFalse(user.is_spotify_connected)
        mock_exchange_code.assert_not_called()

    def test_callback_refuses_a_missing_state(self):
        response = self.client.get(
            '/api/spotify/callback/',
            {'code': 'spotify-code'},
            HTTP_HOST='127.0.0.1:8000',
        )

        self.assertEqual(response.status_code, 400)

    @patch('api.views.spotify_service.get_user_profile_result')
    @patch('api.views.spotify_service.exchange_code')
    def test_callback_sends_browsers_back_to_the_app(
        self,
        mock_exchange_code,
        mock_get_user_profile_result,
    ):
        """A browser finishing OAuth gets a page that deep links into the app.

        API clients still get JSON; only the browser leg needs the return path.
        """
        user = User.objects.create_user(
            username='browser-return',
            email='browser-return@example.com',
            password='pw',
        )
        mock_exchange_code.return_value = {
            'access_token': 'spotify-access',
            'refresh_token': 'spotify-refresh',
            'expires_in': 3600,
            'scope': 'streaming',
        }
        mock_get_user_profile_result.return_value = {
            'ok': True,
            'data': {'id': 'spotify-user-id', 'email': 'spotify-user@example.com'},
        }

        response = self.client.get(
            '/api/spotify/callback/',
            {'code': 'spotify-code', 'state': issue_spotify_oauth_state(user)},
            HTTP_HOST='127.0.0.1:8000',
            HTTP_ACCEPT='text/html,application/xhtml+xml',
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn('text/html', response['Content-Type'])
        body = response.content.decode()
        self.assertIn(settings.SPOTIFY_APP_RETURN_URI, body)
        user.refresh_from_db()
        self.assertTrue(user.is_spotify_connected)

    @patch('api.views.spotify_service.get_user_profile_result')
    @patch('api.views.spotify_service.exchange_code')
    def test_callback_still_returns_json_for_api_clients(
        self,
        mock_exchange_code,
        mock_get_user_profile_result,
    ):
        user = User.objects.create_user(
            username='api-client',
            email='api-client@example.com',
            password='pw',
        )
        mock_exchange_code.return_value = {
            'access_token': 'spotify-access',
            'refresh_token': 'spotify-refresh',
            'expires_in': 3600,
            'scope': 'streaming',
        }
        mock_get_user_profile_result.return_value = {
            'ok': True,
            'data': {'id': 'spotify-user-id', 'email': 'spotify-user@example.com'},
        }

        response = self.client.get(
            '/api/spotify/callback/',
            {'code': 'spotify-code', 'state': issue_spotify_oauth_state(user)},
            HTTP_HOST='127.0.0.1:8000',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()['message'],
            'Spotify connected successfully!',
        )

    @patch('api.views.spotify_service.get_user_profile_result')
    @patch('api.views.spotify_service.exchange_code')
    def test_callback_updates_user_with_configured_redirect_uri(
        self,
        mock_exchange_code,
        mock_get_user_profile_result,
    ):
        user = User.objects.create_user(
            username='spotify-user',
            email='spotify@example.com',
            password='password123',
        )
        mock_exchange_code.return_value = {
            'access_token': 'spotify-access',
            'refresh_token': 'spotify-refresh',
            'expires_in': 3600,
            'scope': 'streaming user-read-playback-state user-modify-playback-state',
        }
        mock_get_user_profile_result.return_value = {
            'ok': True,
            'data': {
                'id': 'spotify-user-id',
                'email': 'spotify-user@example.com',
            },
        }

        before_request = timezone.now()
        response = self.client.get(
            '/api/spotify/callback/',
            {'code': 'spotify-code', 'state': issue_spotify_oauth_state(user)},
            HTTP_HOST='127.0.0.1:8000',
        )

        self.assertEqual(response.status_code, 200)
        mock_exchange_code.assert_called_once_with(
            'spotify-code',
            redirect_uri='http://127.0.0.1:8000/api/spotify/callback/',
        )
        mock_get_user_profile_result.assert_called_once_with('spotify-access')

        user.refresh_from_db()
        self.assertTrue(user.is_spotify_connected)
        self.assertEqual(user.spotify_access_token, 'spotify-access')
        self.assertEqual(user.spotify_refresh_token, 'spotify-refresh')
        self.assertEqual(
            user.spotify_granted_scopes,
            ['streaming', 'user-read-playback-state', 'user-modify-playback-state'],
        )
        self.assertEqual(user.spotify_id, 'spotify-user-id')
        self.assertGreaterEqual(
            user.spotify_token_expires,
            before_request + timedelta(seconds=3590),
        )

    @patch('api.views.spotify_service.get_user_profile_result')
    @patch('api.views.spotify_service.exchange_code')
    def test_callback_returns_forbidden_when_spotify_account_is_not_allowlisted(
        self,
        mock_exchange_code,
        mock_get_user_profile_result,
    ):
        user = User.objects.create_user(
            username='spotify-blocked-user',
            email='spotify-blocked@example.com',
            password='password123',
        )
        mock_exchange_code.return_value = {
            'access_token': 'spotify-access',
            'refresh_token': 'spotify-refresh',
            'expires_in': 3600,
            'scope': 'streaming user-read-playback-state user-modify-playback-state',
        }
        mock_get_user_profile_result.return_value = {
            'ok': False,
            'status_code': 403,
            'reason': 'developer_allowlist_required',
            'error': (
                'The user is not registered for this application. '
                'Please check your settings on developer dashboard.'
            ),
            'error_code': 'None',
            'response_json': {
                'error': {
                    'status': 403,
                    'message': (
                        'The user is not registered for this application. '
                        'Please check your settings on developer dashboard.'
                    ),
                },
            },
            'recommended_action': (
                'Spotify blocked this account because the app is still in Development Mode. '
                'Add the exact Spotify account to the Spotify Developer Dashboard user '
                'allowlist, then reconnect Spotify in EmoTune.'
            ),
        }

        response = self.client.get(
            '/api/spotify/callback/',
            {'code': 'spotify-code', 'state': issue_spotify_oauth_state(user)},
            HTTP_HOST='127.0.0.1:8000',
        )

        self.assertEqual(response.status_code, 403)
        body = response.json()
        self.assertEqual(
            body['spotify_profile_error']['reason'],
            'developer_allowlist_required',
        )
        self.assertIn('not registered', body['message'])

        user.refresh_from_db()
        self.assertFalse(user.is_spotify_connected)
        self.assertFalse(user.spotify_access_token)

    @patch('api.views.spotify_service.exchange_code')
    def test_callback_returns_structured_token_exchange_error(
        self,
        mock_exchange_code,
    ):
        mock_exchange_code.return_value = {
            'ok': False,
            'status_code': 400,
            'reason': 'client_credentials_invalid',
            'error': 'invalid_client',
            'error_code': 'invalid_client',
            'response_json': {
                'error': 'invalid_client',
                'error_description': 'Invalid client secret',
            },
            'recommended_action': (
                'SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET do not match the same '
                'Spotify app. Update the backend .env with the client secret for the '
                'current Spotify app, then restart Django.'
            ),
        }

        response = self.client.get(
            '/api/spotify/callback/',
            {'code': 'spotify-code', 'state': issue_spotify_oauth_state(self.auth_user)},
            HTTP_HOST='127.0.0.1:8000',
        )

        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertEqual(body['spotify_token_error']['reason'], 'client_credentials_invalid')
        self.assertEqual(body['spotify_token_error']['status_code'], 400)
        self.assertIn('client secret', body['message'])

    @patch('api.views.spotify_service.search_catalog')
    def test_search_tracks_returns_bad_gateway_with_spotify_failure_payload(
        self,
        mock_search_catalog,
    ):
        user = User.objects.create_user(
            username='search-user',
            email='search@example.com',
            password='password123',
        )
        mock_search_catalog.return_value = {
            'ok': False,
            'status_code': 403,
            'reason': 'developer_allowlist_required',
            'error': 'Check settings on https://developer.spotify.com/dashboard, the user may not be registered.',
            'error_code': '403',
            'recommended_action': 'Add this account to the allowlist.',
            'response_json': {'error': {'status': 403, 'message': 'user may not be registered'}},
            'attempts': [{'source': 'user', 'status_code': 403, 'reason': 'developer_allowlist_required'}],
            'token_failures': [],
        }

        client = APIClient()
        client.force_authenticate(user=user)
        response = client.get('/api/spotify/search-tracks/?q=love')

        self.assertEqual(response.status_code, 502)
        body = response.json()
        self.assertEqual(body['spotify']['reason'], 'developer_allowlist_required')
        self.assertEqual(body['spotify']['status_code'], 403)
        mock_search_catalog.assert_called_once_with('love', 'track', user=user, limit=20)

    @patch('api.views.spotify_service.get_playback_debug_status')
    def test_debug_status_returns_service_payload_for_authenticated_user(
        self,
        mock_debug_status,
    ):
        user = User.objects.create_user(
            username='debug-user',
            email='debug@example.com',
            password='password123',
        )
        mock_debug_status.return_value = {
            'spotify_connected': True,
            'account': {'has_premium': True},
            'devices': {'device_count': 1, 'has_active_device': True},
            'recommended_action': 'Ready to play.',
        }

        client = APIClient()
        client.force_authenticate(user=user)
        response = client.get('/api/spotify/debug-status/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['recommended_action'], 'Ready to play.')
        mock_debug_status.assert_called_once_with(user)

    @patch('api.views.spotify_service.prepare_playback')
    def test_prepare_playback_returns_service_payload_for_authenticated_user(
        self,
        mock_prepare_playback,
    ):
        user = User.objects.create_user(
            username='prepare-user',
            email='prepare@example.com',
            password='password123',
        )
        mock_prepare_playback.return_value = {
            'ok': True,
            'transfer_attempted': True,
            'transfer_succeeded': True,
            'blocking_issue': None,
            'recommended_action': 'Spotify playback is ready on this phone.',
        }

        client = APIClient()
        client.force_authenticate(user=user)
        response = client.post('/api/spotify/prepare-playback/', {}, format='json')

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['ok'])
        self.assertTrue(response.json()['transfer_succeeded'])
        mock_prepare_playback.assert_called_once_with(user, device_id=None)

    @patch('api.views.spotify_service.execute_playback_command')
    def test_player_control_returns_service_payload_for_authenticated_user(
        self,
        mock_execute_playback_command,
    ):
        user = User.objects.create_user(
            username='player-control-user',
            email='player-control@example.com',
            password='password123',
        )
        mock_execute_playback_command.return_value = {
            'ok': True,
            'action': 'play',
            'blocking_issue': None,
            'selected_device_name': '2409BRN2CA',
            'recommended_action': 'Spotify is playing the selected song on this device.',
        }

        client = APIClient()
        client.force_authenticate(user=user)
        response = client.post(
            '/api/spotify/player-control/',
            {'action': 'play', 'uri': 'spotify:track:track-1'},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['ok'])
        self.assertEqual(response.json()['action'], 'play')
        mock_execute_playback_command.assert_called_once_with(
            user,
            action='play',
            uri='spotify:track:track-1',
            device_id=None,
            position_ms=None,
            shuffle_enabled=None,
            repeat_mode=None,
        )

    @patch('api.views.spotify_service.execute_playback_command')
    def test_player_control_passes_extended_parameters_to_service(
        self,
        mock_execute_playback_command,
    ):
        user = User.objects.create_user(
            username='player-control-extended-user',
            email='player-control-extended@example.com',
            password='password123',
        )
        mock_execute_playback_command.return_value = {
            'ok': True,
            'action': 'seek',
            'blocking_issue': None,
            'selected_device_name': '2409BRN2CA',
            'recommended_action': 'Spotify playback jumped to the requested position.',
        }

        client = APIClient()
        client.force_authenticate(user=user)
        response = client.post(
            '/api/spotify/player-control/',
            {
                'action': 'seek',
                'position_ms': 45000,
                'shuffle_enabled': True,
                'repeat_mode': 'track',
            },
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        mock_execute_playback_command.assert_called_once_with(
            user,
            action='seek',
            uri=None,
            device_id=None,
            position_ms=45000,
            shuffle_enabled=True,
            repeat_mode='track',
        )

    def test_disconnect_spotify_clears_linked_account_state(self):
        user = User.objects.create_user(
            username='disconnect-user',
            email='disconnect@example.com',
            password='password123',
        )
        user.is_spotify_connected = True
        user.spotify_access_token = 'spotify-access'
        user.spotify_refresh_token = 'spotify-refresh'
        user.spotify_granted_scopes = ['streaming', 'app-remote-control']
        user.spotify_token_expires = timezone.now() + timedelta(hours=1)
        user.spotify_id = 'spotify-user-id'
        user.save()

        client = APIClient()
        client.force_authenticate(user=user)
        response = client.post('/api/spotify/disconnect/', {}, format='json')

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['ok'])
        self.assertEqual(response.json()['previous_spotify_id'], 'spotify-user-id')

        user.refresh_from_db()
        self.assertFalse(user.is_spotify_connected)
        self.assertIsNone(user.spotify_access_token)
        self.assertIsNone(user.spotify_refresh_token)
        self.assertEqual(user.spotify_granted_scopes, [])
        self.assertIsNone(user.spotify_token_expires)
        self.assertIsNone(user.spotify_id)


class AdminPanelAccessTests(TestCase):
    """The dashboard page itself must be staff-only, not just its API."""

    def setUp(self):
        self.staff = User.objects.create_user(
            username='dash-staff',
            email='dash-staff@example.com',
            password='password123',
            is_staff=True,
        )
        self.regular = User.objects.create_user(
            username='dash-regular',
            email='dash-regular@example.com',
            password='password123',
        )

    def test_anonymous_visitor_is_sent_to_the_login_page(self):
        response = self.client.get('/admin-panel/')

        self.assertEqual(response.status_code, 302)
        self.assertIn('/django-admin/login/', response['Location'])

    def test_signed_in_non_staff_user_cannot_open_the_dashboard(self):
        self.client.force_login(self.regular)

        response = self.client.get('/admin-panel/')

        self.assertEqual(response.status_code, 302)
        self.assertIn('/django-admin/login/', response['Location'])

    def test_staff_user_gets_the_dashboard_with_an_api_token(self):
        self.client.force_login(self.staff)

        response = self.client.get('/admin-panel/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            AccessToken(response.context['admin_access_token'])['user_id'],
            self.staff.id,
        )
        # The page no longer collects credentials of its own.
        self.assertNotContains(response, 'id="login-password"')

    def test_template_comments_do_not_leak_into_the_page(self):
        # A {# #} comment only works on one line. A multi-line one rendered as
        # text and, with body as a flex row, pushed the dashboard ~260px right.
        self.client.force_login(self.staff)

        response = self.client.get('/admin-panel/')

        self.assertNotContains(response, '{#')
        self.assertNotContains(response, '{%')

    def test_root_url_routes_to_the_gated_dashboard(self):
        response = self.client.get('/')

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], '/admin-panel/')


class AnalyzeEmotionTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='analyze-user',
            email='analyze@example.com',
            password='password123',
        )
        self.client.force_authenticate(user=self.user)

    @patch('api.views.spotify_service.get_recommendations_with_details')
    @patch('api.views.get_classifier')
    def test_analyze_emotion_returns_response_when_spotify_fails(
        self,
        mock_get_classifier,
        mock_get_recommendations_with_details,
    ):
        mock_get_classifier.return_value.predict.return_value = {
            'emotion': 'happy',
            'confidence': 0.91,
            'all_scores': {'happy': 0.91, 'mixed': 0.09},
            'top_emotions': [
                {'emotion': 'happy', 'confidence': 0.91},
                {'emotion': 'mixed', 'confidence': 0.09},
            ],
            'prediction_source': 'bert',
            'prediction_strategy': 'bert_high_confidence',
            'confidence_band': 'high',
            'confidence_margin': 0.82,
            'fallback_used': False,
            'fallback_reason': None,
            'needs_review': False,
            'secondary_emotion': 'mixed',
        }
        mock_get_recommendations_with_details.side_effect = RuntimeError('spotify unavailable')

        response = self.client.post(
            '/api/analyze/',
            {'text': 'I am feeling great today'},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['emotion'], 'happy')
        self.assertEqual(response.json()['tracks'], [])
        self.assertEqual(response.json()['prediction_strategy'], 'bert_high_confidence')
        self.assertEqual(response.json()['prediction_source'], 'bert')
        self.assertIn('plutchik_scores', response.json())
        self.assertEqual(response.json()['plutchik_dominant_emotion'], 'joy')
        self.assertEqual(response.json()['plutchik_profile_version'], 'v1')
        self.assertFalse(response.json()['prediction_fallback_used'])
        self.assertTrue(response.json()['tracks_fallback_used'])
        self.assertEqual(response.json()['tracks_source'], 'fallback')
        self.assertEqual(PromptHistory.objects.count(), 1)

    @patch('api.views.spotify_service.get_recommendations_with_details')
    @patch('api.views.get_classifier')
    def test_analyze_emotion_returns_session_and_taste_metadata_for_custom_lane(
        self,
        mock_get_classifier,
        mock_get_recommendations_with_details,
    ):
        mock_get_classifier.return_value.predict.return_value = {
            'emotion': 'stressed',
            'confidence': 0.94,
            'all_scores': {'stressed': 0.94, 'calm': 0.06},
            'top_emotions': [
                {'emotion': 'stressed', 'confidence': 0.94},
                {'emotion': 'calm', 'confidence': 0.06},
            ],
            'prediction_source': 'bert',
            'prediction_strategy': 'bert_high_confidence',
            'confidence_band': 'high',
            'confidence_margin': 0.88,
            'fallback_used': False,
            'fallback_reason': None,
            'needs_review': False,
            'secondary_emotion': 'calm',
        }
        mock_get_recommendations_with_details.return_value = {
            'tracks': [{
                'id': 'track-focus-1',
                'item_type': 'track',
                'name': 'Deep Work',
                'artist': 'Focus Artist',
                'album': 'Momentum',
                'image': '',
                'preview_url': None,
                'duration_ms': 180000,
                'spotify_url': 'https://open.spotify.com/track/track-focus-1',
                'uri': 'spotify:track:track-focus-1',
                'recommendation_source': 'spotify_catalog',
            }],
            'source': 'spotify',
            'used_fallback': False,
            'fallback_reason': None,
            'personalized': False,
            'personalization_sources': [],
            'personalization_missing_scopes': [],
        }

        response = self.client.post(
            '/api/analyze/',
            {
                'text': 'I need to settle down and focus.',
                'outcome_mode': 'calm_me_down',
                'session_length_minutes': 45,
                'check_in_frequency_tracks': 4,
                'taste_profile': {
                    'familiarity': 'discovery',
                    'prefer_instrumental': True,
                    'train_session': False,
                },
            },
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['outcome_mode'], 'calm_me_down')
        self.assertEqual(body['taste_profile']['familiarity'], 'discovery')
        self.assertTrue(body['taste_profile']['prefer_instrumental'])
        self.assertFalse(body['taste_profile']['train_session'])
        self.assertEqual(body['session_plan']['target_minutes'], 45)
        self.assertEqual(body['session_plan']['check_in_after_tracks'], 4)
        self.assertEqual(body['session_plan']['mode'], 'calm_me_down')
        self.assertEqual(
            mock_get_recommendations_with_details.call_args.kwargs['taste_profile'],
            {
                'familiarity': 'discovery',
                'prefer_instrumental': True,
                'train_session': False,
            },
        )

        history = PromptHistory.objects.get(user=self.user)
        self.assertEqual(
            history.music_picker_data['personalization']['familiarity'],
            'discovery',
        )
        self.assertFalse(history.music_picker_data['personalization']['train_session'])
        self.assertEqual(
            history.music_picker_data['session_plan']['target_minutes'],
            45,
        )

    @patch(
        'api.views.spotify_service.get_recommendations_with_details',
        return_value={
            'tracks': [],
            'source': 'fallback',
            'used_fallback': True,
            'fallback_reason': 'classifier_failed',
        },
    )
    @patch('api.views.get_classifier', side_effect=RuntimeError('classifier crashed'))
    def test_analyze_emotion_falls_back_when_classifier_fails(
        self,
        _mock_get_classifier,
        _mock_get_recommendations_with_details,
    ):
        response = self.client.post(
            '/api/analyze/',
            {'text': 'I do not know how I feel'},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['emotion'], 'mixed')
        self.assertEqual(response.json()['confidence'], 35.0)
        self.assertEqual(response.json()['prediction_strategy'], 'system_fallback')
        self.assertTrue(response.json()['prediction_fallback_used'])
        self.assertTrue(response.json()['needs_review'])
        self.assertIn('ai_response', response.json())

    @patch('api.views.spotify_service.get_recommendations_with_details')
    @patch('api.views.get_classifier')
    def test_analyze_emotion_normalizes_tracks_with_only_spotify_url(
        self,
        mock_get_classifier,
        mock_get_recommendations_with_details,
    ):
        mock_get_classifier.return_value.predict.return_value = {
            'emotion': 'sad',
            'confidence': 0.89,
            'all_scores': {'sad': 0.89, 'mixed': 0.11},
            'top_emotions': [
                {'emotion': 'sad', 'confidence': 0.89},
                {'emotion': 'mixed', 'confidence': 0.11},
            ],
            'prediction_source': 'bert',
            'prediction_strategy': 'bert_high_confidence',
            'confidence_band': 'high',
            'confidence_margin': 0.78,
            'fallback_used': False,
            'fallback_reason': None,
            'needs_review': False,
            'secondary_emotion': 'mixed',
        }
        mock_get_recommendations_with_details.return_value = {
            'tracks': [{
                'id': '',
                'item_type': 'playlist',
                'name': 'Sad Songs',
                'artist': 'Spotify',
                'album': 'Curated comfort playlist',
                'image': '',
                'preview_url': None,
                'duration_ms': 0,
                'spotify_url': 'https://open.spotify.com/playlist/37i9dQZF1DX7qK8ma5wgG1',
                'uri': '',
            }],
            'source': 'spotify',
            'used_fallback': False,
            'fallback_reason': None,
        }

        response = self.client.post(
            '/api/analyze/',
            {'text': 'I feel sad today'},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        track = response.json()['tracks'][0]
        self.assertEqual(track['uri'], 'spotify:playlist:37i9dQZF1DX7qK8ma5wgG1')
        self.assertEqual(
            track['spotify_url'],
            'https://open.spotify.com/playlist/37i9dQZF1DX7qK8ma5wgG1',
        )
        self.assertEqual(
            response.json()['selected_track']['spotify_url'],
            'https://open.spotify.com/playlist/37i9dQZF1DX7qK8ma5wgG1',
        )

    @patch('api.views.spotify_service.get_recommendations_with_details')
    @patch('api.views.get_classifier')
    def test_analyze_emotion_exposes_personalized_track_metadata(
        self,
        mock_get_classifier,
        mock_get_recommendations_with_details,
    ):
        mock_get_classifier.return_value.predict.return_value = {
            'emotion': 'romantic',
            'confidence': 0.87,
            'all_scores': {'romantic': 0.87, 'mixed': 0.13},
            'top_emotions': [
                {'emotion': 'romantic', 'confidence': 0.87},
                {'emotion': 'mixed', 'confidence': 0.13},
            ],
            'prediction_source': 'bert',
            'prediction_strategy': 'bert_high_confidence',
            'confidence_band': 'high',
            'confidence_margin': 0.74,
            'fallback_used': False,
            'fallback_reason': None,
            'needs_review': False,
            'secondary_emotion': 'mixed',
        }
        mock_get_recommendations_with_details.return_value = {
            'tracks': [{
                'id': 'track-123',
                'name': 'Favorite Song',
                'artist': 'Loved Artist',
                'album': 'Album',
                'image': '',
                'preview_url': None,
                'duration_ms': 123000,
                'spotify_url': 'https://open.spotify.com/track/track-123',
                'uri': 'spotify:track:track-123',
                'recommendation_source': 'spotify_top_tracks',
            }],
            'source': 'user_music',
            'used_fallback': False,
            'fallback_reason': None,
            'personalized': True,
            'personalization_sources': ['top_tracks'],
            'personalization_missing_scopes': ['user-read-recently-played'],
        }

        response = self.client.post(
            '/api/analyze/',
            {'text': 'Make me a love playlist'},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['tracks_personalized'])
        self.assertEqual(response.json()['tracks_personalization_sources'], ['top_tracks'])
        self.assertEqual(
            response.json()['tracks_personalization_missing_scopes'],
            ['user-read-recently-played'],
        )
        self.assertEqual(response.json()['selected_track']['id'], 'track-123')
        self.assertEqual(response.json()['selected_track_source'], 'spotify_top_tracks')

    @patch(
        'api.views.spotify_service.get_recommendations_with_details',
        return_value={
            'tracks': [],
            'source': 'fallback',
            'used_fallback': True,
            'fallback_reason': 'no_results',
        },
    )
    @patch('api.views.get_classifier')
    def test_analyze_emotion_ignores_legacy_open_in_spotify_preferences(
        self,
        mock_get_classifier,
        _mock_get_recommendations_with_details,
    ):
        UserPreference.objects.create(
            user=self.user,
            emotion='sad',
            spotify_track_id='legacy-item',
            track_name='Sad Mix',
            artist_name='Open in Spotify',
            play_count=5,
        )
        mock_get_classifier.return_value.predict.return_value = {
            'emotion': 'sad',
            'confidence': 0.91,
            'all_scores': {'sad': 0.91, 'mixed': 0.09},
            'top_emotions': [
                {'emotion': 'sad', 'confidence': 0.91},
                {'emotion': 'mixed', 'confidence': 0.09},
            ],
            'prediction_source': 'bert',
            'prediction_strategy': 'bert_high_confidence',
            'confidence_band': 'high',
            'confidence_margin': 0.82,
            'fallback_used': False,
            'fallback_reason': None,
            'needs_review': False,
            'secondary_emotion': 'mixed',
        }

        response = self.client.post(
            '/api/analyze/',
            {'text': 'I feel sad'},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['tracks'], [])

    @patch('api.views.music_picker.pick_playlist')
    @patch('api.views.spotify_service.get_recommendations_with_details')
    @patch('api.views.get_classifier')
    def test_analyze_emotion_surfaces_the_picker_playlist(
        self,
        mock_get_classifier,
        mock_get_recommendations_with_details,
        mock_pick_playlist,
    ):
        mock_get_classifier.return_value.predict.return_value = {
            'emotion': 'happy',
            'confidence': 0.92,
            'all_scores': {'happy': 0.92, 'mixed': 0.08},
            'top_emotions': [
                {'emotion': 'happy', 'confidence': 0.92},
                {'emotion': 'mixed', 'confidence': 0.08},
            ],
            'prediction_source': 'bert',
            'prediction_strategy': 'bert_high_confidence',
            'confidence_band': 'high',
            'confidence_margin': 0.84,
            'fallback_used': False,
            'fallback_reason': None,
            'needs_review': False,
            'secondary_emotion': 'mixed',
        }
        spotify_tracks = [
            {
                'id': 'track-a',
                'item_type': 'track',
                'name': 'First Song',
                'artist': 'Artist A',
                'album': 'Album A',
                'image': '',
                'preview_url': None,
                'duration_ms': 180000,
                'spotify_url': 'https://open.spotify.com/track/track-a',
                'uri': 'spotify:track:track-a',
                'recommendation_source': 'spotify_top_tracks',
            },
            {
                'id': 'track-b',
                'item_type': 'track',
                'name': 'Chosen Song',
                'artist': 'Artist B',
                'album': 'Album B',
                'image': '',
                'preview_url': None,
                'duration_ms': 181000,
                'spotify_url': 'https://open.spotify.com/track/track-b',
                'uri': 'spotify:track:track-b',
                'recommendation_source': 'spotify_saved_tracks',
            },
        ]
        mock_get_recommendations_with_details.side_effect = [
            {
                'tracks': spotify_tracks,
                'source': 'spotify',
                'used_fallback': False,
                'fallback_reason': None,
                'personalized': False,
                'personalization_sources': [],
                'personalization_missing_scopes': [],
            },
            {
                'tracks': spotify_tracks,
                'source': 'user_music',
                'used_fallback': False,
                'fallback_reason': None,
                'personalized': True,
                'personalization_sources': ['top_tracks', 'saved_tracks'],
                'personalization_missing_scopes': [],
            },
        ]
        mock_pick_playlist.return_value = {
            'ok': True,
            'strategy': 'linear_ranker_playlist',
            'tracks': [
                {
                    'id': 'track-b',
                    'item_type': 'track',
                    'name': 'Chosen Song',
                    'artist': 'Artist B',
                    'album': 'Album B',
                    'image': '',
                    'preview_url': None,
                    'duration_ms': 181000,
                    'spotify_url': 'https://open.spotify.com/track/track-b',
                    'uri': 'spotify:track:track-b',
                    'recommendation_source': 'spotify_saved_tracks',
                },
                {
                    'id': 'track-a',
                    'item_type': 'track',
                    'name': 'First Song',
                    'artist': 'Artist A',
                    'album': 'Album A',
                    'image': '',
                    'preview_url': None,
                    'duration_ms': 180000,
                    'spotify_url': 'https://open.spotify.com/track/track-a',
                    'uri': 'spotify:track:track-a',
                    'recommendation_source': 'spotify_top_tracks',
                },
            ],
            'selected_track': {
                'id': 'track-b',
                'item_type': 'track',
                'name': 'Chosen Song',
                'artist': 'Artist B',
                'album': 'Album B',
                'image': '',
                'preview_url': None,
                'duration_ms': 181000,
                'spotify_url': 'https://open.spotify.com/track/track-b',
                'uri': 'spotify:track:track-b',
                'recommendation_source': 'spotify_saved_tracks',
            },
            'playlist_track_ids': ['track-b', 'track-a'],
            'reason': 'Ranked on emotion fit and listening history.',
            'confidence': 0.81,
            'provider': 'picker_ranker',
            'model': 'picker_linear_default',
            'used_fallback': False,
            'error': None,
            'candidates': [],
            'intent': 'playlist',
            'artist_name': 'Artist B',
            'track_name': 'Chosen Song',
            'playlist_category': 'happy_mixed',
            'confirmation': 'Playing Chosen Song by Artist B for your happy mood.',
        }

        initial_response = self.client.post(
            '/api/analyze/',
            {'text': 'Pick me one bright song'},
            format='json',
        )
        self.assertEqual(initial_response.status_code, 200)
        initial_body = initial_response.json()
        self.assertEqual(initial_body['progressive_stage'], 'initial')
        self.assertTrue(initial_body['loading_more_tracks'])
        self.assertEqual(len(initial_body['tracks']), 1)
        self.assertEqual(initial_body['selected_track']['id'], 'track-a')
        self.assertEqual(initial_body['music_picker_strategy'], 'quick_primary_track')
        self.assertEqual(PromptHistory.objects.count(), 1)

        response = self.client.post(
            '/api/recommendation-playlist/',
            {'continuation_token': initial_body['continuation_token']},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['progressive_stage'], 'full')
        self.assertFalse(body['loading_more_tracks'])
        self.assertEqual(body['selected_track']['id'], 'track-b')
        self.assertEqual(body['tracks'][0]['id'], 'track-b')
        self.assertEqual(body['tracks'][1]['id'], 'track-a')
        self.assertEqual(body['music_picker_strategy'], 'linear_ranker_playlist')
        self.assertEqual(
            body['music_picker_reason'],
            'Ranked on emotion fit and listening history.',
        )
        self.assertEqual(body['music_picker_intent'], 'playlist')
        self.assertEqual(body['music_picker_artist_name'], 'Artist B')
        self.assertEqual(body['music_picker_track_name'], 'Chosen Song')
        self.assertEqual(body['music_picker_playlist_category'], 'happy_mixed')
        self.assertEqual(
            body['music_picker_confirmation'],
            'Playing Chosen Song by Artist B for your happy mood.',
        )
        self.assertFalse(body['music_picker_used_fallback'])
        self.assertEqual(PromptHistory.objects.count(), 1)
        history = PromptHistory.objects.get()
        self.assertEqual(len(history.playlist_data), 2)
        self.assertEqual(history.playlist_data[0]['id'], 'track-b')

    @patch('api.views.spotify_service.get_recommendations_with_details')
    @patch('api.views.get_classifier')
    def test_analyze_emotion_passes_emotion_stats_into_spotify_lookup(
        self,
        mock_get_classifier,
        mock_get_recommendations_with_details,
    ):
        mock_get_classifier.return_value.predict.return_value = {
            'emotion': 'stressed',
            'confidence': 0.76,
            'all_scores': {'stressed': 0.76, 'calm': 0.14, 'fear': 0.10},
            'top_emotions': [
                {'emotion': 'stressed', 'confidence': 0.76},
                {'emotion': 'calm', 'confidence': 0.14},
            ],
            'prediction_source': 'bert',
            'prediction_strategy': 'bert_high_confidence',
            'confidence_band': 'high',
            'confidence_margin': 0.62,
            'fallback_used': False,
            'fallback_reason': None,
            'needs_review': False,
            'secondary_emotion': 'calm',
        }
        mock_get_recommendations_with_details.return_value = {
            'tracks': [{
                'id': 'track-focus',
                'item_type': 'track',
                'name': 'Breathing Room',
                'artist': 'Ambient Artist',
                'album': 'Calm Focus',
                'image': '',
                'preview_url': None,
                'duration_ms': 180000,
                'spotify_url': 'https://open.spotify.com/track/track-focus',
                'uri': 'spotify:track:track-focus',
                'recommendation_source': 'spotify_catalog',
            }],
            'source': 'spotify',
            'used_fallback': False,
            'fallback_reason': None,
            'personalized': False,
            'personalization_sources': [],
            'personalization_missing_scopes': [],
        }
        response = self.client.post(
            '/api/analyze/',
            # Pinned to match_mood so this stays a test about the stats
            # reaching Spotify unaltered. "stressed" routes to calm_me_down by
            # default now, which deliberately blends the scores -- that steer
            # is covered in OutcomeModeRoutingTests.
            {'text': 'I need help calming down fast', 'outcome_mode': 'match_mood'},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        spotify_lookup_kwargs = mock_get_recommendations_with_details.call_args.kwargs
        self.assertEqual(
            spotify_lookup_kwargs['top_emotions'],
            [
                {'emotion': 'stressed', 'confidence': 0.76},
                {'emotion': 'calm', 'confidence': 0.14},
            ],
        )
        self.assertEqual(spotify_lookup_kwargs['all_scores']['stressed'], 0.76)
        self.assertEqual(spotify_lookup_kwargs['all_scores']['calm'], 0.14)
        self.assertEqual(spotify_lookup_kwargs['all_scores']['fear'], 0.10)
        self.assertNotIn('llm_queries', spotify_lookup_kwargs)
        self.assertNotIn('playlist_category', spotify_lookup_kwargs)
        self.assertNotIn('seed_artist_name', spotify_lookup_kwargs)
        self.assertNotIn('seed_track_name', spotify_lookup_kwargs)
        self.assertEqual(spotify_lookup_kwargs['limit'], 6)
        self.assertFalse(spotify_lookup_kwargs['include_personalization'])
        self.assertEqual(spotify_lookup_kwargs['time_budget_seconds'], 2.5)
        self.assertEqual(spotify_lookup_kwargs['query_mode'], 'default')

    @patch('api.views.music_picker.pick_playlist')
    @patch('api.views.spotify_service.get_recommendations_with_details')
    @patch('api.views.get_classifier')
    def test_analyze_emotion_handles_a_degraded_picker_result(
        self,
        mock_get_classifier,
        mock_get_recommendations_with_details,
        mock_pick_playlist,
    ):
        mock_get_classifier.return_value.predict.return_value = {
            'emotion': 'calm',
            'confidence': 0.89,
            'all_scores': {'calm': 0.89, 'mixed': 0.11},
            'top_emotions': [
                {'emotion': 'calm', 'confidence': 0.89},
                {'emotion': 'mixed', 'confidence': 0.11},
            ],
            'prediction_source': 'bert',
            'prediction_strategy': 'bert_high_confidence',
            'confidence_band': 'high',
            'confidence_margin': 0.78,
            'fallback_used': False,
            'fallback_reason': None,
            'needs_review': False,
            'secondary_emotion': 'mixed',
        }
        spotify_tracks = [{
            'id': 'track-primary',
            'item_type': 'track',
            'name': 'Quiet Song',
            'artist': 'Artist Calm',
            'album': 'Album Calm',
            'image': '',
            'preview_url': None,
            'duration_ms': 180000,
            'spotify_url': 'https://open.spotify.com/track/track-primary',
            'uri': 'spotify:track:track-primary',
            'recommendation_source': 'spotify_top_tracks',
        }]
        mock_get_recommendations_with_details.side_effect = [
            {
                'tracks': spotify_tracks,
                'source': 'spotify',
                'used_fallback': False,
                'fallback_reason': None,
                'personalized': False,
                'personalization_sources': [],
                'personalization_missing_scopes': [],
            },
            {
                'tracks': spotify_tracks,
                'source': 'user_music',
                'used_fallback': False,
                'fallback_reason': None,
                'personalized': True,
                'personalization_sources': ['top_tracks'],
                'personalization_missing_scopes': [],
            },
        ]
        mock_pick_playlist.return_value = {
            'ok': False,
            'strategy': 'heuristic_playlist',
            'tracks': spotify_tracks,
            'selected_track': spotify_tracks[0],
            'playlist_track_ids': ['track-primary'],
            'reason': None,
            'confidence': None,
            'provider': 'disabled',
            'model': None,
            'used_fallback': True,
            'error': 'no_ranked_candidates',
            'candidates': [],
            'intent': 'track',
            'artist_name': 'Artist Calm',
            'track_name': 'Quiet Song',
            'playlist_category': 'calm',
            'confirmation': 'Playing Quiet Song by Artist Calm.',
        }

        initial_response = self.client.post(
            '/api/analyze/',
            {'text': 'Play something calm'},
            format='json',
        )
        self.assertEqual(initial_response.status_code, 200)
        initial_body = initial_response.json()
        self.assertEqual(initial_body['music_picker_strategy'], 'quick_primary_track')

        response = self.client.post(
            '/api/recommendation-playlist/',
            {'continuation_token': initial_body['continuation_token']},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['selected_track']['id'], 'track-primary')
        self.assertEqual(body['music_picker_strategy'], 'heuristic_playlist')
        self.assertEqual(body['music_picker_intent'], 'track')
        self.assertEqual(body['music_picker_track_name'], 'Quiet Song')
        self.assertEqual(body['music_picker_confirmation'], 'Playing Quiet Song by Artist Calm.')
        self.assertTrue(body['music_picker_used_fallback'])
        initial_lookup_kwargs = mock_get_recommendations_with_details.call_args_list[0].kwargs
        continuation_lookup_kwargs = (
            mock_get_recommendations_with_details.call_args_list[1].kwargs
        )
        self.assertEqual(initial_lookup_kwargs['query_mode'], 'default')
        self.assertEqual(continuation_lookup_kwargs['query_mode'], 'continuation')
        self.assertFalse(continuation_lookup_kwargs['include_personalization'])
        self.assertEqual(continuation_lookup_kwargs['time_budget_seconds'], 8.0)


class ExplicitEmotionRecommendationTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='explicit-emotion-user',
            email='explicit@example.com',
            password='password123',
        )
        self.client.force_authenticate(user=self.user)

    @patch('api.views.spotify_service.get_recommendations_with_details')
    @patch('api.views.get_classifier')
    def test_recommend_by_emotion_bypasses_classifier_and_uses_selected_emotion(
        self,
        mock_get_classifier,
        mock_get_recommendations_with_details,
    ):
        mock_get_recommendations_with_details.return_value = {
            'tracks': [{
                'id': 'track-motivation',
                'item_type': 'track',
                'name': 'Rise Up',
                'artist': 'Focus Artist',
                'album': 'Momentum',
                'image': '',
                'preview_url': None,
                'duration_ms': 180000,
                'spotify_url': 'https://open.spotify.com/track/track-motivation',
                'uri': 'spotify:track:track-motivation',
                'recommendation_source': 'spotify_catalog',
            }],
            'source': 'spotify',
            'used_fallback': False,
            'fallback_reason': None,
            'personalized': False,
            'personalization_sources': [],
            'personalization_missing_scopes': [],
        }

        response = self.client.post(
            '/api/recommend-by-emotion/',
            {'emotion': 'motivational'},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['emotion'], 'motivational')
        self.assertEqual(body['prediction_strategy'], 'explicit_emotion_tab')
        self.assertEqual(body['tracks'][0]['id'], 'track-motivation')
        self.assertEqual(body['progressive_stage'], 'initial')
        self.assertTrue(body['loading_more_tracks'])
        self.assertTrue(body['continuation_token'])
        self.assertEqual(mock_get_recommendations_with_details.call_args.args[0], 'motivational')
        self.assertFalse(mock_get_recommendations_with_details.call_args.kwargs['include_personalization'])
        self.assertFalse(mock_get_classifier.called)
        self.assertEqual(PromptHistory.objects.count(), 0)

    @patch('api.views.spotify_service.get_recommendations_with_details')
    def test_recommend_by_emotion_persists_history_when_custom_controls_are_enabled(
        self,
        mock_get_recommendations_with_details,
    ):
        mock_get_recommendations_with_details.return_value = {
            'tracks': [{
                'id': 'track-calm-1',
                'item_type': 'track',
                'name': 'Slow Breathing',
                'artist': 'Calm Artist',
                'album': 'Reset',
                'image': '',
                'preview_url': None,
                'duration_ms': 175000,
                'spotify_url': 'https://open.spotify.com/track/track-calm-1',
                'uri': 'spotify:track:track-calm-1',
                'recommendation_source': 'spotify_catalog',
            }],
            'source': 'spotify',
            'used_fallback': False,
            'fallback_reason': None,
            'personalized': False,
            'personalization_sources': [],
            'personalization_missing_scopes': [],
        }

        response = self.client.post(
            '/api/recommend-by-emotion/',
            {
                'emotion': 'stressed',
                'outcome_mode': 'calm_me_down',
                'taste_profile': {
                    'familiarity': 'familiar',
                    'prefer_instrumental': True,
                    'train_session': True,
                },
            },
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['outcome_mode'], 'calm_me_down')
        self.assertEqual(body['taste_profile']['familiarity'], 'familiar')
        self.assertTrue(body['taste_profile']['prefer_instrumental'])
        self.assertIsNotNone(body['history_id'])
        self.assertEqual(PromptHistory.objects.count(), 1)

        history = PromptHistory.objects.get(user=self.user)
        self.assertEqual(
            history.music_picker_data['outcome_mode'],
            'calm_me_down',
        )
        self.assertEqual(
            history.music_picker_data['personalization']['familiarity'],
            'familiar',
        )

    def test_recommend_by_emotion_rejects_unknown_emotion(self):
        response = self.client.post(
            '/api/recommend-by-emotion/',
            {'emotion': 'confused'},
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('Emotion must be one of', response.json()['error'])


class ListeningPreferenceOptOutTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='listen-opt-out-user',
            email='listen-opt-out@example.com',
            password='password123',
        )
        self.client.force_authenticate(user=self.user)

    def test_listen_time_skips_training_when_session_learning_is_disabled(self):
        history = PromptHistory.objects.create(
            user=self.user,
            prompt_text='Keep me focused.',
            detected_emotion='motivational',
            emotion_confidence=0.88,
            emotion_scores={'motivational': 0.88, 'calm': 0.12},
            ai_response='response',
            playlist_data=[],
            music_picker_data={
                'personalization': {
                    'familiarity': 'discovery',
                    'prefer_instrumental': True,
                    'train_session': False,
                },
                'session_plan': build_session_plan(
                    outcome_mode='calm_me_down',
                    session_length_minutes=45,
                    check_in_frequency_tracks=4,
                ),
            },
            session_duration=0,
            felt_better_response=None,
        )

        response = self.client.post(
            '/api/users/listen-time/',
            {
                'track_id': 'track-focus-1',
                'emotion': 'motivational',
                'duration': 92,
                'track_name': 'Deep Work',
                'artist_name': 'Focus Artist',
                'item_type': 'track',
                'history_id': history.id,
            },
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'tracking_disabled')
        self.assertEqual(UserPreference.objects.count(), 0)
        self.assertEqual(ListeningSession.objects.count(), 0)

        history.refresh_from_db()
        self.assertEqual(history.session_duration, 92)
        self.assertEqual(
            history.music_picker_data['session_plan']['progress_seconds'],
            92,
        )


class SpotifyRecommendationTests(TestCase):
    def test_select_primary_track_prefers_track_items_over_playlist_items(self):
        selected_track = spotify_service.select_primary_track([
            {
                'id': 'playlist-1',
                'item_type': 'playlist',
                'name': 'Mood Mix',
                'artist': 'Spotify',
                'spotify_url': 'https://open.spotify.com/playlist/playlist-1',
                'uri': 'spotify:playlist:playlist-1',
            },
            {
                'id': 'track-55',
                'item_type': 'track',
                'name': 'Signal Song',
                'artist': 'Artist',
                'spotify_url': 'https://open.spotify.com/track/track-55',
                'uri': 'spotify:track:track-55',
            },
        ])

        self.assertIsNotNone(selected_track)
        self.assertEqual(selected_track['id'], 'track-55')
        self.assertEqual(selected_track['item_type'], 'track')

    def test_rank_tracks_for_emotion_prefers_aligned_track(self):
        ranked_tracks = spotify_service.rank_tracks_for_emotion(
            [
                {
                    'id': 'track-party',
                    'item_type': 'track',
                    'name': 'Beast Mode Party',
                    'artist': 'Hype Crew',
                    'album': 'Workout Anthems',
                    'recommendation_source': 'spotify_catalog',
                    'selection_reasons': [],
                },
                {
                    'id': 'track-calm',
                    'item_type': 'track',
                    'name': 'Peaceful Focus',
                    'artist': 'Ambient Artist',
                    'album': 'Meditation Tones',
                    'recommendation_source': 'spotify_saved_tracks',
                    'selection_reasons': ['emotion_keyword_match', 'emotion_genre_match'],
                    'personalization_score': 2.0,
                },
            ],
            emotion='stressed',
            top_emotions=[{'emotion': 'stressed', 'confidence': 0.81}],
            confidence_band='high',
            preferred_artists=[],
            limit=2,
        )

        self.assertEqual(ranked_tracks[0]['id'], 'track-calm')
        self.assertGreater(
            ranked_tracks[0]['emotion_alignment_score'],
            ranked_tracks[1]['emotion_alignment_score'],
        )

    def test_rank_tracks_for_emotion_penalizes_recent_cross_emotion_repeats(self):
        user = User.objects.create_user(
            username='repeat-penalty-user',
            email='repeat-penalty@example.com',
            password='password123',
        )
        PromptHistory.objects.create(
            user=user,
            prompt_text='I feel calm',
            detected_emotion='calm',
            emotion_confidence=0.9,
            emotion_scores={'calm': 0.9},
            ai_response='response',
            playlist_data=[{
                'id': 'track-repeated',
                'item_type': 'track',
                'name': 'Peaceful Focus',
                'artist': 'Ambient Artist',
                'uri': 'spotify:track:track-repeated',
            }],
        )

        context = spotify_service._build_personalization_context('stressed', user=user)
        repeated_track = spotify_service._score_personalized_track(
            {
                'id': 'track-repeated',
                'item_type': 'track',
                'name': 'Peaceful Focus',
                'artist': 'Ambient Artist',
                'album': 'Meditation Tones',
                'recommendation_source': 'spotify_saved_tracks',
            },
            context,
        )
        fresh_track = spotify_service._score_personalized_track(
            {
                'id': 'track-fresh',
                'item_type': 'track',
                'name': 'Breathing Room',
                'artist': 'Ambient Artist',
                'album': 'Meditation Tones',
                'recommendation_source': 'spotify_saved_tracks',
            },
            context,
        )

        self.assertLess(
            repeated_track['personalization_score'],
            fresh_track['personalization_score'],
        )
        self.assertIn(
            'cross_emotion_repeat_penalty',
            repeated_track['selection_reasons'],
        )

    def test_score_personalized_track_penalizes_generic_track_without_emotion_signal(self):
        context = spotify_service._build_personalization_context('happy')
        generic_track = spotify_service._score_personalized_track(
            {
                'id': 'track-generic',
                'item_type': 'track',
                'name': 'No Surprises',
                'artist': 'Radiohead',
                'album': 'OK Computer',
                'recommendation_source': 'spotify_top_tracks',
            },
            context,
        )
        aligned_track = spotify_service._score_personalized_track(
            {
                'id': 'track-aligned',
                'item_type': 'track',
                'name': 'Happy Sunshine',
                'artist': 'Joy Club',
                'album': 'Feel Good Summer',
                'recommendation_source': 'spotify_top_tracks',
            },
            context,
        )

        self.assertIn(
            'generic_personalization_penalty',
            generic_track['selection_reasons'],
        )
        self.assertGreater(
            aligned_track['personalization_score'],
            generic_track['personalization_score'],
        )

    def test_get_recommendations_with_details_keeps_searching_after_personalized_tracks_fill_limit(self):
        user = User.objects.create_user(
            username='hybrid-recommendation-user',
            email='hybrid-recommendation@example.com',
            password='password123',
        )

        personalized_tracks = [
            {
                'id': f'personal-{index}',
                'item_type': 'track',
                'name': f'Personal {index}',
                'artist': 'Favorite Artist',
                'album': 'Album',
                'spotify_url': f'https://open.spotify.com/track/personal-{index}',
                'uri': f'spotify:track:personal-{index}',
                'recommendation_source': 'spotify_top_tracks',
                'personalization_score': 2.0,
            }
            for index in range(3)
        ]
        search_track = {
            'id': 'search-1',
            'item_type': 'track',
            'name': 'Calming Search Result',
            'artist': 'Ambient Artist',
            'album': 'Search Album',
            'spotify_url': 'https://open.spotify.com/track/search-1',
            'uri': 'spotify:track:search-1',
            'recommendation_source': 'spotify_catalog',
        }

        with patch.object(
            spotify_service,
            'get_user_music_candidates',
            return_value={
                'tracks': personalized_tracks,
                'sources_used': ['top_tracks'],
                'missing_scopes': [],
                'errors': [],
            },
        ):
            with patch.object(
                spotify_service,
                '_get_catalog_token_candidates',
                return_value=([('client', 'client-token')], []),
            ):
                with patch.object(
                    spotify_service,
                    '_build_recommendation_queries',
                    return_value=['calm ambient'],
                ):
                    with patch.object(
                        spotify_service,
                        'search_tracks_detailed',
                        return_value={'ok': True, 'items': [search_track]},
                    ):
                        result = spotify_service.get_recommendations_with_details(
                            'calm',
                            user=user,
                            limit=3,
                        )

        self.assertTrue(result['ok'])
        self.assertEqual(result['source'], 'hybrid_user_music_spotify')
        self.assertIn('calm ambient', result['queries_tried'])
        self.assertTrue(any(track['id'] == 'search-1' for track in result['tracks']))

    def test_get_recommendations_falls_back_when_personalized_tracks_are_generic_across_emotions(self):
        user = User.objects.create_user(
            username='generic-personalized-user',
            email='generic-personalized@example.com',
            password='password123',
        )
        user.is_spotify_connected = True
        user.spotify_access_token = 'spotify-token'
        user.spotify_refresh_token = 'spotify-refresh'
        user.spotify_granted_scopes = [
            'user-top-read',
            'user-library-read',
        ]
        user.spotify_token_expires = timezone.now() + timedelta(hours=1)
        user.save()

        top_tracks_payload = {
            'ok': True,
            'status_code': 200,
            'data': {
                'items': [
                    {
                        'id': 'track-top-1',
                        'name': 'No Surprises',
                        'artists': [{'name': 'Radiohead'}],
                        'album': {'name': 'OK Computer', 'images': []},
                        'external_urls': {'spotify': 'https://open.spotify.com/track/track-top-1'},
                        'uri': 'spotify:track:track-top-1',
                        'duration_ms': 180000,
                        'popularity': 85,
                    },
                    {
                        'id': 'track-top-2',
                        'name': 'Tek It',
                        'artists': [{'name': 'Cafune'}],
                        'album': {'name': 'Running', 'images': []},
                        'external_urls': {'spotify': 'https://open.spotify.com/track/track-top-2'},
                        'uri': 'spotify:track:track-top-2',
                        'duration_ms': 180000,
                        'popularity': 80,
                    },
                ],
            },
            'response_text': '{"items":[...]}',
        }

        saved_tracks_payload = {
            'ok': True,
            'status_code': 200,
            'data': {
                'items': [],
            },
            'response_text': '{"items":[]}',
        }

        def fake_spotify_get(token, path, params=None, timeout_seconds=None):
            if path == '/me/top/tracks':
                return top_tracks_payload
            if path == '/me/tracks':
                return saved_tracks_payload
            self.fail(f'unexpected endpoint requested: {path}')

        with patch.object(
            spotify_service,
            'ensure_valid_token_with_details',
            return_value={
                'access_token': 'spotify-token',
                'refresh_attempted': False,
                'refresh_succeeded': False,
                'refresh_error': None,
                'granted_scopes': ['user-top-read', 'user-library-read'],
            },
        ):
            with patch.object(spotify_service, '_spotify_get', side_effect=fake_spotify_get):
                with patch.object(
                    spotify_service,
                    '_get_catalog_token_candidates',
                    return_value=([('client', 'token')], []),
                ):
                    with patch.object(
                        spotify_service,
                        'search_tracks_detailed',
                        return_value={
                            'ok': True,
                            'items': [],
                            'status_code': 200,
                            'error': None,
                            'response_text': '',
                        },
                    ):
                        result = spotify_service.get_recommendations_with_details(
                            'happy',
                            user=user,
                            limit=4,
                        )

        self.assertTrue(result['ok'])
        self.assertEqual(result['source'], 'fallback')
        self.assertTrue(all(
            track['recommendation_source'] == 'curated_fallback'
            for track in result['tracks']
        ))

    def test_llm_request_payload_includes_alignment_metadata(self):
        picker = LLMMusicPicker()
        picker.provider = 'openai_compatible'
        picker.api_url = 'https://llm.example.test/v1/chat/completions'
        payload = picker._build_request_payload(
            prompt_text='I feel overwhelmed and need to calm down.',
            emotion='stressed',
            top_emotions=[{'emotion': 'stressed', 'confidence': 0.82}],
            all_scores={
                'stressed': 0.82,
                'fear': 0.11,
                'calm': 0.07,
            },
            confidence_band='high',
            confidence_margin=0.24,
            candidates=[
                {
                    'candidate_id': 'track-1',
                    'name': 'Peaceful Focus',
                    'artist': 'Ambient Artist',
                    'album': 'Meditation Tones',
                    'recommendation_source': 'spotify_saved_tracks',
                    'selection_reasons': ['emotion_keyword_match'],
                    'emotion_alignment_score': 6.2,
                    'emotion_alignment_reasons': ['keyword_fit:stressed'],
                    'personalization_score': 2.1,
                    'is_preferred': False,
                },
            ],
            preferred_artists=[],
            playlist_size=1,
        )

        self.assertIn('emotion_alignment_score', payload['messages'][1]['content'])
        self.assertIn('emotion_guidance', payload['messages'][1]['content'])
        self.assertIn('all_scores', payload['messages'][1]['content'])
        self.assertIn('confidence_margin', payload['messages'][1]['content'])

    @patch('api.http_client.post')
    def test_build_search_plan_fills_with_fallback_queries(self, mock_post):
        picker = LLMMusicPicker()
        picker.enabled = True
        picker.api_url = 'https://llm.example.test/v1/chat/completions'
        picker.api_key = 'test-key'
        picker.model = 'test-model'
        picker.search_query_count = 4

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'choices': [{
                'message': {
                    'content': json.dumps({
                        'search_queries': ['bright pop'],
                        'reason': 'Use a bright pop seed first.',
                        'confidence': 0.84,
                        'intent': 'mood',
                        'playlist_category': 'bright pop',
                        'confirmation': 'Searching Spotify for bright pop.',
                    }),
                },
            }],
        }
        mock_post.return_value = mock_response

        result = picker.build_search_plan(
            prompt_text='Play something bright and cheerful.',
            emotion='happy',
            top_emotions=[{'emotion': 'happy', 'confidence': 0.82}],
            all_scores={'happy': 0.82, 'mixed': 0.18},
            confidence_band='high',
            confidence_margin=0.64,
            preferred_artists=['Taylor Swift'],
            search_query_count=4,
        )

        self.assertTrue(result['ok'])
        self.assertEqual(result['strategy'], 'llm_search_plan')
        self.assertEqual(result['search_queries'][0], 'bright pop')
        self.assertEqual(len(result['search_queries']), 4)
        self.assertEqual(result['playlist_category'], 'bright pop')

    @patch('api.http_client.post')
    def test_build_search_plan_supports_gemini_provider(self, mock_post):
        picker = LLMMusicPicker()
        picker.enabled = True
        picker.provider = 'gemini'
        picker.api_url = ''
        picker.api_key = 'gemini-key'
        picker.model = 'gemini-2.5-flash'
        picker.gemini_api_version = 'v1beta'
        picker.search_query_count = 3

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'candidates': [{
                'content': {
                    'parts': [{
                        'text': json.dumps({
                            'search_queries': ['calm focus', 'ambient reset'],
                            'reason': 'Blend calm and focus cues.',
                            'confidence': 0.88,
                            'intent': 'mood',
                            'playlist_category': 'calm focus',
                            'confirmation': 'Searching Spotify for calm focus songs.',
                        }),
                    }],
                },
            }],
        }
        mock_post.return_value = mock_response

        result = picker.build_search_plan(
            prompt_text='I need something calming but still focused.',
            emotion='stressed',
            top_emotions=[{'emotion': 'stressed', 'confidence': 0.81}],
            all_scores={'stressed': 0.81, 'calm': 0.19},
            confidence_band='high',
            confidence_margin=0.62,
            preferred_artists=[],
            search_query_count=3,
        )

        self.assertTrue(result['ok'])
        self.assertEqual(result['provider'], 'gemini')
        self.assertEqual(result['search_queries'][0], 'calm focus')
        self.assertIn(
            '/v1beta/models/gemini-2.5-flash:generateContent',
            mock_post.call_args.args[0],
        )
        self.assertEqual(
            mock_post.call_args.kwargs['headers']['x-goog-api-key'],
            'gemini-key',
        )
        self.assertNotIn('Authorization', mock_post.call_args.kwargs['headers'])
        self.assertEqual(
            mock_post.call_args.kwargs['json']['generationConfig']['responseMimeType'],
            'application/json',
        )
        self.assertIn(
            'systemInstruction',
            mock_post.call_args.kwargs['json'],
        )
        self.assertNotIn(
            'additionalProperties',
            json.dumps(
                mock_post.call_args.kwargs['json']['generationConfig']['responseSchema']
            ),
        )

    def test_build_recommendation_queries_prioritizes_llm_queries_and_blended_emotions(self):
        queries = spotify_service._build_recommendation_queries(
            'happy',
            preferred_artists=['Taylor Swift'],
            top_emotions=[
                {'emotion': 'happy', 'confidence': 0.54},
                {'emotion': 'nostalgic', 'confidence': 0.28},
            ],
            all_scores={'happy': 0.54, 'nostalgic': 0.28, 'calm': 0.18},
            llm_queries=['bright pop', 'sunset drive throwback'],
            playlist_category='bright pop',
            seed_artist_name='Katrina & The Waves',
            seed_track_name='Walking on Sunshine',
        )

        self.assertGreaterEqual(len(queries), 4)
        self.assertEqual(
            queries[0],
            'track:"Walking on Sunshine" artist:"Katrina & The Waves"',
        )
        self.assertEqual(queries[1], '"Walking on Sunshine" "Katrina & The Waves"')
        self.assertIn('bright pop', queries)
        self.assertIn('happy nostalgic', queries)
        self.assertTrue(any('artist:"Taylor Swift"' in query for query in queries))

    def test_build_recommendation_queries_uses_music_doc_sad_seed_tracks(self):
        queries = spotify_service._build_recommendation_queries(
            'sad',
            preferred_artists=[],
            top_emotions=[{'emotion': 'sad', 'confidence': 1.0}],
            all_scores={'sad': 1.0},
        )

        self.assertEqual(
            queries[0],
            'track:"The Cure" artist:"Olivia Rodrigo"',
        )
        self.assertIn('track:"Multo" artist:"Cup of Joe"', queries)
        self.assertIn('sad heartbreak songs', queries)
        self.assertIn('heartbreak ballads', queries)

    def test_build_recommendation_queries_uses_music_doc_profiles_for_other_emotions(self):
        cases = [
            (
                'angry',
                'track:"Good Luck, Babe!" artist:"Chappell Roan"',
                'angry rock songs',
            ),
            (
                'motivational',
                'track:"Unstoppable" artist:"Sia"',
                'motivational pump up songs',
            ),
            (
                'fear',
                'track:"Weightless" artist:"Marconi Union"',
                'calming songs for anxiety',
            ),
        ]

        for emotion, expected_first_query, expected_phrase in cases:
            queries = spotify_service._build_recommendation_queries(
                emotion,
                preferred_artists=[],
                top_emotions=[{'emotion': emotion, 'confidence': 1.0}],
                all_scores={emotion: 1.0},
            )
            self.assertEqual(queries[0], expected_first_query)
            self.assertIn(expected_phrase, queries)

    def test_build_recommendation_queries_continuation_mode_uses_music_doc_playlist(self):
        queries = spotify_service._build_recommendation_queries(
            'angry',
            preferred_artists=[],
            top_emotions=[{'emotion': 'angry', 'confidence': 1.0}],
            all_scores={'angry': 1.0},
            query_mode='continuation',
        )

        self.assertEqual(
            queries[0],
            'track:"Good Luck, Babe!" artist:"Chappell Roan"',
        )
        self.assertIn('track:"Bazinga" artist:"SB19"', queries)
        self.assertIn('angry rock songs', queries)

    def test_emotion_query_profiles_use_music_doc_seed_catalogs(self):
        for emotion in MUSIC_PICKER_DOC_EMOTIONS:
            profile = EMOTION_QUERY_PROFILES[emotion]
            seed_tracks = profile.get('seed_tracks') or []

            self.assertEqual(len(seed_tracks), 10, emotion)
            self.assertTrue(
                all(seed.get('source') == 'music_doc' for seed in seed_tracks),
                emotion,
            )

    def test_search_tracks_detailed_clamps_limit_before_spotify_request(self):
        with patch.object(
            spotify_service,
            '_spotify_get',
            return_value={
                'ok': True,
                'status_code': 200,
                'data': {'tracks': {'items': []}},
                'response_text': '{"tracks":{"items":[]}}',
            },
        ) as mock_spotify_get:
            result = spotify_service.search_tracks_detailed(
                'someone you loved',
                'spotify-token',
                limit=999,
            )

        self.assertTrue(result['ok'])
        self.assertEqual(result['limit'], 10)
        self.assertEqual(
            mock_spotify_get.call_args.kwargs['params']['limit'],
            10,
        )

    def test_search_artists_detailed_defaults_invalid_limit_before_spotify_request(self):
        with patch.object(
            spotify_service,
            '_spotify_get',
            return_value={
                'ok': True,
                'status_code': 200,
                'data': {'artists': {'items': []}},
                'response_text': '{"artists":{"items":[]}}',
            },
        ) as mock_spotify_get:
            result = spotify_service.search_artists_detailed(
                'Lewis Capaldi',
                'spotify-token',
                limit='',
            )

        self.assertTrue(result['ok'])
        self.assertEqual(result['limit'], 5)
        self.assertEqual(
            mock_spotify_get.call_args.kwargs['params']['limit'],
            5,
        )

    def test_get_recommendations_clamps_search_limit_inside_query_loop(self):
        with patch.object(
            spotify_service,
            'get_user_music_candidates',
            return_value={
                'ok': False,
                'tracks': [],
                'sources_used': [],
                'missing_scopes': [],
                'errors': [],
                'token_error': None,
            },
        ), patch.object(
            spotify_service,
            '_get_catalog_token_candidates',
            return_value=([('client', 'spotify-token')], []),
        ), patch.object(
            spotify_service,
            '_build_recommendation_queries',
            return_value=['sad songs'],
        ), patch.object(
            spotify_service,
            'search_tracks_detailed',
            return_value={
                'ok': True,
                'items': [],
                'status_code': 200,
                'error': None,
                'response_text': '{}',
            },
        ) as mock_search_tracks:
            spotify_service.get_recommendations_with_details(
                'sad',
                user=None,
                preferred_artists=[],
                top_emotions=[{'emotion': 'sad', 'confidence': 1.0}],
                all_scores={'sad': 1.0},
                limit=20,
            )

        self.assertEqual(
            mock_search_tracks.call_args.kwargs['limit'],
            10,
        )

    def test_sanitize_recommendations_dedupes_track_variants(self):
        sanitized = spotify_service.sanitize_recommendations(
            [
                {
                    'id': 'track-1',
                    'item_type': 'track',
                    'name': 'Someone You Loved',
                    'artist': 'Lewis Capaldi',
                    'spotify_url': 'https://open.spotify.com/track/track-1',
                    'uri': 'spotify:track:track-1',
                },
                {
                    'id': 'track-2',
                    'item_type': 'track',
                    'name': 'Someone You Loved - Future Humans Remix',
                    'artist': 'Lewis Capaldi, Future Humans',
                    'spotify_url': 'https://open.spotify.com/track/track-2',
                    'uri': 'spotify:track:track-2',
                },
                {
                    'id': 'track-3',
                    'item_type': 'track',
                    'name': 'Let Her Go',
                    'artist': 'Passenger',
                    'spotify_url': 'https://open.spotify.com/track/track-3',
                    'uri': 'spotify:track:track-3',
                },
            ],
            limit=10,
        )

        self.assertEqual([track['id'] for track in sanitized], ['track-1', 'track-3'])

    def test_filter_tracks_for_query_prefers_exact_seed_matches(self):
        filtered = spotify_service._filter_tracks_for_query(
            'track:"Lose Yourself" artist:"Eminem"',
            [
                {
                    'id': 'track-exact',
                    'name': 'Lose Yourself',
                    'artist': 'Eminem',
                },
                {
                    'id': 'track-near',
                    'name': 'Lose Yourself to Dance',
                    'artist': 'Daft Punk, Pharrell Williams',
                },
                {
                    'id': 'track-cover',
                    'name': 'Lose Yourself',
                    'artist': 'Cover Artist',
                },
            ],
        )

        self.assertEqual([track['id'] for track in filtered], ['track-exact'])

    def test_music_doc_seed_query_is_strict_and_tagged(self):
        query = 'track:"Espresso" artist:"Sabrina Carpenter"'
        filtered = spotify_service._filter_tracks_for_query(
            query,
            [
                {
                    'id': 'track-exact',
                    'name': 'Espresso',
                    'artist': 'Sabrina Carpenter',
                },
                {
                    'id': 'track-loose',
                    'name': 'Espresso Macchiato',
                    'artist': 'Other Artist',
                },
            ],
            strict=bool(spotify_service._seed_metadata_for_query('happy', query)),
        )
        annotated = spotify_service._annotate_tracks_for_query(
            query,
            filtered,
            emotion='happy',
        )

        self.assertEqual([track['id'] for track in annotated], ['track-exact'])
        self.assertEqual(annotated[0]['recommendation_source'], 'music_md_playlist')
        self.assertIn('music_md_playlist_seed', annotated[0]['selection_reasons'])
        self.assertEqual(annotated[0]['playlist_seed_emotion'], 'happy')

    def test_get_recommendations_skips_duplicate_seed_variants_to_keep_diversity(self):
        first_query_tracks = [
            {
                'id': 'track-seed-main',
                'name': 'Someone You Loved',
                'artist': 'Lewis Capaldi',
                'album': 'Divinely Uninspired To A Hellish Extent',
                'spotify_url': 'https://open.spotify.com/track/track-seed-main',
                'uri': 'spotify:track:track-seed-main',
                'popularity': 90,
            },
            {
                'id': 'track-seed-remix',
                'name': 'Someone You Loved - Future Humans Remix',
                'artist': 'Lewis Capaldi, Future Humans',
                'album': 'Someone You Loved',
                'spotify_url': 'https://open.spotify.com/track/track-seed-remix',
                'uri': 'spotify:track:track-seed-remix',
                'popularity': 65,
            },
        ]
        second_query_tracks = [
            {
                'id': 'track-other-1',
                'name': 'Let Her Go',
                'artist': 'Passenger',
                'album': 'All The Little Lights',
                'spotify_url': 'https://open.spotify.com/track/track-other-1',
                'uri': 'spotify:track:track-other-1',
                'popularity': 82,
            },
            {
                'id': 'track-other-2',
                'name': 'All I Want',
                'artist': 'Kodaline',
                'album': 'In A Perfect World',
                'spotify_url': 'https://open.spotify.com/track/track-other-2',
                'uri': 'spotify:track:track-other-2',
                'popularity': 80,
            },
        ]

        with patch.object(
            spotify_service,
            'get_user_music_candidates',
            return_value={
                'ok': False,
                'tracks': [],
                'sources_used': [],
                'missing_scopes': [],
                'errors': [],
                'token_error': None,
            },
        ), patch.object(
            spotify_service,
            '_get_catalog_token_candidates',
            return_value=([('client', 'spotify-token')], []),
        ), patch.object(
            spotify_service,
            '_build_recommendation_queries',
            return_value=['seed-query', 'fallback-query'],
        ), patch.object(
            spotify_service,
            'search_tracks_detailed',
            side_effect=[
                {
                    'ok': True,
                    'items': first_query_tracks,
                    'status_code': 200,
                    'error': None,
                    'response_text': '{}',
                },
                {
                    'ok': True,
                    'items': second_query_tracks,
                    'status_code': 200,
                    'error': None,
                    'response_text': '{}',
                },
            ],
        ):
            result = spotify_service.get_recommendations_with_details(
                'sad',
                user=None,
                preferred_artists=[],
                top_emotions=[{'emotion': 'sad', 'confidence': 1.0}],
                all_scores={'sad': 1.0},
                limit=3,
            )

        self.assertTrue(result['ok'])
        result_ids = [track['id'] for track in result['tracks'][:3]]
        self.assertIn('track-seed-main', result_ids)
        self.assertIn('track-other-1', result_ids)
        self.assertIn('track-other-2', result_ids)
        self.assertNotIn('track-seed-remix', result_ids)

    def test_get_recommendations_prefers_personalized_user_music_before_generic_search(self):
        user = User.objects.create_user(
            username='user-music-user',
            email='user-music@example.com',
            password='password123',
        )
        user.is_spotify_connected = True
        user.spotify_access_token = 'spotify-token'
        user.spotify_refresh_token = 'spotify-refresh'
        user.spotify_granted_scopes = [
            'user-top-read',
            'user-library-read',
        ]
        user.spotify_token_expires = timezone.now() + timedelta(hours=1)
        user.save()

        top_tracks_payload = {
            'ok': True,
            'status_code': 200,
            'data': {
                'items': [{
                    'id': 'track-top-1',
                    'name': 'Love Anthem',
                    'artists': [{'name': 'Taylor'}],
                    'album': {'name': 'Album', 'images': []},
                    'external_urls': {'spotify': 'https://open.spotify.com/track/track-top-1'},
                    'uri': 'spotify:track:track-top-1',
                    'duration_ms': 180000,
                    'popularity': 85,
                }],
            },
            'response_text': '{"items":[...]}',
        }
        saved_tracks_payload = {
            'ok': True,
            'status_code': 200,
            'data': {
                'items': [{
                    'added_at': '2026-03-18T12:00:00Z',
                    'track': {
                        'id': 'track-saved-1',
                        'name': 'Soft Lights',
                        'artists': [{'name': 'Indie Artist'}],
                        'album': {'name': 'Album', 'images': []},
                        'external_urls': {'spotify': 'https://open.spotify.com/track/track-saved-1'},
                        'uri': 'spotify:track:track-saved-1',
                        'duration_ms': 175000,
                        'popularity': 60,
                    },
                }],
            },
            'response_text': '{"items":[...]}',
        }

        def fake_spotify_get(token, path, params=None, timeout_seconds=None):
            if path == '/me/top/tracks':
                return top_tracks_payload
            if path == '/me/tracks':
                return saved_tracks_payload
            self.fail(f'unexpected endpoint requested: {path}')

        with patch.object(
            spotify_service,
            'ensure_valid_token_with_details',
            return_value={
                'access_token': 'spotify-token',
                'refresh_attempted': False,
                'refresh_succeeded': False,
                'refresh_error': None,
                'granted_scopes': ['user-top-read', 'user-library-read'],
            },
        ):
            with patch.object(spotify_service, '_spotify_get', side_effect=fake_spotify_get):
                with patch.object(
                    spotify_service,
                    '_get_catalog_token_candidates',
                    return_value=([('client', 'token')], []),
                ):
                    with patch.object(
                        spotify_service,
                        'search_tracks_detailed',
                        return_value={
                            'ok': True,
                            'items': [],
                            'status_code': 200,
                            'error': None,
                            'response_text': '',
                        },
                    ):
                        result = spotify_service.get_recommendations_with_details(
                            'romantic',
                            user=user,
                            preferred_artists=['Taylor'],
                            limit=2,
                        )

        self.assertTrue(result['ok'])
        self.assertTrue(result['personalized'])
        self.assertEqual(result['source'], 'user_music')
        self.assertEqual(result['personalization_sources'], ['top_tracks', 'saved_tracks'])
        self.assertEqual(result['tracks'][0]['id'], 'track-top-1')
        self.assertIn('preferred_artist_match', result['tracks'][0]['selection_reasons'])
        self.assertEqual(result['tracks'][0]['recommendation_source'], 'spotify_top_tracks')

    def test_get_recommendations_tries_broader_queries_when_initial_searches_are_empty(self):
        returned_track = {
            'id': 'track-1',
            'name': 'Happy Song',
            'artist': 'Artist',
            'album': 'Album',
            'image': '',
            'preview_url': None,
            'duration_ms': 180000,
            'spotify_url': 'https://open.spotify.com/track/track-1',
            'uri': 'spotify:track:track-1',
        }

        def fake_search(
            query,
            token,
            limit=10,
            timeout_seconds=None,
        ):
            if query == 'happy':
                return {
                    'ok': True,
                    'items': [returned_track],
                    'status_code': 200,
                    'error': None,
                    'response_text': '',
                }
            return {
                'ok': True,
                'items': [],
                'status_code': 200,
                'error': None,
                'response_text': '',
            }

        with patch.object(
            spotify_service,
            '_get_catalog_token_candidates',
            return_value=([('client', 'token')], []),
        ):
            with patch.object(
                spotify_service,
                'search_tracks_detailed',
                side_effect=fake_search,
            ) as mock_search:
                tracks = spotify_service.get_recommendations('happy', limit=5)

        self.assertEqual(len(tracks), 1)
        self.assertEqual(tracks[0]['id'], returned_track['id'])
        self.assertEqual(tracks[0]['uri'], returned_track['uri'])
        searched_queries = [call.args[0] for call in mock_search.call_args_list]
        self.assertIn('happy', searched_queries)
        self.assertGreater(len(searched_queries), 1)

    def test_get_recommendations_falls_back_to_user_token_after_client_token_403(self):
        user = User.objects.create_user(
            username='spotify-pref-user',
            email='pref@example.com',
            password='password123',
        )
        user.is_spotify_connected = True

        returned_track = {
            'id': 'track-2',
            'name': 'Calm Song',
            'artist': 'Artist',
            'album': 'Album',
            'image': '',
            'preview_url': None,
            'duration_ms': 180000,
            'spotify_url': 'https://open.spotify.com/track/track-2',
            'uri': 'spotify:track:track-2',
        }

        def fake_search(query, token, limit=10, timeout_seconds=None):
            if token == 'client-token':
                return {
                    'ok': False,
                    'items': [],
                    'status_code': 403,
                    'error': 'user may not be registered',
                    'response_text': 'user may not be registered',
                }
            return {
                'ok': True,
                'items': [returned_track],
                'status_code': 200,
                'error': None,
                'response_text': '',
            }

        with patch.object(
            spotify_service,
            '_get_catalog_token_candidates',
            return_value=([('client', 'client-token'), ('user', 'user-token')], []),
        ):
            with patch.object(
                spotify_service,
                'search_tracks_detailed',
                side_effect=fake_search,
            ) as mock_search:
                tracks = spotify_service.get_recommendations('calm', user=user, limit=1)

        self.assertEqual(len(tracks), 1)
        self.assertEqual(tracks[0]['id'], returned_track['id'])
        self.assertEqual(tracks[0]['uri'], returned_track['uri'])
        self.assertEqual(mock_search.call_args_list[0].args[1], 'client-token')
        self.assertEqual(mock_search.call_args_list[1].args[1], 'user-token')

    def test_get_recommendations_stops_when_time_budget_is_exhausted(self):
        with patch.object(
            spotify_service,
            '_get_catalog_token_candidates',
            return_value=([('client', 'token')], []),
        ):
            with patch.object(
                spotify_service,
                '_build_recommendation_queries',
                return_value=['first', 'second', 'third'],
            ):
                with patch.object(
                    spotify_service,
                    'search_tracks_detailed',
                    return_value={
                        'ok': True,
                        'items': [],
                        'status_code': 200,
                        'error': None,
                        'response_text': '',
                    },
                ) as mock_search:
                    with patch('api.spotify_service.time.monotonic') as mock_monotonic:
                        mock_monotonic.side_effect = [100.0, 100.05, 100.60]
                        with patch.object(
                            spotify_service,
                            'recommendation_budget_seconds',
                            0.2,
                        ):
                            tracks = spotify_service.get_recommendations('happy', limit=5)

        self.assertTrue(tracks)
        self.assertTrue(all(track['uri'] for track in tracks))
        self.assertTrue(all(track['spotify_url'].startswith('https://open.spotify.com/') for track in tracks))
        mock_search.assert_called_once()

    # A fresh service under pinned credentials, like its neighbours: the
    # shared spotify_service read its client ID from the local .env at import,
    # so on a fresh checkout it had none and never asked for a token.
    @override_settings(
        SPOTIFY_CLIENT_ID='client-id',
        SPOTIFY_CLIENT_SECRET='client-secret',
    )
    def test_get_client_token_reuses_cached_token_until_expiry(self):
        response = Mock()
        response.ok = True
        response.status_code = 200
        response.json.return_value = {
            'access_token': 'cached-token',
            'expires_in': 3600,
        }
        service = SpotifyService()

        with patch('api.http_client.post', return_value=response) as mock_post:
            first_token = service.get_client_token()
            second_token = service.get_client_token()

        self.assertEqual(first_token, 'cached-token')
        self.assertEqual(second_token, 'cached-token')
        mock_post.assert_called_once()

    @override_settings(
        SPOTIFY_CLIENT_ID='client-id',
        SPOTIFY_CLIENT_SECRET='client-secret',
    )
    def test_client_token_network_error_returns_structured_failure(self):
        service = SpotifyService()

        with self.assertLogs('api.spotify_service', level='WARNING') as logs:
            with patch(
                'api.http_client.post',
                side_effect=requests.ConnectionError('dns lookup failed'),
            ):
                result = service.get_client_token_details()

        self.assertFalse(result['ok'])
        self.assertEqual(result['reason'], 'network_error')
        self.assertTrue(result['retryable'])
        self.assertEqual(result['source'], 'client_credentials')
        self.assertEqual(result['endpoint'], '/api/token')
        self.assertIn('Spotify could not be reached', result['recommended_action'])
        self.assertTrue(all(line.startswith('WARNING:') for line in logs.output))

    def test_ensure_valid_token_does_not_overwrite_user_when_refresh_fails(self):
        user = User.objects.create_user(
            username='refresh-user',
            email='refresh@example.com',
            password='password123',
        )
        user.is_spotify_connected = True
        user.spotify_access_token = 'existing-token'
        user.spotify_refresh_token = 'refresh-token'
        user.spotify_token_expires = timezone.now() - timedelta(minutes=5)
        user.save()

        with patch.object(spotify_service, 'refresh_token', return_value={}):
            refreshed = spotify_service.ensure_valid_token(user)

        self.assertIsNone(refreshed)
        user.refresh_from_db()
        self.assertEqual(user.spotify_access_token, 'existing-token')
        self.assertEqual(user.spotify_refresh_token, 'refresh-token')
        self.assertLessEqual(user.spotify_token_expires, timezone.now())

    @override_settings(
        SPOTIFY_CLIENT_ID='client-id',
        SPOTIFY_CLIENT_SECRET='client-secret',
    )
    def test_ensure_valid_token_preserves_network_refresh_failure_reason(self):
        service = SpotifyService()
        user = User.objects.create_user(
            username='refresh-network-user',
            email='refresh-network@example.com',
            password='password123',
        )
        user.is_spotify_connected = True
        user.spotify_access_token = 'expired-token'
        user.spotify_refresh_token = 'refresh-token'
        user.spotify_token_expires = timezone.now() - timedelta(minutes=5)
        user.save()

        with patch(
            'api.http_client.post',
            side_effect=requests.ConnectionError('dns lookup failed'),
        ):
            details = service.ensure_valid_token_with_details(user)

        self.assertIsNone(details['access_token'])
        self.assertTrue(details['refresh_attempted'])
        self.assertFalse(details['refresh_succeeded'])
        self.assertEqual(details['refresh_error'], 'network_error')
        self.assertEqual(details['refresh_failure']['reason'], 'network_error')
        self.assertIn(
            'Spotify could not be reached',
            details['refresh_failure']['recommended_action'],
        )

        user.refresh_from_db()
        self.assertEqual(user.spotify_access_token, 'expired-token')

    def test_get_recommendations_returns_playable_fallback_tracks_when_spotify_rejects_all_tokens(self):
        with patch.object(
            spotify_service,
            '_get_catalog_token_candidates',
            return_value=([('client', 'client-token'), ('user', 'user-token')], []),
        ):
            with patch.object(
                spotify_service,
                'search_tracks_detailed',
                return_value={
                    'ok': False,
                    'items': [],
                    'status_code': 403,
                    'error': 'user may not be registered',
                    'response_text': 'user may not be registered',
                },
            ):
                tracks = spotify_service.get_recommendations('angry', limit=3)

        self.assertEqual(len(tracks), 3)
        self.assertTrue(all(track['uri'] for track in tracks))
        self.assertTrue(all(track['spotify_url'].startswith('https://open.spotify.com/') for track in tracks))
        self.assertTrue(all(track['recommendation_source'] == 'curated_fallback' for track in tracks))

    def test_curated_fallback_only_uses_the_emotions_own_playlists(self):
        """QA 2026-10-06: a happy listener got "Sad Songs" whenever search fell
        back, because every emotion was padded with the 'mixed' list."""
        from api.spotify.constants import CURATED_CONTEXT_LIBRARY, CURATED_PLAYABLE_CONTEXTS

        sad_songs = CURATED_CONTEXT_LIBRARY['sad_songs']['name']
        for emotion, context_keys in CURATED_PLAYABLE_CONTEXTS.items():
            with self.subTest(emotion=emotion):
                allowed = {CURATED_CONTEXT_LIBRARY[key]['name'] for key in context_keys}
                names = {
                    track['name']
                    for track in spotify_service._build_curated_fallback_tracks(emotion, limit=20)
                }

                self.assertTrue(names)
                self.assertLessEqual(names, allowed)
                if 'sad_songs' not in context_keys:
                    self.assertNotIn(sad_songs, names)

    def test_history_replay_skips_curated_playlists_stored_by_old_fallbacks(self):
        """QA 2026-10-06: happy users kept getting the old padded list (with
        "Sad Songs") because a past fallback had saved it to their history."""
        from api.spotify.constants import CURATED_CONTEXT_LIBRARY
        from users.models import PromptHistory

        user = User.objects.create_user(username='replay', email='replay@example.com', password='pw12345!')
        learned = {
            'id': 'learned-1', 'item_type': 'track', 'name': 'Espresso', 'artist': 'Sabrina Carpenter',
            'uri': 'spotify:track:learned-1', 'spotify_url': 'https://open.spotify.com/track/learned-1',
            'recommendation_source': 'spotify_catalog',
        }
        stale_curated = {**CURATED_CONTEXT_LIBRARY['sad_songs'], 'recommendation_source': 'curated_fallback'}
        PromptHistory.objects.create(
            user=user, prompt_text='so happy', detected_emotion='happy', ai_response='',
            playlist_data=[learned, stale_curated],
        )

        tracks = spotify_service._build_fallback_tracks('happy', user=user, limit=20)
        names = [track['name'] for track in tracks]

        self.assertIn('Espresso', names)
        self.assertNotIn(CURATED_CONTEXT_LIBRARY['sad_songs']['name'], names)

    def test_get_recommendations_uses_user_preferences_as_playable_fallback_when_no_tokens(self):
        user = User.objects.create_user(
            username='history-user',
            email='history@example.com',
            password='password123',
        )
        UserPreference.objects.create(
            user=user,
            emotion='calm',
            spotify_track_id='track-9',
            track_name='Quiet Track',
            artist_name='Artist',
            play_count=5,
        )

        with patch.object(
            spotify_service,
            '_get_catalog_token_candidates',
            return_value=([], []),
        ):
            tracks = spotify_service.get_recommendations('calm', user=user, limit=3)

        self.assertTrue(tracks)
        self.assertEqual(tracks[0]['id'], 'track-9')
        self.assertEqual(tracks[0]['uri'], 'spotify:track:track-9')
        self.assertEqual(
            tracks[0]['spotify_url'],
            'https://open.spotify.com/track/track-9',
        )
        self.assertEqual(tracks[0]['recommendation_source'], 'user_preference')

    def test_get_recommendations_with_details_marks_fallback_source(self):
        with patch.object(
            spotify_service,
            '_get_catalog_token_candidates',
            return_value=([], [{'reason': 'network_error'}]),
        ):
            result = spotify_service.get_recommendations_with_details('happy', limit=2)

        self.assertTrue(result['used_fallback'])
        self.assertEqual(result['source'], 'fallback')
        self.assertEqual(result['fallback_reason'], 'network_error')

    def test_debug_status_marks_allowlist_issue_without_claiming_non_premium(self):
        user = User.objects.create_user(
            username='allowlist-user',
            email='allowlist@example.com',
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
        user.save()

        failure_payload = {
            'ok': False,
            'status_code': 403,
            'error': 'Check settings on https://developer.spotify.com/dashboard, the user may not be registered.',
            'error_code': '403',
            'reason': 'developer_allowlist_required',
            'response_text': 'Check settings on https://developer.spotify.com/dashboard, the user may not be registered.',
            'response_json': {'error': {'status': 403, 'message': 'user may not be registered'}},
            'recommended_action': 'Add the account to the allowlist.',
        }

        with patch.object(
            spotify_service,
            'get_user_profile_result',
            return_value=failure_payload,
        ):
            with patch.object(spotify_service, '_spotify_get', return_value=failure_payload):
                diagnostics = spotify_service.get_playback_debug_status(user)

        self.assertTrue(diagnostics['account']['developer_allowlist_required'])
        self.assertIsNone(diagnostics['account']['has_premium'])
        self.assertEqual(diagnostics['account']['error_reason'], 'developer_allowlist_required')
        self.assertIn('Development Mode', diagnostics['recommended_action'])

    def test_debug_status_uses_refresh_failure_action_when_refresh_hits_network(self):
        user = User.objects.create_user(
            username='debug-refresh-network-user',
            email='debug-refresh-network@example.com',
            password='password123',
        )
        user.is_spotify_connected = True
        user.spotify_access_token = 'expired-token'
        user.spotify_refresh_token = 'refresh-token'
        user.spotify_token_expires = timezone.now() - timedelta(minutes=5)
        user.spotify_granted_scopes = [
            'streaming',
            'user-modify-playback-state',
            'user-read-playback-state',
            'user-read-currently-playing',
            'app-remote-control',
        ]
        user.save()

        refresh_failure = {
            'source': 'refresh_token',
            'status_code': None,
            'reason': 'network_error',
            'error': 'dns lookup failed',
            'error_code': None,
            'recommended_action': (
                'Spotify could not be reached from the backend. Check internet access, '
                'firewall settings, and Spotify API availability.'
            ),
        }

        with patch.object(
            spotify_service,
            'ensure_valid_token_with_details',
            return_value={
                'access_token': None,
                'refresh_attempted': True,
                'refresh_succeeded': False,
                'refresh_error': 'network_error',
                'refresh_failure': refresh_failure,
                'granted_scopes': user.spotify_granted_scopes,
            },
        ):
            diagnostics = spotify_service.get_playback_debug_status(user)

        self.assertFalse(diagnostics['token']['is_valid'])
        self.assertEqual(diagnostics['token']['refresh_error'], 'network_error')
        self.assertEqual(diagnostics['token']['refresh_failure'], refresh_failure)
        self.assertEqual(
            diagnostics['recommended_action'],
            refresh_failure['recommended_action'],
        )

    def test_prepare_playback_returns_allowlist_block_when_devices_endpoint_is_rejected(self):
        user = User.objects.create_user(
            username='devices-allowlist-user',
            email='devices-allowlist@example.com',
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
        user.save()

        profile_payload = {
            'ok': True,
            'status_code': 200,
            'data': {
                'id': 'spotify-user-id',
                'product': 'premium',
                'email': 'devices-allowlist@example.com',
            },
            'response_text': '{"id":"spotify-user-id","product":"premium"}',
        }
        allowlist_failure = {
            'ok': False,
            'status_code': 403,
            'error': (
                'The user is not registered for this application. '
                'Please check your settings on developer dashboard.'
            ),
            'error_code': 'None',
            'reason': 'developer_allowlist_required',
            'response_text': (
                'The user is not registered for this application. '
                'Please check your settings on developer dashboard.'
            ),
            'response_json': {
                'error': {
                    'status': 403,
                    'message': (
                        'The user is not registered for this application. '
                        'Please check your settings on developer dashboard.'
                    ),
                },
            },
            'recommended_action': (
                'Spotify blocked this account because the app is still in Development Mode. '
                'Add this exact Spotify account to the Spotify Developer Dashboard user '
                'allowlist, then reconnect Spotify in EmoTune.'
            ),
        }

        with patch.object(
            spotify_service,
            'get_user_profile_result',
            return_value=profile_payload,
        ):
            with patch.object(
                spotify_service,
                '_spotify_get',
                side_effect=[allowlist_failure, allowlist_failure],
            ):
                result = spotify_service.prepare_playback(user)

        self.assertFalse(result['ok'])
        self.assertEqual(result['blocking_issue'], 'developer_allowlist_required')
        self.assertIn('Development Mode', result['recommended_action'])

    def test_get_playback_debug_status_includes_current_track_metadata(self):
        user = User.objects.create_user(
            username='debug-metadata-user',
            email='debug-metadata@example.com',
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

        token_details = {
            'access_token': 'spotify-token',
            'refresh_attempted': False,
            'refresh_succeeded': False,
            'refresh_error': None,
            'granted_scopes': user.spotify_granted_scopes,
        }
        profile_payload = {
            'ok': True,
            'status_code': 200,
            'data': {
                'id': 'spotify-user-id',
                'product': 'premium',
                'email': 'debug-metadata@example.com',
            },
            'response_text': '{"id":"spotify-user-id","product":"premium"}',
        }
        current_playback_payload = {
            'ok': True,
            'status_code': 200,
            'data': {
                'is_playing': True,
                'progress_ms': 42000,
                'device': {
                    'id': 'device-1',
                    'name': '2409BRN2CA',
                },
                'context': {
                    'type': 'playlist',
                    'uri': 'spotify:playlist:playlist-1',
                },
                'item': {
                    'id': 'track-1',
                    'uri': 'spotify:track:track-1',
                    'type': 'track',
                    'name': 'Happy Track',
                    'duration_ms': 215000,
                    'artists': [
                        {'name': 'Artist One'},
                        {'name': 'Artist Two'},
                    ],
                    'album': {
                        'name': 'Album One',
                        'images': [{'url': 'https://image.test/cover.jpg'}],
                    },
                },
            },
            'response_text': '{"is_playing":true}',
        }
        devices_payload = {
            'ok': True,
            'status_code': 200,
            'data': {
                'devices': [{
                    'id': 'device-1',
                    'name': '2409BRN2CA',
                    'type': 'Smartphone',
                    'is_active': True,
                    'is_restricted': False,
                }],
            },
            'response_text': '{"devices":[{"id":"device-1"}]}',
        }

        with patch.object(
            spotify_service,
            'ensure_valid_token_with_details',
            return_value=token_details,
        ):
            with patch.object(
                spotify_service,
                'get_user_profile_result',
                return_value=profile_payload,
            ):
                with patch.object(
                    spotify_service,
                    '_spotify_get',
                    side_effect=[current_playback_payload, devices_payload],
                ):
                    diagnostics = spotify_service.get_playback_debug_status(user)

        current = diagnostics['currently_playing']
        self.assertTrue(current['ok'])
        self.assertEqual(current['progress_ms'], 42000)
        self.assertEqual(current['item_id'], 'track-1')
        self.assertEqual(current['item_name'], 'Happy Track')
        self.assertEqual(current['item_type'], 'track')
        self.assertEqual(current['artist_names'], ['Artist One', 'Artist Two'])
        self.assertEqual(current['artist_name'], 'Artist One, Artist Two')
        self.assertEqual(current['album_name'], 'Album One')
        self.assertEqual(current['duration_ms'], 215000)
        self.assertEqual(current['image_url'], 'https://image.test/cover.jpg')
        self.assertEqual(current['context_type'], 'playlist')
        self.assertEqual(current['context_uri'], 'spotify:playlist:playlist-1')

    def test_prepare_playback_treats_visible_transfer_target_as_activation_pending(self):
        user = User.objects.create_user(
            username='activation-pending-user',
            email='activation-pending@example.com',
            password='password123',
        )

        initial_diagnostics = {
            'spotify_connected': True,
            'token': {'is_valid': True},
            'oauth': {'missing_required_scopes': []},
            'account': {'has_premium': True},
            'devices': {
                'has_active_device': False,
                'devices': [{
                    'id': 'device-1',
                    'name': '2409BRN2CA',
                    'type': 'Smartphone',
                    'is_active': False,
                    'is_restricted': False,
                }],
            },
            'recommended_action': 'Spotify connected, but no active device is selected yet.',
        }
        updated_diagnostics = {
            'spotify_connected': True,
            'token': {'is_valid': True},
            'oauth': {'missing_required_scopes': []},
            'account': {'has_premium': True},
            'devices': {
                'has_active_device': False,
                'devices': [{
                    'id': 'device-1',
                    'name': '2409BRN2CA',
                    'type': 'Smartphone',
                    'is_active': False,
                    'is_restricted': False,
                }],
            },
            'recommended_action': 'Spotify connected, but the device is still becoming active.',
        }

        with patch.object(
            spotify_service,
            'get_playback_debug_status',
            side_effect=[initial_diagnostics, updated_diagnostics],
        ):
            with patch.object(spotify_service, 'ensure_valid_token', return_value='spotify-token'):
                with patch.object(
                    spotify_service,
                    '_spotify_put',
                    return_value={'ok': True, 'status_code': 204},
                ):
                    result = spotify_service.prepare_playback(user)

        self.assertTrue(result['ok'])
        self.assertTrue(result['transfer_attempted'])
        self.assertTrue(result['transfer_succeeded'])
        self.assertTrue(result['device_activation_pending'])
        self.assertIsNone(result['blocking_issue'])
        self.assertIn('retry playback on this device now', result['recommended_action'])

    def test_prepare_playback_reports_background_device_unavailable_without_reconnect_hint(self):
        user = User.objects.create_user(
            username='no-device-user',
            email='no-device@example.com',
            password='password123',
        )

        diagnostics = {
            'spotify_connected': True,
            'token': {'is_valid': True},
            'oauth': {'missing_required_scopes': []},
            'account': {'has_premium': True},
            'devices': {
                'has_active_device': False,
                'devices': [],
            },
            'recommended_action': 'legacy device guidance',
        }

        with patch.object(
            spotify_service,
            'get_playback_debug_status',
            return_value=diagnostics,
        ):
            result = spotify_service.prepare_playback(user)

        self.assertFalse(result['ok'])
        self.assertEqual(result['blocking_issue'], 'no_device')
        self.assertIn('has not exposed a playable device', result['recommended_action'])
        self.assertNotIn('reconnect', result['recommended_action'].lower())

    def test_execute_playback_command_plays_track_after_prepare(self):
        user = User.objects.create_user(
            username='play-command-user',
            email='play-command@example.com',
            password='password123',
        )

        preparation = {
            'ok': True,
            'blocking_issue': None,
            'selected_device_id': 'device-1',
            'selected_device_name': '2409BRN2CA',
            'device_activation_pending': False,
            'diagnostics': {
                'devices': {
                    'active_device_id': 'device-1',
                    'active_device_name': '2409BRN2CA',
                },
            },
        }
        playback_payload = {
            'is_playing': True,
            'item': {'uri': 'spotify:track:track-1'},
        }

        with patch.object(
            spotify_service,
            'get_playback_debug_status',
            return_value={
                'spotify_connected': True,
                'token': {'is_valid': True},
                'oauth': {'missing_required_scopes': []},
                'account': {'has_premium': True},
                'devices': {'has_active_device': True},
                'recommended_action': 'Ready to play.',
            },
        ):
            with patch.object(spotify_service, 'ensure_valid_token', return_value='spotify-token'):
                with patch.object(
                    spotify_service,
                    'prepare_playback',
                    return_value=preparation,
                ):
                    with patch.object(
                        spotify_service,
                        '_spotify_request',
                        return_value={'ok': True, 'status_code': 204},
                    ) as mock_spotify_request:
                        with patch.object(
                            spotify_service,
                            '_spotify_get',
                            return_value={'ok': True, 'data': playback_payload},
                        ):
                            result = spotify_service.execute_playback_command(
                                user,
                                action='play',
                                uri='spotify:track:track-1',
                            )

        self.assertTrue(result['ok'])
        self.assertEqual(result['action'], 'play')
        self.assertEqual(result['selected_device_name'], '2409BRN2CA')
        self.assertEqual(result['playback'], playback_payload)
        mock_spotify_request.assert_called_once_with(
            'PUT',
            'spotify-token',
            '/me/player/play',
            params={'device_id': 'device-1'},
            json_body={'uris': ['spotify:track:track-1']},
        )

    def test_execute_playback_command_seeks_with_position_param(self):
        user = User.objects.create_user(
            username='seek-command-user',
            email='seek-command@example.com',
            password='password123',
        )

        preparation = {
            'ok': True,
            'blocking_issue': None,
            'selected_device_id': 'device-1',
            'selected_device_name': '2409BRN2CA',
            'device_activation_pending': False,
            'diagnostics': {
                'devices': {
                    'active_device_id': 'device-1',
                    'active_device_name': '2409BRN2CA',
                },
            },
        }

        with patch.object(
            spotify_service,
            'get_playback_debug_status',
            return_value={
                'spotify_connected': True,
                'token': {'is_valid': True},
                'oauth': {'missing_required_scopes': []},
                'account': {'has_premium': True},
                'devices': {'has_active_device': True},
                'recommended_action': 'Ready to play.',
            },
        ):
            with patch.object(spotify_service, 'ensure_valid_token', return_value='spotify-token'):
                with patch.object(
                    spotify_service,
                    'prepare_playback',
                    return_value=preparation,
                ):
                    with patch.object(
                        spotify_service,
                        '_spotify_request',
                        return_value={'ok': True, 'status_code': 204},
                    ) as mock_spotify_request:
                        with patch.object(
                            spotify_service,
                            '_spotify_get',
                            return_value={'ok': True, 'data': {'is_playing': True}},
                        ):
                            result = spotify_service.execute_playback_command(
                                user,
                                action='seek',
                                position_ms=45000,
                            )

        self.assertTrue(result['ok'])
        self.assertEqual(result['position_ms'], 45000)
        mock_spotify_request.assert_called_once_with(
            'PUT',
            'spotify-token',
            '/me/player/seek',
            params={'device_id': 'device-1', 'position_ms': 45000},
        )

    def test_execute_playback_command_rejects_invalid_repeat_mode(self):
        user = User.objects.create_user(
            username='repeat-command-user',
            email='repeat-command@example.com',
            password='password123',
        )

        with patch.object(
            spotify_service,
            'get_playback_debug_status',
            return_value={
                'spotify_connected': True,
                'token': {'is_valid': True},
                'oauth': {'missing_required_scopes': []},
                'account': {'has_premium': True},
                'devices': {'has_active_device': True},
                'recommended_action': 'Ready to play.',
            },
        ):
            with patch.object(spotify_service, 'ensure_valid_token', return_value='spotify-token'):
                result = spotify_service.execute_playback_command(
                    user,
                    action='repeat',
                    repeat_mode='loop-everything',
                )

        self.assertFalse(result['ok'])
        self.assertEqual(result['blocking_issue'], 'invalid_repeat_mode')

    def test_classify_upstream_failure_detects_not_registered_for_application_message(self):
        classification = spotify_service._classify_upstream_failure(
            403,
            error_message='The user is not registered for this application.',
            response_text='Please check your settings on developer dashboard.',
            endpoint='/me',
        )

        self.assertEqual(classification['reason'], 'developer_allowlist_required')
        self.assertIn('Development Mode', classification['recommended_action'])


class EmotionClassifierTests(TestCase):
    @patch.object(EmotionClassifier, '_load_model', return_value=None)
    @patch.object(EmotionClassifier, '_load_goemotions_model', return_value=None)
    def test_keyword_classifier_returns_deterministic_signal_for_clear_text(
        self,
        _mock_load_goemotions_model,
        _mock_load_model,
    ):
        classifier = EmotionClassifier()
        classifier.model_loaded = False

        result = classifier.predict('I feel calm and peaceful after meditating.')

        self.assertEqual(result['emotion'], 'calm')
        self.assertEqual(result['prediction_source'], 'keyword')
        self.assertEqual(result['prediction_strategy'], 'keyword_only')
        self.assertIn('top_emotions', result)
        self.assertIn('plutchik_scores', result)
        self.assertEqual(result['plutchik_dominant_emotion'], 'trust')
        self.assertGreater(result['confidence'], 0)

    @patch.object(EmotionClassifier, '_load_model', return_value=None)
    @patch.object(EmotionClassifier, '_load_goemotions_model', return_value=None)
    def test_keyword_classifier_marks_uncertain_text_for_review(
        self,
        _mock_load_goemotions_model,
        _mock_load_model,
    ):
        classifier = EmotionClassifier()
        classifier.model_loaded = False

        result = classifier.predict('table chair window')

        self.assertEqual(result['emotion'], 'mixed')
        self.assertTrue(result['fallback_used'])
        self.assertTrue(result['needs_review'])
        self.assertEqual(result['confidence_band'], 'low')

    @patch.object(EmotionClassifier, '_load_model', return_value=None)
    @patch.object(EmotionClassifier, '_load_goemotions_model', return_value=None)
    def test_keyword_classifier_treats_heart_broken_phrase_as_sad(
        self,
        _mock_load_goemotions_model,
        _mock_load_model,
    ):
        classifier = EmotionClassifier()
        classifier.model_loaded = False

        result = classifier.predict('I feel heart broken and I miss them.')

        self.assertEqual(result['emotion'], 'sad')
        self.assertEqual(result['prediction_source'], 'keyword')
        self.assertEqual(result['top_emotions'][0]['emotion'], 'sad')
        self.assertGreater(
            result['top_emotions'][0]['confidence'],
            result['top_emotions'][1]['confidence'],
        )

    @patch.object(EmotionClassifier, '_load_model', return_value=None)
    @patch.object(EmotionClassifier, '_load_goemotions_model', return_value=None)
    def test_keyword_classifier_treats_broke_my_heart_phrase_as_sad(
        self,
        _mock_load_goemotions_model,
        _mock_load_model,
    ):
        classifier = EmotionClassifier()
        classifier.model_loaded = False

        result = classifier.predict("They broke my heart and I can't stop crying.")

        self.assertEqual(result['emotion'], 'sad')
        self.assertEqual(result['prediction_source'], 'keyword')
        self.assertEqual(result['top_emotions'][0]['emotion'], 'sad')

    @patch.object(EmotionClassifier, '_load_model', return_value=None)
    @patch.object(EmotionClassifier, '_load_goemotions_model', return_value=None)
    def test_goemotions_fallback_prefers_sad_for_downward_life_prompt(
        self,
        _mock_load_goemotions_model,
        _mock_load_model,
    ):
        classifier = EmotionClassifier()
        classifier.model_loaded = False
        classifier.goemotions_model_loaded = True
        classifier.goemotions_confidence_threshold = 0.3
        classifier.goemotions_margin_threshold = 0.05

        classifier._goemotions_predict = Mock(return_value={
            'emotion': 'sad',
            'confidence': 0.56,
            'all_scores': {'sad': 0.56, 'mixed': 0.12},
            'top_emotions': [
                {'emotion': 'sad', 'confidence': 0.56},
                {'emotion': 'mixed', 'confidence': 0.12},
            ],
            'secondary_emotion': 'mixed',
            'prediction_source': 'goemotions',
            'prediction_strategy': 'goemotions_only',
            'confidence_band': 'medium',
            'confidence_margin': 0.44,
            'fallback_used': False,
            'fallback_reason': None,
            'needs_review': True,
            'label_schema_version': 'v1',
        })

        result = classifier.predict('i feel my life is going down')

        self.assertEqual(result['emotion'], 'sad')
        self.assertEqual(result['prediction_source'], 'goemotions')
        self.assertEqual(result['prediction_strategy'], 'goemotions_only')

    @patch.object(EmotionClassifier, '_load_model', return_value=None)
    @patch.object(EmotionClassifier, '_load_goemotions_model', return_value=None)
    def test_resolve_model_source_uses_existing_local_model_directory(
        self,
        _mock_load_goemotions_model,
        _mock_load_model,
    ):
        # A relative ML_MODEL_PATH resolves against BASE_DIR. The real model is
        # gitignored, so a stand-in directory keeps this passing on a fresh
        # checkout instead of only on machines that have trained one.
        with tempfile.TemporaryDirectory() as base_dir:
            model_dir = Path(base_dir) / 'ml' / 'models' / 'bert_emotion_model'
            model_dir.mkdir(parents=True)
            with override_settings(BASE_DIR=Path(base_dir), ML_MODEL_PATH='ml/models/bert_emotion_model'):
                classifier = EmotionClassifier()
                model_source, is_local = classifier._resolve_model_source(settings.ML_MODEL_PATH)
            # Compared as a Path, not a string suffix: the resolver joins with
            # the OS separator, so a hardcoded one only ever passes on the
            # machine it was written on.
            expected = model_dir.resolve()

        self.assertTrue(is_local)
        self.assertEqual(Path(model_source), expected)

    @patch.object(EmotionClassifier, '_load_model', return_value=None)
    @patch.object(EmotionClassifier, '_load_goemotions_model', return_value=None)
    @override_settings(ML_MODEL_PATH='j-hartmann/emotion-english-distilroberta-base')
    def test_resolve_model_source_accepts_hugging_face_model_id(
        self,
        _mock_load_goemotions_model,
        _mock_load_model,
    ):
        classifier = EmotionClassifier()

        model_source, is_local = classifier._resolve_model_source(settings.ML_MODEL_PATH)

        self.assertFalse(is_local)
        self.assertEqual(model_source, 'j-hartmann/emotion-english-distilroberta-base')

    @patch.object(EmotionClassifier, '_load_model', return_value=None)
    @patch.object(EmotionClassifier, '_load_goemotions_model', return_value=None)
    def test_resolve_model_label_map_accepts_matching_emotune_labels(
        self,
        _mock_load_goemotions_model,
        _mock_load_model,
    ):
        classifier = EmotionClassifier()
        fake_model = Mock()
        fake_model.config = Mock()
        fake_model.config.id2label = {
            index: emotion.upper()
            for index, emotion in enumerate([
                'happy',
                'sad',
                'angry',
                'motivational',
                'fear',
                'depressing',
                'surprising',
                'stressed',
                'calm',
                'lonely',
                'romantic',
                'nostalgic',
                'mixed',
            ])
        }
        fake_model.config.num_labels = 13

        label_map = classifier._resolve_model_label_map(fake_model)

        self.assertEqual(
            label_map,
            [
                'happy',
                'sad',
                'angry',
                'motivational',
                'fear',
                'depressing',
                'surprising',
                'stressed',
                'calm',
                'lonely',
                'romantic',
                'nostalgic',
                'mixed',
            ],
        )

    @patch.object(EmotionClassifier, '_load_model', return_value=None)
    @patch.object(EmotionClassifier, '_load_goemotions_model', return_value=None)
    def test_resolve_model_label_map_rejects_mismatched_public_emotion_schema(
        self,
        _mock_load_goemotions_model,
        _mock_load_model,
    ):
        classifier = EmotionClassifier()
        fake_model = Mock()
        fake_model.config = Mock()
        fake_model.config.id2label = {
            0: 'anger',
            1: 'joy',
            2: 'love',
            3: 'sadness',
            4: 'surprise',
            5: 'fear',
        }
        fake_model.config.num_labels = 6

        label_map = classifier._resolve_model_label_map(fake_model)

        self.assertIsNone(label_map)

    def test_build_plutchik_profile_maps_emotune_scores_to_visualization_profile(self):
        profile = build_plutchik_profile({
            'romantic': 0.6,
            'happy': 0.2,
            'sad': 0.1,
            'mixed': 0.1,
        })

        self.assertEqual(profile['plutchik_dominant_emotion'], 'trust')
        self.assertEqual(profile['plutchik_profile_version'], 'v1')
        self.assertGreater(profile['plutchik_scores']['trust'], profile['plutchik_scores']['sadness'])
        self.assertEqual(len(profile['plutchik_top_emotions']), 3)


class FeelBetterRecoveryTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='recovery-user',
            email='recovery@example.com',
            password='password123',
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def _create_history(self, **overrides):
        payload = {
            'user': self.user,
            'prompt_text': 'I feel very sad.',
            'detected_emotion': 'sad',
            'emotion_confidence': 0.95,
            'emotion_scores': {'sad': 0.95, 'calm': 0.05},
            'ai_response': 'It is okay to feel sad.',
            'playlist_data': [],
            'music_picker_data': {},
            'session_duration': 0,
            'felt_better_response': None,
        }
        payload.update(overrides)
        return PromptHistory.objects.create(**payload)

    def test_check_feel_better_prompts_after_five_tracks_for_high_intensity_session(self):
        history = self._create_history()

        response = self.client.post(
            '/api/feel-better/',
            {
                'history_id': history.id,
                'duration': 930,
                'tracks_played': 5,
            },
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body['should_prompt'])
        self.assertEqual(body['next_checkpoint_tracks'], 5)
        self.assertEqual(body['recovery_plan']['original_emotion'], 'sad')
        self.assertEqual(body['recovery_plan']['support_emotion'], 'calm')

        history.refresh_from_db()
        self.assertEqual(history.session_duration, 930)
        self.assertEqual(
            history.music_picker_data['recovery_plan']['tracks_played'],
            5,
        )

    def test_feel_better_response_not_yet_moves_checkpoint_forward(self):
        history = self._create_history()

        response = self.client.post(
            '/api/feel-better-response/',
            {
                'history_id': history.id,
                'felt_better': False,
                'duration': 930,
                'tracks_played': 5,
            },
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['action'], 'continue_playlist')
        self.assertEqual(body['next_checkpoint_tracks'], 10)

        history.refresh_from_db()
        self.assertFalse(history.felt_better_response)
        self.assertEqual(
            history.music_picker_data['recovery_plan']['next_checkpoint_tracks'],
            10,
        )
        self.assertEqual(
            history.music_picker_data['recovery_plan']['not_yet_count'],
            1,
        )

    def test_feel_better_response_completes_session_only_plan(self):
        history = self._create_history(
            detected_emotion='calm',
            emotion_confidence=0.62,
            emotion_scores={'calm': 0.62, 'mixed': 0.38},
            music_picker_data={
                'session_plan': build_session_plan(
                    outcome_mode='calm_me_down',
                    session_length_minutes=45,
                    check_in_frequency_tracks=4,
                ),
            },
        )

        response = self.client.post(
            '/api/feel-better-response/',
            {
                'history_id': history.id,
                'felt_better': True,
                'duration': 780,
                'tracks_played': 4,
            },
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['action'], 'session_complete')
        self.assertTrue(body['session_plan']['completed'])
        self.assertIsNone(body['next_checkpoint_tracks'])

        history.refresh_from_db()
        self.assertTrue(history.felt_better_response)
        self.assertTrue(history.music_picker_data['session_plan']['completed'])

    @patch('api.views.music_picker.pick_playlist')
    @patch('api.views.spotify_service.select_primary_track')
    @patch('api.views.spotify_service.rank_tracks_for_emotion')
    @patch('api.views.spotify_service.sanitize_recommendations')
    @patch('api.views.spotify_service.get_recommendations_with_details')
    def test_feel_better_response_fine_now_returns_transition_playlist(
        self,
        mock_get_recommendations_with_details,
        mock_sanitize_recommendations,
        mock_rank_tracks_for_emotion,
        mock_select_primary_track,
        mock_pick_playlist,
    ):
        history = self._create_history()
        transition_track = {
            'id': 'calm-track-1',
            'name': 'Soft Landing',
            'artist': 'Calm Artist',
            'spotify_url': 'https://open.spotify.com/track/calm-track-1',
            'uri': 'spotify:track:calm-track-1',
            'preview_url': 'https://cdn.example.com/calm-track-1.mp3',
            'duration_ms': 180000,
            'recommendation_source': 'spotify_catalog',
        }
        mock_get_recommendations_with_details.return_value = {
            'tracks': [transition_track],
            'source': 'spotify_catalog',
            'used_fallback': False,
            'fallback_reason': None,
        }
        mock_sanitize_recommendations.return_value = [transition_track]
        mock_rank_tracks_for_emotion.return_value = [transition_track]
        mock_select_primary_track.return_value = transition_track
        mock_pick_playlist.return_value = {
            'tracks': [transition_track],
            'selected_track': transition_track,
            'playlist_track_ids': ['calm-track-1'],
            'strategy': 'linear_ranker_playlist',
            'reason': 'Transitioned into a lighter recovery mix.',
            'used_fallback': False,
            'provider': 'picker_ranker',
            'model': 'picker_linear_default',
            'error': None,
            'confidence': 0.88,
            'intent': 'playlist',
            'artist_name': 'Calm Artist',
            'track_name': 'Soft Landing',
            'playlist_category': 'calm',
            'confirmation': 'Switching to a calmer recovery mix now.',
        }

        response = self.client.post(
            '/api/feel-better-response/',
            {
                'history_id': history.id,
                'felt_better': True,
                'duration': 930,
                'tracks_played': 5,
            },
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['action'], 'transition_playlist')
        self.assertEqual(body['emotion'], 'calm')
        self.assertEqual(body['tracks'][0]['id'], 'calm-track-1')
        self.assertTrue(body['recovery_plan']['transition_applied'])

        history.refresh_from_db()
        self.assertTrue(history.felt_better_response)
        self.assertEqual(history.playlist_data[0]['id'], 'calm-track-1')
        self.assertTrue(
            history.music_picker_data['recovery_plan']['transition_applied'],
        )


# Pinned: .env.example sets a 72h max age on purpose (it outlasts missed
# refresh runs), so ages below would mean different things on different
# machines if they were read from the environment.
@override_settings(
    SPOTIFY_TRACK_POOL_FRESH_SECONDS=6 * 60 * 60,
    SPOTIFY_TRACK_POOL_MAX_AGE_SECONDS=24 * 60 * 60,
)
class EmotionTrackPoolTests(TestCase):
    """The shared per-emotion candidate pool ("waiting room").

    A pool hit must keep the recommendation off Spotify's search API without
    flattening the per-user half of the pipeline or serving stale rows
    forever.
    """

    def _pool_tracks(self, count, *, prefix='pooled'):
        return [
            {
                'id': f'{prefix}-{index}',
                'item_type': 'track',
                'name': f'Sunshine Anthem {index}',
                'artist': f'Bright Band {index}',
                'album': 'Feel Good Album',
                'spotify_url': f'https://open.spotify.com/track/{prefix}-{index}',
                'uri': f'spotify:track:{prefix}-{index}',
                'recommendation_source': 'spotify_catalog',
            }
            for index in range(count)
        ]

    def _create_pool(self, emotion, tracks, *, age_seconds=0):
        return EmotionTrackPool.objects.create(
            emotion=emotion,
            tracks=tracks,
            queries_used=['happy upbeat songs'],
            refreshed_at=timezone.now() - timedelta(seconds=age_seconds),
        )

    def _recommend(self, emotion='happy', *, search_mock=None, **kwargs):
        """Run a recommendation with catalog tokens available and search mocked."""
        search_mock = search_mock or Mock(return_value={'ok': True, 'items': []})
        with patch.object(
            spotify_service,
            '_get_catalog_token_candidates',
            return_value=([('client', 'client-token')], []),
        ):
            with patch.object(spotify_service, 'search_tracks_detailed', search_mock):
                result = spotify_service.get_recommendations_with_details(
                    emotion,
                    include_personalization=False,
                    **kwargs,
                )
        return result, search_mock

    def test_fresh_pool_serves_recommendations_without_any_spotify_search(self):
        self._create_pool('happy', self._pool_tracks(25))

        result, search_mock = self._recommend('happy', limit=5)

        search_mock.assert_not_called()
        self.assertTrue(result['ok'])
        self.assertTrue(result['pool_used'])
        self.assertEqual(result['pool_state'], 'fresh')
        self.assertEqual(len(result['tracks']), 5)
        self.assertTrue(all(track['pool_cached'] for track in result['tracks']))

    def test_pool_hit_still_runs_the_queries_specific_to_this_request(self):
        self._create_pool('happy', self._pool_tracks(25))
        artist_track = {
            'id': 'artist-track-1',
            'item_type': 'track',
            'name': 'Preferred Artist Anthem',
            'artist': 'Favorite Artist',
            'album': 'Album',
            'spotify_url': 'https://open.spotify.com/track/artist-track-1',
            'uri': 'spotify:track:artist-track-1',
            'recommendation_source': 'spotify_catalog',
        }
        search_mock = Mock(return_value={'ok': True, 'items': [artist_track]})

        result, search_mock = self._recommend(
            'happy',
            search_mock=search_mock,
            preferred_artists=['Favorite Artist'],
            limit=10,
        )

        self.assertTrue(result['pool_used'])
        # Only the preferred-artist queries reach Spotify; the emotion-baseline
        # ones are what the pool already answered.
        self.assertTrue(result['queries_tried'])
        self.assertTrue(all(
            'Favorite Artist' in query for query in result['queries_tried']
        ))
        track_ids = {track['id'] for track in result['tracks']}
        self.assertIn('artist-track-1', track_ids)
        self.assertTrue(any(track_id.startswith('pooled-') for track_id in track_ids))

    def test_stale_pool_is_still_served_rather_than_making_the_user_wait(self):
        self._create_pool('happy', self._pool_tracks(25), age_seconds=12 * 60 * 60)

        result, search_mock = self._recommend('happy', limit=5)

        search_mock.assert_not_called()
        self.assertTrue(result['pool_used'])
        self.assertEqual(result['pool_state'], 'stale')

    def test_expired_pool_is_ignored_so_the_cache_self_heals(self):
        self._create_pool('happy', self._pool_tracks(25), age_seconds=48 * 60 * 60)
        search_mock = Mock(return_value={
            'ok': True,
            'items': self._pool_tracks(5, prefix='live'),
        })

        result, search_mock = self._recommend('happy', search_mock=search_mock, limit=5)

        search_mock.assert_called()
        self.assertFalse(result['pool_used'])
        self.assertTrue(all(
            track['id'].startswith('live-') for track in result['tracks']
        ))

    def test_thin_pool_falls_back_to_live_search_for_the_rest(self):
        self._create_pool('happy', self._pool_tracks(1))
        search_mock = Mock(return_value={
            'ok': True,
            'items': self._pool_tracks(6, prefix='live'),
        })

        result, search_mock = self._recommend('happy', search_mock=search_mock, limit=5)

        search_mock.assert_called()
        self.assertTrue(result['pool_used'])
        self.assertEqual(result['pool_tracks_used'], 1)
        self.assertGreaterEqual(len(result['tracks']), 5)

    def test_seed_track_requests_bypass_the_pool(self):
        self._create_pool('happy', self._pool_tracks(25))
        search_mock = Mock(return_value={
            'ok': True,
            'items': self._pool_tracks(5, prefix='live'),
        })

        result, search_mock = self._recommend(
            'happy',
            search_mock=search_mock,
            seed_track_name='Specific Song',
            seed_artist_name='Specific Artist',
            limit=5,
        )

        search_mock.assert_called()
        self.assertFalse(result['pool_used'])

    def test_emotion_only_request_warms_the_pool(self):
        search_mock = Mock(return_value={
            'ok': True,
            'items': self._pool_tracks(5, prefix='live'),
        })

        self._recommend('happy', search_mock=search_mock, limit=5)

        warmed_pool = EmotionTrackPool.objects.get(emotion='happy')
        self.assertTrue(warmed_pool.tracks)
        self.assertNotIn('pool_cached', warmed_pool.tracks[0])

    def test_personalized_request_does_not_warm_the_shared_pool(self):
        search_mock = Mock(return_value={
            'ok': True,
            'items': self._pool_tracks(5, prefix='live'),
        })

        self._recommend(
            'happy',
            search_mock=search_mock,
            preferred_artists=['Favorite Artist'],
            limit=5,
        )

        self.assertFalse(EmotionTrackPool.objects.filter(emotion='happy').exists())

    def test_store_pool_does_not_shrink_a_bigger_fresh_pool(self):
        self._create_pool('happy', self._pool_tracks(40))

        stored_count = pool.store_pool('happy', self._pool_tracks(5, prefix='thin'))

        self.assertEqual(stored_count, 0)
        self.assertEqual(len(EmotionTrackPool.objects.get(emotion='happy').tracks), 40)

    def test_store_pool_replaces_a_bigger_pool_when_forced(self):
        self._create_pool('happy', self._pool_tracks(40))

        stored_count = pool.store_pool(
            'happy',
            self._pool_tracks(5, prefix='forced'),
            force=True,
        )

        self.assertEqual(stored_count, 5)
        self.assertEqual(len(EmotionTrackPool.objects.get(emotion='happy').tracks), 5)

    def test_sample_tracks_skips_tracks_the_request_already_has(self):
        pool_tracks = self._pool_tracks(4)

        sampled_tracks = pool.sample_tracks(
            pool_tracks,
            limit=4,
            seen_track_ids={'pooled-0'},
            seen_track_match_keys=set(),
        )

        self.assertEqual(len(sampled_tracks), 3)
        self.assertNotIn('pooled-0', {track['id'] for track in sampled_tracks})

    @override_settings(SPOTIFY_TRACK_POOL_ENABLED=False)
    def test_disabled_pool_is_never_read(self):
        self._create_pool('happy', self._pool_tracks(25))
        search_mock = Mock(return_value={
            'ok': True,
            'items': self._pool_tracks(5, prefix='live'),
        })

        result, search_mock = self._recommend('happy', search_mock=search_mock, limit=5)

        search_mock.assert_called()
        self.assertFalse(result['pool_used'])

    def test_refresh_emotion_pool_stores_baseline_candidates(self):
        search_mock = Mock(return_value={
            'ok': True,
            'items': self._pool_tracks(10, prefix='refreshed'),
        })

        with patch.object(
            spotify_service,
            '_get_catalog_token_candidates',
            return_value=([('client', 'client-token')], []),
        ):
            with patch.object(spotify_service, 'search_tracks_detailed', search_mock):
                refresh_result = spotify_service.refresh_emotion_pool(
                    'calm',
                    target_size=10,
                )

        self.assertTrue(refresh_result['ok'])
        self.assertEqual(refresh_result['stored'], 10)
        self.assertEqual(len(EmotionTrackPool.objects.get(emotion='calm').tracks), 10)

    def _named(self, track_id, name, artist):
        return {
            'id': track_id, 'item_type': 'track', 'name': name, 'artist': artist, 'album': 'A',
            'spotify_url': f'https://open.spotify.com/track/{track_id}', 'uri': f'spotify:track:{track_id}',
            'recommendation_source': 'spotify_catalog',
        }

    def test_pools_drop_non_music_and_repeat_versions_on_read(self):
        """QA 2026-10-06: pools held "- Commentary" tracks and three takes of one song.

        Cleaned on read, so pools stored before the rule need no Spotify refresh.
        """
        self._create_pool('stressed', [
            self._named('t1', 'Shake It Off', 'Taylor Swift'),
            self._named('t2', 'Shake It Off - Commentary', 'Taylor Swift'),
            self._named('t3', 'Choker / Stressed Out / Migraine - Livestream Version', 'Twenty One Pilots'),
            self._named('t4', 'the cure - performance video', 'Olivia Rodrigo'),
            self._named('t5', 'Black', 'Pearl Jam'),
            self._named('t6', "Black - Brendan O'Brien Mix", 'Pearl Jam'),
            self._named('t7', 'Black - Kaufman Astoria Studios - MTV Unplugged - New York, NY 3/16/1992', 'Pearl Jam'),
            self._named('t8', 'Ikaw - (2024 Remastered Version)', 'Yeng Constantino'),
            self._named('t9', 'Ikaw', 'Yeng Constantino'),
            self._named('t10', 'Lover (Remix) [feat. Shawn Mendes]', 'Taylor Swift'),
            self._named('t11', 'Lover', 'Taylor Swift'),
            # Different songs that merely share a title stay.
            self._named('t12', 'Bittersweet', 'Madison Beer'),
            self._named('t13', 'Bittersweet', 'Matilda Mann'),
        ])

        names = [track['name'] for track in pool.read_pool('stressed')['tracks']]

        self.assertEqual(names, [
            'Shake It Off', 'Black', 'Ikaw - (2024 Remastered Version)',
            'Lover (Remix) [feat. Shawn Mendes]', 'Bittersweet', 'Bittersweet',
        ])

    def test_live_search_results_skip_non_music_tracks(self):
        search_mock = Mock(return_value={'ok': True, 'items': [
            self._named('c1', 'Look What You Made Me Do - Commentary', 'Taylor Swift'),
            self._named('m1', 'Calm Waters', 'Quiet Band'),
        ]})
        with patch.object(
            spotify_service, '_get_catalog_token_candidates', return_value=([('client', 'client-token')], []),
        ):
            with patch.object(spotify_service, 'search_tracks_detailed', search_mock):
                with patch.object(
                    spotify_service, '_filter_tracks_for_query', side_effect=lambda query, items, **kwargs: items,
                ):
                    result = spotify_service.build_emotion_pool('calm', target_size=10)

        names = {track['name'] for track in result['tracks']}
        self.assertIn('Calm Waters', names)
        self.assertNotIn('Look What You Made Me Do - Commentary', names)

    def _refresh_with_a_429_after_the_first_query(self, emotion, *, first_query_tracks):
        """First search answers, every later one is rate-limited (a 429 storm)."""
        rate_limited = {
            'ok': False, 'items': [], 'status_code': 429, 'reason': 'rate_limited',
            'error': 'rate limited', 'retry_after': 30,
        }
        search_mock = Mock(side_effect=[{'ok': True, 'items': first_query_tracks}] + [rate_limited] * 50)
        with patch.object(
            spotify_service,
            '_get_catalog_token_candidates',
            return_value=([('client', 'client-token')], []),
        ):
            with patch.object(spotify_service, 'search_tracks_detailed', search_mock):
                # The first queries are seed-track searches that drop anything
                # whose title doesn't match; this is about storage, not relevance.
                with patch.object(
                    spotify_service,
                    '_filter_tracks_for_query',
                    side_effect=lambda query, items, **kwargs: items,
                ):
                    return spotify_service.refresh_emotion_pool(emotion, target_size=100)

    def test_a_rate_limited_refresh_never_shrinks_a_live_pool(self):
        """QA 2026-10-06: a refresh during the 429 storm left "happy" with one track."""
        self._create_pool('happy', self._pool_tracks(25), age_seconds=8 * 60 * 60)

        result = self._refresh_with_a_429_after_the_first_query(
            'happy', first_query_tracks=self._pool_tracks(1, prefix='espresso'),
        )

        self.assertTrue(result['partial'])
        self.assertEqual(result['stored'], 0)
        # Lets the refresh command wait out Retry-After and try again.
        self.assertEqual(result['reason'], 'rate_limited')
        self.assertEqual(len(EmotionTrackPool.objects.get(emotion='happy').tracks), 25)

    def test_a_rate_limited_refresh_still_fills_an_empty_pool(self):
        result = self._refresh_with_a_429_after_the_first_query(
            'calm', first_query_tracks=self._pool_tracks(3, prefix='partial'),
        )

        self.assertEqual(result['stored'], 3)
        self.assertEqual(len(EmotionTrackPool.objects.get(emotion='calm').tracks), 3)

    def test_a_clean_refresh_still_rotates_a_bigger_pool(self):
        self._create_pool('calm', self._pool_tracks(40), age_seconds=8 * 60 * 60)
        search_mock = Mock(return_value={'ok': True, 'items': self._pool_tracks(10, prefix='rotated')})

        with patch.object(
            spotify_service,
            '_get_catalog_token_candidates',
            return_value=([('client', 'client-token')], []),
        ):
            with patch.object(spotify_service, 'search_tracks_detailed', search_mock):
                result = spotify_service.refresh_emotion_pool('calm', target_size=10)

        self.assertFalse(result['partial'])
        self.assertEqual(result['stored'], 10)

    def test_refresh_emotion_pool_reports_missing_tokens_without_storing(self):
        with patch.object(
            spotify_service,
            '_get_catalog_token_candidates',
            return_value=([], [{'reason': 'token_unavailable'}]),
        ):
            refresh_result = spotify_service.refresh_emotion_pool('calm')

        self.assertFalse(refresh_result['ok'])
        self.assertEqual(refresh_result['reason'], 'token_unavailable')
        self.assertEqual(refresh_result['stored'], 0)
        self.assertFalse(EmotionTrackPool.objects.exists())

    def test_refresh_command_skips_fresh_pools_unless_forced(self):
        self._create_pool('calm', self._pool_tracks(30))
        refresh_mock = Mock(return_value={
            'ok': True,
            'emotion': 'calm',
            'tracks': [],
            'queries_tried': [],
            'reason': None,
            'stored': 30,
        })

        with patch.object(spotify_service, 'refresh_emotion_pool', refresh_mock):
            call_command('refresh_emotion_pools', '--emotions', 'calm', stdout=StringIO())
            refresh_mock.assert_not_called()

            call_command(
                'refresh_emotion_pools',
                '--emotions',
                'calm',
                '--force',
                stdout=StringIO(),
            )
            refresh_mock.assert_called_once()

    def test_refresh_command_rejects_unknown_emotions(self):
        with self.assertRaises(CommandError):
            call_command('refresh_emotion_pools', '--emotions', 'sleepy', stdout=StringIO())

    def test_pool_serves_recommendations_when_spotify_tokens_are_unavailable(self):
        self._create_pool('happy', self._pool_tracks(25))

        with patch.object(
            spotify_service,
            '_get_catalog_token_candidates',
            return_value=([], [{'reason': 'token_unavailable'}]),
        ):
            result = spotify_service.get_recommendations_with_details(
                'happy',
                include_personalization=False,
                limit=5,
            )

        self.assertTrue(result['ok'])
        self.assertTrue(result['pool_used'])
        self.assertFalse(result['used_fallback'])
        self.assertEqual(result['fallback_reason'], 'token_unavailable')
        self.assertEqual(len(result['tracks']), 5)

    def test_curated_fallback_still_answers_when_there_is_no_pool_either(self):
        with patch.object(
            spotify_service,
            '_get_catalog_token_candidates',
            return_value=([], [{'reason': 'token_unavailable'}]),
        ):
            result = spotify_service.get_recommendations_with_details(
                'happy',
                include_personalization=False,
                limit=5,
            )

        self.assertFalse(result['pool_used'])
        self.assertTrue(result['used_fallback'])
        self.assertEqual(result['source'], 'fallback')
