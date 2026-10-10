from datetime import timedelta
import tempfile
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from unittest.mock import Mock, patch

import requests
from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from api.models import EmotionSong
from api.session_plan import build_session_plan
from rest_framework_simplejwt.tokens import AccessToken

from api.spotify_oauth_state import (
    issue_state as issue_spotify_oauth_state,
    read_state as read_spotify_oauth_state,
)
from api.spotify_service import (
    SpotifyService,
    spotify_service,
)
from ml.emotion_classifier import EmotionClassifier
from ml.plutchik_mapper import build_plutchik_profile
from users.models import PromptHistory


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


def _prediction(emotion, confidence=0.91):
    return {
        'emotion': emotion,
        'confidence': confidence,
        'all_scores': {emotion: confidence, 'mixed': round(1 - confidence, 2)},
        'top_emotions': [{'emotion': emotion, 'confidence': confidence}],
        'secondary_emotion': 'mixed',
        'prediction_source': 'bert',
        'prediction_strategy': 'bert_high_confidence',
        'confidence_band': 'high',
        'confidence_margin': 0.8,
        'fallback_used': False,
        'fallback_reason': None,
        'needs_review': False,
    }


def _approved_titles(emotion_name):
    return list(
        EmotionSong.objects.filter(emotion__name=emotion_name, song__is_active=True)
        .order_by('position')
        .values_list('song__title', flat=True)
    )


