"""Session length coverage: the plan must still build end-to-end with the
default match_mood outcome mode (the only mode reachable now that the
profile picker is gone)."""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from users.models import PromptHistory
from api.recommendation_session import (
    build_session_plan,
    should_persist_recommendation_context,
    update_session_plan_progress,
)


TRACKS = {
    'tracks': [{
        'id': 't1', 'item_type': 'track', 'name': 'A', 'artist': 'B',
        'album': 'C', 'image': '', 'preview_url': None, 'duration_ms': 180000,
        'spotify_url': 'https://open.spotify.com/track/t1',
        'uri': 'spotify:track:t1', 'recommendation_source': 'spotify_catalog',
    }],
    'source': 'spotify', 'used_fallback': False, 'fallback_reason': None,
    'personalized': False, 'personalization_sources': [],
    'personalization_missing_scopes': [],
}

PREDICTION = {
    'emotion': 'calm', 'confidence': 0.9,
    'all_scores': {'calm': 0.9, 'happy': 0.1},
    'top_emotions': [{'emotion': 'calm', 'confidence': 0.9}],
    'prediction_source': 'bert', 'prediction_strategy': 'bert_high_confidence',
    'confidence_band': 'high', 'confidence_margin': 0.8,
    'fallback_used': False, 'fallback_reason': None, 'needs_review': False,
    'secondary_emotion': 'happy',
}


class SessionLengthUnitTests(APITestCase):
    def test_each_profile_chip_builds_matching_plan(self):
        for minutes in (15, 20, 45):
            plan = build_session_plan(
                outcome_mode='match_mood',
                session_length_minutes=minutes,
                check_in_frequency_tracks=None,
            )
            self.assertIsNotNone(plan, minutes)
            self.assertEqual(plan['target_minutes'], minutes)
            self.assertEqual(plan['target_seconds'], minutes * 60)
            self.assertEqual(plan['mode'], 'match_mood')
            # Auto check-in falls back to the mode default (5 for match_mood)
            self.assertEqual(plan['check_in_after_tracks'], 5)
            self.assertEqual(plan['phase'], 'settle')
            self.assertFalse(plan['completed'])

    def test_auto_chip_uses_mode_default_minutes(self):
        plan = build_session_plan(
            outcome_mode='match_mood', session_length_minutes=None,
        )
        self.assertEqual(plan['target_minutes'], 20)

    def test_zero_minutes_disables_plan(self):
        self.assertIsNone(
            build_session_plan(outcome_mode='match_mood', session_length_minutes=0)
        )

    def test_check_in_override_is_honoured(self):
        plan = build_session_plan(
            outcome_mode='match_mood',
            session_length_minutes=15,
            check_in_frequency_tracks=3,
        )
        self.assertEqual(plan['check_in_after_tracks'], 3)

    def test_session_length_alone_marks_context_worth_persisting(self):
        self.assertTrue(should_persist_recommendation_context(
            outcome_mode='match_mood', session_length_minutes=15, taste_profile={},
        ))
        self.assertFalse(should_persist_recommendation_context(
            outcome_mode='match_mood', session_length_minutes=0, taste_profile={},
        ))

    def test_progress_moves_through_phases(self):
        plan = build_session_plan(
            outcome_mode='match_mood', session_length_minutes=15,
        )
        settle = update_session_plan_progress(plan, duration_seconds=60, tracks_played=1)
        self.assertEqual(settle['phase'], 'settle')
        support = update_session_plan_progress(plan, duration_seconds=6 * 60, tracks_played=3)
        self.assertEqual(support['phase'], 'support')
        close = update_session_plan_progress(plan, duration_seconds=15 * 60, tracks_played=6)
        self.assertEqual(close['phase'], 'close')
        self.assertEqual(close['progress_seconds'], 900)


class SessionLengthApiTests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='sessionprobe', email='probe@example.com', password='pw12345!',
        )
        self.client.force_authenticate(user=self.user)

    @patch('api.views.spotify_service.get_recommendations_with_details', return_value=TRACKS)
    @patch('api.views.get_classifier')
    def test_analyze_with_only_session_length(self, mock_classifier, _mock_tracks):
        mock_classifier.return_value.predict.return_value = PREDICTION
        response = self.client.post(
            '/api/analyze/',
            {'text': 'winding down', 'session_length_minutes': 15},
            format='json',
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['outcome_mode'], 'match_mood')
        self.assertIsNotNone(body['session_plan'])
        self.assertEqual(body['session_plan']['target_minutes'], 15)
        history = PromptHistory.objects.get(user=self.user)
        self.assertEqual(
            history.music_picker_data['session_plan']['target_minutes'], 15,
        )

    @patch('api.views.spotify_service.get_recommendations_with_details', return_value=TRACKS)
    @patch('api.views.get_classifier')
    def test_analyze_without_session_length_has_no_plan(self, mock_classifier, _mock_tracks):
        mock_classifier.return_value.predict.return_value = PREDICTION
        response = self.client.post(
            '/api/analyze/', {'text': 'winding down'}, format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()['session_plan'])

    @patch('api.views.spotify_service.get_recommendations_with_details', return_value=TRACKS)
    def test_recommend_by_emotion_with_only_session_length(self, _mock_tracks):
        response = self.client.post(
            '/api/recommend-by-emotion/',
            {'emotion': 'calm', 'session_length_minutes': 45},
            format='json',
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['session_plan']['target_minutes'], 45)
        self.assertEqual(PromptHistory.objects.filter(user=self.user).count(), 1)

    @patch('api.views.spotify_service.get_recommendations_with_details', return_value=TRACKS)
    @patch('api.views.get_classifier')
    def test_feel_better_tracks_session_progress(self, mock_classifier, _mock_tracks):
        mock_classifier.return_value.predict.return_value = PREDICTION
        analyze = self.client.post(
            '/api/analyze/',
            {
                'text': 'winding down',
                'session_length_minutes': 15,
                'check_in_frequency_tracks': 3,
            },
            format='json',
        )
        history_id = analyze.json()['history_id']

        early = self.client.post(
            '/api/feel-better/',
            {'history_id': history_id, 'duration': 120, 'tracks_played': 1},
            format='json',
        ).json()
        self.assertFalse(early['should_prompt'])
        self.assertEqual(early['session_plan']['progress_seconds'], 120)
        self.assertEqual(early['check_interval_tracks'], 3)

        at_checkpoint = self.client.post(
            '/api/feel-better/',
            {'history_id': history_id, 'duration': 6 * 60, 'tracks_played': 3},
            format='json',
        ).json()
        self.assertTrue(at_checkpoint['should_prompt'])
        self.assertEqual(at_checkpoint['session_plan']['phase'], 'support')

        at_target = self.client.post(
            '/api/feel-better/',
            {'history_id': history_id, 'duration': 15 * 60, 'tracks_played': 6},
            format='json',
        ).json()
        self.assertEqual(at_target['session_plan']['phase'], 'close')
        self.assertEqual(at_target['session_plan']['progress_seconds'], 900)

    @patch('api.views.spotify_service.get_recommendations_with_details', return_value=TRACKS)
    @patch('api.views.get_classifier')
    def test_invalid_session_length_is_ignored(self, mock_classifier, _mock_tracks):
        mock_classifier.return_value.predict.return_value = PREDICTION
        for bad in ('', None, 'abc', -5):
            response = self.client.post(
                '/api/analyze/',
                {'text': 'winding down', 'session_length_minutes': bad},
                format='json',
            )
            self.assertEqual(response.status_code, 200, bad)
            self.assertIsNone(response.json()['session_plan'], bad)
