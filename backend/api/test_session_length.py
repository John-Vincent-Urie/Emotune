"""Session length coverage: the plan must still build end-to-end with the
default match_mood outcome mode (the only mode reachable now that the
profile picker is gone)."""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from users.models import PromptHistory
from api.session_plan import build_session_plan, update_session_plan_progress


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

    @patch('api.views.get_classifier')
    def test_analyze_with_only_session_length(self, mock_classifier):
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
        # The songs are calm's whole therapist-approved list, from the database.
        self.assertEqual(body['total'], 10)
        self.assertEqual(len(body['tracks']), 10)
        history = PromptHistory.objects.get(user=self.user)
        self.assertEqual(
            history.music_picker_data['session_plan']['target_minutes'], 15,
        )

    @patch('api.views.get_classifier')
    def test_analyze_without_session_length_has_no_plan(self, mock_classifier):
        mock_classifier.return_value.predict.return_value = PREDICTION
        response = self.client.post(
            '/api/analyze/', {'text': 'winding down'}, format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()['session_plan'])

    def test_recommend_by_emotion_with_only_session_length(self):
        response = self.client.post(
            '/api/recommend-by-emotion/',
            {'emotion': 'calm', 'session_length_minutes': 45},
            format='json',
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['session_plan']['target_minutes'], 45)
        self.assertEqual(PromptHistory.objects.filter(user=self.user).count(), 1)

    def test_browsing_a_tab_without_a_session_saves_no_history(self):
        response = self.client.post('/api/recommend-by-emotion/', {'emotion': 'calm'}, format='json')

        self.assertEqual(response.status_code, 200)
        self.assertFalse(PromptHistory.objects.filter(user=self.user).exists())

    @patch('api.views.get_classifier')
    def test_feel_better_tracks_session_progress(self, mock_classifier):
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

    @patch('api.views.get_classifier')
    def test_session_cadence_wins_over_the_recovery_interval(self, mock_classifier):
        # A high-confidence stressed reading starts a recovery plan (every 5
        # tracks) and calm_me_down's session plan (every 3). The app schedules
        # its next call from next_checkpoint_tracks, so both fields must follow
        # the session, which comes first.
        mock_classifier.return_value.predict.return_value = {
            **PREDICTION,
            'emotion': 'stressed', 'confidence': 0.97,
            'all_scores': {'stressed': 0.97, 'calm': 0.03},
            'top_emotions': [{'emotion': 'stressed', 'confidence': 0.97}],
        }
        analyze = self.client.post(
            '/api/analyze/',
            {'text': 'too many deadlines', 'session_length_minutes': 15},
            format='json',
        ).json()
        self.assertEqual(analyze['outcome_mode'], 'calm_me_down')
        self.assertTrue(analyze['recovery_plan'])

        early = self.client.post(
            '/api/feel-better/',
            {'history_id': analyze['history_id'], 'duration': 60, 'tracks_played': 1},
            format='json',
        ).json()

        self.assertFalse(early['should_prompt'])
        self.assertEqual(early['check_interval_tracks'], 3)
        self.assertEqual(early['next_checkpoint_tracks'], 3)

    def test_non_numeric_history_id_is_a_bad_request(self):
        for path in ('/api/feel-better/', '/api/feel-better-response/', '/api/users/listen-time/'):
            for bad in ('abc', '1; drop', -3, 0):
                response = self.client.post(
                    path, {'history_id': bad, 'track_id': 't', 'duration': 'x'}, format='json',
                )
                self.assertEqual(response.status_code, 400, (path, bad))

    @patch('api.views.get_classifier')
    def test_invalid_session_length_is_ignored(self, mock_classifier):
        mock_classifier.return_value.predict.return_value = PREDICTION
        for bad in ('', None, 'abc', -5):
            response = self.client.post(
                '/api/analyze/',
                {'text': 'winding down', 'session_length_minutes': bad},
                format='json',
            )
            self.assertEqual(response.status_code, 200, bad)
            self.assertIsNone(response.json()['session_plan'], bad)
