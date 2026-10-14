"""Session mode routing.

Two modes ship, and the detected emotion picks one. Since the 2026-10-10
refactor a mode no longer changes WHICH songs are served -- those are always the
therapist-approved list for the detected emotion -- it only sets the listening
session's check-in wording and cadence (api/session_plan.py). The score blending
that used to pull a sad prompt's songs toward calm, and its tests, are gone.
"""
from django.test import SimpleTestCase

from api.session_plan import (
    EMOTION_OUTCOME_MODES,
    OUTCOME_MODE_CONFIG,
    normalize_outcome_mode,
    normalize_requested_outcome_mode,
    outcome_mode_for_emotion,
)
from users.models import EMOTION_CHOICES

MATCH_MOOD_EMOTIONS = {
    'happy', 'surprising', 'motivational', 'calm', 'romantic', 'nostalgic', 'mixed',
}
CALM_ME_DOWN_EMOTIONS = {
    'sad', 'stressed', 'depressing', 'angry', 'fear', 'lonely',
}


class ShippedModeTests(SimpleTestCase):
    def test_only_two_modes_exist(self):
        self.assertEqual(set(OUTCOME_MODE_CONFIG), {'match_mood', 'calm_me_down'})

    def test_the_retired_modes_are_gone(self):
        for mode in ('help_me_focus', 'lift_me_up', 'sleep'):
            with self.subTest(mode=mode):
                self.assertNotIn(mode, OUTCOME_MODE_CONFIG)
                # A stale client or signed token asking for one must not pin
                # the session; it falls through to routing.
                self.assertIsNone(normalize_requested_outcome_mode(mode))

    def test_a_retired_mode_still_normalizes_to_a_shipped_one(self):
        self.assertEqual(normalize_outcome_mode('sleep'), 'match_mood')


class RoutingTableTests(SimpleTestCase):
    def test_every_emotion_label_routes_somewhere(self):
        """A label with no route would silently fall back to match_mood."""
        labels = {value for value, _label in EMOTION_CHOICES}
        self.assertEqual(set(EMOTION_OUTCOME_MODES), labels)

    def test_every_route_names_a_shipped_mode(self):
        self.assertEqual(set(EMOTION_OUTCOME_MODES.values()), set(OUTCOME_MODE_CONFIG))

    def test_settled_emotions_are_mirrored(self):
        for emotion in sorted(MATCH_MOOD_EMOTIONS):
            with self.subTest(emotion=emotion):
                self.assertEqual(outcome_mode_for_emotion(emotion), 'match_mood')

    def test_distressing_emotions_get_the_calm_me_down_session(self):
        for emotion in sorted(CALM_ME_DOWN_EMOTIONS):
            with self.subTest(emotion=emotion):
                self.assertEqual(outcome_mode_for_emotion(emotion), 'calm_me_down')

    def test_an_unknown_emotion_is_mirrored(self):
        self.assertEqual(outcome_mode_for_emotion('elated'), 'match_mood')
        self.assertEqual(outcome_mode_for_emotion(None), 'match_mood')
