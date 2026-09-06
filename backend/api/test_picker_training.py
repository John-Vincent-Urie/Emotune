"""End-to-end check that playback logging produces trainable data.

The chain is: the player reports a listen -> the backend writes a
ListeningSession -> the trainer turns that prompt's candidate set into a
labelled group. A break anywhere in it looks identical from the outside (the
trainer just says "not enough data"), so it is worth testing as one piece.
"""
import importlib.util
from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from users.models import PromptHistory

TRAINER_PATH = Path(__file__).resolve().parents[2] / 'ml_model' / 'train_picker_ranker.py'

User = get_user_model()


def _load_trainer():
    spec = importlib.util.spec_from_file_location('train_picker_ranker', TRAINER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _candidate(track_id, **overrides):
    track = {
        'id': track_id,
        'name': f'Song {track_id}',
        'artist': 'Artist',
        'album': 'Album',
        'spotify_url': f'https://open.spotify.com/track/{track_id}',
        'duration_ms': 210000,
        'popularity': 40,
        'item_type': 'track',
        'recommendation_source': 'spotify_catalog',
        'personalization_score': 1.0,
        'emotion_alignment_score': 1.0,
    }
    track.update(overrides)
    return track


class PlaybackLoggingFeedsTheTrainerTests(TestCase):
    def setUp(self):
        self.trainer = _load_trainer()
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='trainee', email='trainee@example.com', password='pw12345!',
        )
        self.client.force_authenticate(user=self.user)
        self.history = PromptHistory.objects.create(
            user=self.user,
            prompt_text='feeling low',
            detected_emotion='sad',
            emotion_confidence=0.9,
            emotion_scores={'sad': 0.9},
            ai_response='here you go',
            playlist_data=[],
            music_picker_data={
                'candidate_tracks': [
                    _candidate('kept', emotion_alignment_score=9.0),
                    _candidate('left', emotion_alignment_score=2.0),
                    _candidate('unplayed', emotion_alignment_score=1.0),
                ],
                'selected_track_id': 'kept',
            },
        )

    def _report(self, track_id, duration, ended_reason='skipped'):
        return self.client.post(
            '/api/users/listen-time/',
            {
                'track_id': track_id,
                'emotion': 'sad',
                'duration': duration,
                'track_name': f'Song {track_id}',
                'artist_name': 'Artist',
                'item_type': 'track',
                'history_id': self.history.id,
                'duration_ms': 210000,
                'ended_reason': ended_reason,
            },
            format='json',
        )

    def test_a_listen_and_a_skip_become_one_labelled_group(self):
        self._report('kept', 190, ended_reason='completed')
        self._report('left', 6)

        groups, skipped = self.trainer.load_examples(label_mode='outcome')

        self.assertEqual(len(groups), 1)
        self.assertEqual(skipped['no_listen_outcome'], 0)
        self.assertEqual(list(groups[0]['labels']), [1, 0, 0])

    def test_a_prompt_with_no_listen_is_not_a_training_example(self):
        """This is the state the whole database was in: candidates, no outcome."""
        groups, skipped = self.trainer.load_examples(label_mode='outcome')

        self.assertEqual(groups, [])
        self.assertEqual(skipped['no_listen_outcome'], 1)

    def test_skips_alone_are_not_a_training_example(self):
        """All-negative groups teach nothing; the trainer must not count them."""
        self._report('kept', 4)
        self._report('left', 6)

        groups, skipped = self.trainer.load_examples(label_mode='outcome')

        self.assertEqual(groups, [])
        self.assertEqual(skipped['no_listen_outcome'], 1)

    def test_a_completed_listen_is_weighted_above_a_bare_pick(self):
        self._report('kept', 190, ended_reason='completed')
        self._report('left', 6)

        groups, _skipped = self.trainer.load_examples(label_mode='outcome')
        weights = list(groups[0]['weights'])

        self.assertGreater(weights[0], weights[1])

    def test_an_opted_out_prompt_is_never_trained_on(self):
        picker_data = dict(self.history.music_picker_data)
        picker_data['personalization'] = {'train_session': False}
        self.history.music_picker_data = picker_data
        self.history.save(update_fields=['music_picker_data'])

        groups, skipped = self.trainer.load_examples(label_mode='outcome')

        self.assertEqual(groups, [])
        self.assertEqual(skipped['opted_out'], 1)

    def test_the_selection_label_is_reported_as_position_zero(self):
        """Guards the leak the trainer warns about: on selection labels the
        positive is whatever the ranker already put first."""
        groups, _skipped = self.trainer.load_examples(label_mode='selection')

        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]['positive_positions'], [0])