class AnalyzeEmotionTests(TestCase):
    """EmoTune Architecture Refactor Plan, sec. 11: the analysis returns every
    active therapist-approved song for the detected emotion, from the database,
    in the therapist's order -- no ranking, no Spotify search."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='analyze-user', email='analyze@example.com', password='password123',
        )
        self.client.force_authenticate(user=self.user)

    def _analyze(self, emotion='depressing', text='everything feels heavy lately', **extra):
        with patch('api.views.get_classifier') as get_classifier, \
                patch('api.http_client.request') as spotify_request, \
                patch('api.http_client.post') as spotify_post:
            get_classifier.return_value.predict.return_value = _prediction(emotion)
            response = self.client.post('/api/analyze/', {'text': text, **extra}, format='json')
        spotify_request.assert_not_called()
        spotify_post.assert_not_called()
        return response

    def test_returns_every_approved_song_for_the_detected_emotion_in_therapist_order(self):
        body = self._analyze('depressing').json()

        self.assertEqual(body['emotion'], 'depressing')
        self.assertEqual(body['emotion_info']['display_name'], 'Depressed')
        self.assertEqual([t['name'] for t in body['tracks']], _approved_titles('depressing'))
        self.assertEqual(body['total'], 9)
        self.assertEqual([t['position'] for t in body['tracks']], list(range(1, 10)))
        self.assertTrue(all(t['recommendation_source'] == 'therapist_list' for t in body['tracks']))
        # Owner correction 2026-10-10: no longer approved for Depressed.
        self.assertNotIn('Innocence', [t['name'] for t in body['tracks']])

    def test_no_song_from_another_emotion_is_returned(self):
        body = self._analyze('happy').json()

        self.assertEqual(set(t['name'] for t in body['tracks']), set(_approved_titles('happy')))

    def test_a_matched_song_carries_what_in_app_playback_needs(self):
        track = next(t for t in self._analyze('motivational').json()['tracks'] if t['name'] == 'Graduation March')

        self.assertEqual(track['artist'], 'Holiday Celebration Troupe')
        self.assertTrue(track['playable'])
        self.assertEqual(track['id'], '1uaFfBstndFSw4vntlb1k7')
        self.assertEqual(track['uri'], 'spotify:track:1uaFfBstndFSw4vntlb1k7')
        self.assertEqual(track['spotify_url'], 'https://open.spotify.com/track/1uaFfBstndFSw4vntlb1k7')

    def test_an_unmatched_song_is_listed_with_a_search_link_but_not_playable(self):
        link = EmotionSong.objects.filter(song__spotify_track_id__isnull=True).select_related('emotion', 'song').first()
        track = next(
            t for t in self._analyze(link.emotion.name).json()['tracks'] if t['song_id'] == link.song_id
        )

        self.assertFalse(track['playable'])
        self.assertEqual(track['id'], f'song-{link.song_id}')
        self.assertEqual(track['uri'], '')
        self.assertTrue(track['spotify_url'].startswith('https://open.spotify.com/search/'))

    def test_inactive_songs_are_left_out(self):
        first = EmotionSong.objects.filter(emotion__name='calm').order_by('position').first().song
        first.is_active = False
        first.save(update_fields=['is_active'])

        body = self._analyze('calm').json()

        self.assertEqual(body['total'], 9)
        self.assertNotIn(first.title, [t['name'] for t in body['tracks']])

    def test_a_song_approved_for_several_emotions_appears_once_in_each(self):
        for emotion in ('depressing', 'calm', 'stressed'):
            with self.subTest(emotion=emotion):
                names = [t['name'] for t in self._analyze(emotion).json()['tracks']]
                self.assertEqual(names.count('Leaves'), 1)

    def test_an_emotion_with_no_songs_returns_an_empty_list_and_a_message(self):
        EmotionSong.objects.filter(emotion__name='mixed').delete()

        body = self._analyze('mixed').json()

        self.assertEqual((body['tracks'], body['total']), ([], 0))
        self.assertIn('message', body)

    def test_an_unsupported_label_returns_no_unrelated_playlist(self):
        body = self._analyze('elated').json()

        self.assertIsNone(body['emotion_info'])
        self.assertEqual(body['tracks'], [])
        self.assertEqual(body['message'], 'No supported emotion was identified.')

    def test_the_removed_ranking_fields_are_gone(self):
        body = self._analyze('happy').json()

        for key in ('continuation_token', 'loading_more_tracks', 'selected_track', 'taste_profile',
                    'music_picker_strategy', 'recommendation_target_emotion', 'tracks_personalized'):
            with self.subTest(key=key):
                self.assertNotIn(key, body)

    def test_the_list_is_saved_to_history(self):
        body = self._analyze('happy').json()

        history = PromptHistory.objects.get(id=body['history_id'])
        self.assertEqual(history.playlist_data, body['tracks'])
        self.assertEqual(history.music_picker_data['song_source'], 'therapist_list')

    def test_a_classifier_failure_still_answers_with_the_mixed_list(self):
        with patch('api.views.get_classifier') as get_classifier:
            get_classifier.return_value.predict.side_effect = RuntimeError('classifier crashed')
            body = self.client.post('/api/analyze/', {'text': 'hmm'}, format='json').json()

        self.assertEqual(body['emotion'], 'mixed')
        self.assertEqual(body['total'], 6)

    def test_blank_or_overlong_text_is_rejected(self):
        for text in ('', '   ', 'x' * 2001):
            with self.subTest(length=len(text)):
                response = self.client.post('/api/analyze/', {'text': text}, format='json')
                self.assertEqual(response.status_code, 400)

    def test_the_old_continuation_endpoint_is_gone(self):
        response = self.client.post('/api/recommendation-playlist/', {'continuation_token': 'x'}, format='json')

        self.assertEqual(response.status_code, 404)


class ExplicitEmotionRecommendationTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='explicit-emotion-user', email='explicit@example.com', password='password123',
        )
        self.client.force_authenticate(user=self.user)

    @patch('api.views.get_classifier')
    def test_a_tab_returns_that_emotions_approved_list_without_classifying(self, get_classifier):
        body = self.client.post('/api/recommend-by-emotion/', {'emotion': 'motivational'}, format='json').json()

        self.assertEqual(body['emotion'], 'motivational')
        self.assertEqual(body['prediction_strategy'], 'explicit_emotion_tab')
        self.assertEqual([t['name'] for t in body['tracks']], _approved_titles('motivational'))
        self.assertEqual(body['total'], 10)
        get_classifier.assert_not_called()
        self.assertEqual(PromptHistory.objects.count(), 0)

    def test_a_tab_with_a_session_saves_history(self):
        body = self.client.post(
            '/api/recommend-by-emotion/',
            {'emotion': 'calm', 'session_length_minutes': 20},
            format='json',
        ).json()

        self.assertEqual(PromptHistory.objects.get(id=body['history_id']).playlist_data, body['tracks'])

    def test_an_unknown_tab_is_rejected(self):
        response = self.client.post('/api/recommend-by-emotion/', {'emotion': 'elated'}, format='json')

        self.assertEqual(response.status_code, 400)


class SpotifyAuthPlaybackTests(TestCase):
    """Spotify auth, artist/track search for the profile picker, and in-app playback."""
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

    def test_feel_better_response_fine_now_returns_transition_playlist(self):
        """The switch serves the support emotion's approved songs, in order."""
        history = self._create_history()

        response = self.client.post(
            '/api/feel-better-response/',
            {'history_id': history.id, 'felt_better': True, 'duration': 930, 'tracks_played': 5},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['action'], 'transition_playlist')
        self.assertEqual(body['emotion'], 'calm')
        self.assertEqual([t['name'] for t in body['tracks']], _approved_titles('calm'))
        self.assertEqual(body['total'], 10)
        self.assertTrue(body['recovery_plan']['transition_applied'])

        history.refresh_from_db()
        self.assertTrue(history.felt_better_response)
        self.assertEqual(history.playlist_data, body['tracks'])
        self.assertTrue(history.music_picker_data['recovery_plan']['transition_applied'])
