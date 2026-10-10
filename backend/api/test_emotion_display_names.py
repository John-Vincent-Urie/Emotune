"""Every emotion the API serves carries the therapist's display name next to the
machine label, so the app never has to hardcode "motivational" -> "Motivated"."""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from users.models import FavoriteTrack, PromptHistory


THERAPIST_ORDER = [
    ('happy', 'Happy'), ('sad', 'Sad'), ('angry', 'Angry'),
    ('motivational', 'Motivated'), ('fear', 'Scared'), ('depressing', 'Depressed'),
    ('nostalgic', 'Nostalgic'), ('romantic', 'Romantic'), ('lonely', 'Lonely'),
    ('calm', 'Calm'), ('stressed', 'Stressed'), ('surprising', 'Surprised'),
    ('mixed', 'Mixed'),
]

PREDICTION = {
    'emotion': 'motivational', 'confidence': 0.8,
    'all_scores': {'motivational': 0.8, 'fear': 0.2},
    'top_emotions': [
        {'emotion': 'motivational', 'confidence': 0.8},
        {'emotion': 'fear', 'confidence': 0.2},
    ],
    'prediction_source': 'bert', 'prediction_strategy': 'bert_high_confidence',
    'confidence_band': 'high', 'confidence_margin': 0.6,
    'fallback_used': False, 'fallback_reason': None, 'needs_review': False,
    'secondary_emotion': 'fear',
}


class EmotionDisplayNameTests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='labels', email='labels@example.com', password='pw12345!',
        )
        self.client.force_authenticate(user=self.user)

    def test_emotions_endpoint_lists_the_therapist_names_in_order(self):
        response = self.client.get('/api/emotions/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [(row['name'], row['display_name']) for row in response.json()],
            THERAPIST_ORDER,
        )

    def test_emotions_endpoint_requires_login(self):
        self.client.force_authenticate(user=None)

        self.assertEqual(self.client.get('/api/emotions/').status_code, 401)

    @patch('api.views.get_classifier')
    def test_analyze_labels_top_and_secondary_emotions(self, mock_classifier):
        mock_classifier.return_value.predict.return_value = PREDICTION

        body = self.client.post('/api/analyze/', {'text': 'lets go'}, format='json').json()

        self.assertEqual(body['emotion'], 'motivational')
        self.assertEqual(body['emotion_info']['display_name'], 'Motivated')
        self.assertEqual(
            [(item['emotion'], item['display_name']) for item in body['top_emotions']],
            [('motivational', 'Motivated'), ('fear', 'Scared')],
        )
        self.assertEqual(body['secondary_emotion'], 'fear')
        self.assertEqual(body['secondary_emotion_display'], 'Scared')

    def test_history_favorites_and_stats_carry_display_names(self):
        for emotion in ('depressing', 'depressing', 'surprising'):
            PromptHistory.objects.create(
                user=self.user, prompt_text='x', detected_emotion=emotion,
                emotion_confidence=0.9, emotion_scores={}, ai_response='', playlist_data=[],
            )
        FavoriteTrack.objects.create(
            user=self.user, spotify_track_id='t1', track_name='A', artist_name='B',
            emotion='fear',
        )

        history = self.client.get('/api/users/history/').json()
        self.assertEqual(
            sorted(item['detected_emotion_display'] for item in history),
            ['Depressed', 'Depressed', 'Surprised'],
        )
        stats = self.client.get('/api/users/emotion-stats/').json()
        self.assertEqual(
            stats,
            [
                {'detected_emotion': 'depressing', 'count': 2, 'display_name': 'Depressed'},
                {'detected_emotion': 'surprising', 'count': 1, 'display_name': 'Surprised'},
            ],
        )
        favorites = self.client.get('/api/users/favorites/').json()
        self.assertEqual(favorites[0]['emotion'], 'fear')
        self.assertEqual(favorites[0]['emotion_display'], 'Scared')

    def test_unknown_label_has_no_display_name(self):
        # An untagged favorite has no therapist name; the app falls back.
        FavoriteTrack.objects.create(
            user=self.user, spotify_track_id='t2', track_name='A', artist_name='B',
            emotion='untagged',
        )

        favorites = self.client.get('/api/users/favorites/').json()

        self.assertIsNone(favorites[0]['emotion_display'])
