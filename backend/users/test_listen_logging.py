"""Playback logging tests.

The music picker's ranker learns from listens, and it can only learn from a
contrast: something the user stayed with, against something they left. Before
these tests the client dropped every listen under 30 seconds and the backend
called any 30-second listen complete, so the training table held 12 rows that
were all positives. These lock in both halves of the fix.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from users.models import ListeningSession, PromptHistory, UserPreference

User = get_user_model()


class ListenLoggingTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='listener', email='listener@example.com', password='pw12345!',
        )
        self.client.force_authenticate(user=self.user)
        self.history = PromptHistory.objects.create(
            user=self.user,
            prompt_text='feeling low',
            detected_emotion='sad',
            emotion_confidence=0.9,
            emotion_scores={'sad': 0.9},
            ai_response='here is something',
            playlist_data=[],
            music_picker_data={'candidate_tracks': [], 'selected_track_id': 'track-1'},
        )

    def _report(self, **overrides):
        payload = {
            'track_id': 'track-1',
            'emotion': 'sad',
            'duration': 200,
            'track_name': 'A Song',
            'artist_name': 'An Artist',
            'item_type': 'track',
            'history_id': self.history.id,
        }
        payload.update(overrides)
        return self.client.post('/api/users/listen-time/', payload, format='json')

    # -- the regression this whole change exists for -------------------------

    def test_a_skip_is_recorded_as_a_negative(self):
        response = self._report(duration=7, duration_ms=210000, ended_reason='skipped')

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()['completed'])
        session = ListeningSession.objects.get()
        self.assertEqual(session.listen_duration, 7)
        self.assertFalse(session.completed)

    def test_a_skip_does_not_count_as_a_preference(self):
        """Recording a skip must not teach the personalizer that you like it."""
        self._report(duration=7, duration_ms=210000, ended_reason='skipped')
        self.assertEqual(UserPreference.objects.count(), 0)

    def test_a_played_through_track_is_a_positive(self):
        response = self._report(duration=200, duration_ms=210000, ended_reason='completed')

        self.assertTrue(response.json()['completed'])
        self.assertTrue(ListeningSession.objects.get().completed)
        preference = UserPreference.objects.get()
        self.assertEqual(preference.play_count, 1)
        self.assertEqual(preference.total_listen_time, 200)

    def test_one_prompt_can_hold_a_positive_and_a_negative(self):
        """A candidate set only becomes a training group with both labels."""
        self._report(track_id='kept', duration=190, duration_ms=210000)
        self._report(track_id='skipped', duration=5, duration_ms=210000)

        labels = dict(
            ListeningSession.objects.values_list('spotify_track_id', 'completed')
        )
        self.assertEqual(labels, {'kept': True, 'skipped': False})

    # -- completion judged against the track, not a flat number --------------

    def test_thirty_seconds_of_a_long_track_is_not_a_completed_listen(self):
        """The old flat 30s rule called this complete. It is a skip."""
        self._report(duration=30, duration_ms=300000)
        self.assertFalse(ListeningSession.objects.get().completed)

    def test_most_of_a_short_track_is_a_completed_listen(self):
        """The same flat rule called this a skip. The user heard nearly all of it."""
        self._report(duration=25, duration_ms=28000)
        self.assertTrue(ListeningSession.objects.get().completed)

    def test_an_explicit_completion_is_believed(self):
        """The player knows the track ran out, even when the position is short."""
        self._report(duration=12, duration_ms=200000, ended_reason='completed')
        self.assertTrue(ListeningSession.objects.get().completed)

    def test_an_unknown_track_length_falls_back_to_a_flat_threshold(self):
        self._report(duration=45)
        self.assertTrue(ListeningSession.objects.get().completed)

        ListeningSession.objects.all().delete()
        self._report(duration=12)
        self.assertFalse(ListeningSession.objects.get().completed)

    def test_a_corrupt_track_length_does_not_break_the_report(self):
        response = self._report(duration=45, duration_ms='not-a-number')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(ListeningSession.objects.get().completed)

    # -- everything that must keep working -----------------------------------

    def test_repeated_reports_update_one_row_per_track(self):
        self._report(duration=5, duration_ms=210000)
        self._report(duration=195, duration_ms=210000)

        session = ListeningSession.objects.get()
        self.assertEqual(session.listen_duration, 195)
        self.assertTrue(session.completed)

    def test_an_opted_out_session_records_nothing(self):
        self.history.music_picker_data = {'personalization': {'train_session': False}}
        self.history.save(update_fields=['music_picker_data'])

        response = self._report(duration=200, duration_ms=210000)

        self.assertEqual(response.json()['status'], 'tracking_disabled')
        self.assertEqual(ListeningSession.objects.count(), 0)
        self.assertEqual(UserPreference.objects.count(), 0)

    def test_a_playlist_link_is_not_a_listen(self):
        response = self._report(item_type='playlist')
        self.assertEqual(response.json()['status'], 'skipped')
        self.assertEqual(ListeningSession.objects.count(), 0)

    def test_the_open_in_spotify_placeholder_is_not_a_listen(self):
        response = self._report(artist_name='Open in Spotify')
        self.assertEqual(response.json()['status'], 'skipped')
        self.assertEqual(ListeningSession.objects.count(), 0)

    def test_progress_is_still_written_to_the_prompt(self):
        self._report(duration=64, duration_ms=210000)
        self.history.refresh_from_db()
        self.assertEqual(self.history.session_duration, 64)
