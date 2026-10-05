"""Outcome mode routing (docs/arch).

Two modes ship. The classifier picks between them: emotions the listener has no
reason to be moved out of are mirrored, and the distressing ones are steered
toward something steadier. There is no user-facing switch, so these tests are
the only thing holding the routing table in place.
"""
from django.test import SimpleTestCase

from api.recommendation_session import (
    EMOTION_OUTCOME_MODES,
    OUTCOME_MODE_CONFIG,
    apply_outcome_mode,
    normalize_outcome_mode,
    normalize_requested_outcome_mode,
    outcome_mode_for_emotion,
    outcome_target_weight,
    resolve_outcome_mode,
)
from ml.emotion_labels import EMOTIONS
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

    def test_distressing_emotions_are_steered(self):
        """The point of the whole feature: someone who says they feel hopeless
        must not be handed more hopeless music."""
        for emotion in sorted(CALM_ME_DOWN_EMOTIONS):
            with self.subTest(emotion=emotion):
                self.assertEqual(outcome_mode_for_emotion(emotion), 'calm_me_down')

    def test_an_unknown_emotion_is_mirrored(self):
        self.assertEqual(outcome_mode_for_emotion('elated'), 'match_mood')
        self.assertEqual(outcome_mode_for_emotion(None), 'match_mood')


class ResolutionTests(SimpleTestCase):
    def test_the_emotion_decides_when_nothing_was_requested(self):
        self.assertEqual(resolve_outcome_mode('sad'), 'calm_me_down')
        self.assertEqual(resolve_outcome_mode('happy'), 'match_mood')

    def test_an_explicit_request_wins(self):
        """Stage 2 has to stay on the mode stage 1 committed to."""
        self.assertEqual(resolve_outcome_mode('sad', 'match_mood'), 'match_mood')
        self.assertEqual(resolve_outcome_mode('happy', 'calm_me_down'), 'calm_me_down')

    def test_a_retired_request_falls_through_to_routing(self):
        self.assertEqual(resolve_outcome_mode('sad', 'sleep'), 'calm_me_down')

    def test_blank_requests_fall_through_to_routing(self):
        for requested in (None, '', '   '):
            with self.subTest(requested=requested):
                self.assertEqual(resolve_outcome_mode('angry', requested), 'calm_me_down')


class SteerTests(SimpleTestCase):
    """Routing only matters if the chosen mode actually moves the target."""

    def _profile(self, emotion, scores):
        return apply_outcome_mode(
            {'all_scores': scores},
            resolve_outcome_mode(emotion),
        )

    @staticmethod
    def _scores(emotion, confidence):
        """A score map summing to 1, with `emotion` dominant.

        Fillers exclude the target emotion so the map cannot collapse a key
        onto itself, and they sum to exactly 1 so match_mood's renormalization
        is the identity and the mirrored case can be asserted exactly.
        """
        fillers = [
            candidate for candidate in ('calm', 'nostalgic', 'surprising')
            if candidate != emotion
        ][:2]
        rest = (1.0 - confidence) / len(fillers)
        return {emotion: confidence, **{filler: rest for filler in fillers}}

    def test_a_sad_prompt_is_routed_and_pulled_toward_calm(self):
        scores = self._scores('sad', 0.8)
        profile = self._profile('sad', scores)

        self.assertEqual(profile['outcome_mode'], 'calm_me_down')
        self.assertLess(profile['all_scores']['sad'], scores['sad'])
        self.assertGreater(profile['all_scores']['calm'], scores['calm'])

    def test_a_moderate_distress_reading_flips_the_target_to_calm(self):
        profile = self._profile('sad', self._scores('sad', 0.6))
        self.assertEqual(profile['emotion'], 'calm')

    def test_a_confident_distress_reading_does_not_flip_the_target(self):
        """Documents a real limit rather than an intended design.

        calm_me_down blends 58% toward its calm target, which is not enough to
        overtake a detected emotion above roughly 0.7 -- the mode narrows the
        gap (sad 0.8 -> 0.394, calm 0.05 -> 0.361) but sad still leads, so the
        strongest distress readings are the ones least steered. Raising
        target_weight is a therapeutic tuning call, so this test pins the
        current behaviour instead of asserting a preference.
        """
        profile = self._profile('sad', self._scores('sad', 0.9))

        self.assertEqual(profile['outcome_mode'], 'calm_me_down')
        self.assertEqual(profile['emotion'], 'sad')

    def test_an_angry_prompt_is_pulled_toward_calm(self):
        scores = self._scores('angry', 0.8)
        profile = self._profile('angry', scores)

        self.assertEqual(profile['outcome_mode'], 'calm_me_down')
        self.assertLess(profile['all_scores']['angry'], scores['angry'])
        self.assertGreater(profile['all_scores']['calm'], scores['calm'])
        self.assertEqual(profile['emotion'], 'calm')

    def test_even_a_near_certain_angry_reading_never_outranks_calm(self):
        """`angry` has no seat in calm_me_down's target_weights -- unlike `sad`,
        which is one of the mode's acceptable landing states, the mode never
        wants to *land* on `angry`. Before this was fixed, a confident enough
        reading (~0.76+) could out-blend calm and keep the aggressive/hardcore
        keyword set live indefinitely -- the failure mode calm_me_down exists to
        avoid, and worse than the analogous `sad` limit above because `angry`'s
        own content is the escalating one.

        Asserted with no phase, i.e. the flat pre-iso weight. Under the phased
        arc a confident `angry` *does* lead during `settle` -- that is the
        iso-principle's match step, and IsoPrincipleArcTests covers it -- but it
        must still never be where the session comes to rest.
        """
        profile = self._profile('angry', self._scores('angry', 0.99))

        self.assertEqual(profile['outcome_mode'], 'calm_me_down')
        self.assertEqual(profile['emotion'], 'calm')
        self.assertEqual(profile['secondary_emotion'], 'angry')

    def test_depressing_and_lonely_get_the_same_protection_as_angry(self):
        """Same gap, same fix: neither has a seat in target_weights either."""
        for emotion in ('depressing', 'lonely'):
            with self.subTest(emotion=emotion):
                profile = self._profile(emotion, self._scores(emotion, 0.99))
                self.assertEqual(profile['emotion'], 'calm')

    def test_a_happy_prompt_is_left_alone(self):
        scores = self._scores('happy', 0.8)
        profile = self._profile('happy', scores)

        self.assertEqual(profile['outcome_mode'], 'match_mood')
        self.assertEqual(profile['emotion'], 'happy')
        for emotion, value in scores.items():
            with self.subTest(emotion=emotion):
                self.assertAlmostEqual(profile['all_scores'][emotion], value, places=6)

    def test_mixed_is_left_alone(self):
        """Mixed means the classifier could not commit; steering on that
        presumes more than the signal supports."""
        profile = self._profile('mixed', {'mixed': 0.5, 'sad': 0.3, 'happy': 0.2})
        self.assertEqual(profile['outcome_mode'], 'match_mood')


class IsoPrincipleArcTests(SimpleTestCase):
    """calm_me_down should match the listener first, then move -- not jump.

    The iso-principle (Altshuler 1944) is match-then-shift; a single fixed
    target_weight can only express one point on that arc. These pin the arc
    itself: same reading, different session phase, different music.
    """

    @staticmethod
    def _reading(emotion, confidence):
        """A full 13-label distribution, remainder spread across the rest.

        Spreading matters: piling the remainder onto `calm` alone would inflate
        calm's blended score and hide whether the match step actually works.
        """
        rest = (1.0 - confidence) / (len(EMOTIONS) - 1)
        scores = {label: rest for label in EMOTIONS}
        scores[emotion] = confidence
        return {'emotion': emotion, 'confidence': confidence, 'all_scores': scores}

    def _served(self, emotion, confidence, phase):
        return apply_outcome_mode(
            self._reading(emotion, confidence),
            resolve_outcome_mode(emotion),
            phase=phase,
        )['emotion']

    def test_a_clear_distress_reading_is_matched_then_landed_on_calm(self):
        for emotion in ('angry', 'depressing', 'lonely', 'sad', 'stressed', 'fear'):
            with self.subTest(emotion=emotion):
                self.assertEqual(self._served(emotion, 0.9, 'settle'), emotion)
                self.assertEqual(self._served(emotion, 0.9, 'close'), 'calm')

    def test_lonely_finally_gets_an_arc(self):
        """`lonely` routes to calm_me_down but is not in RECOVERY_TRIGGER_EMOTIONS,
        so before the phased blend it had no match step at any confidence -- it
        went straight to calm and stayed there."""
        self.assertEqual(self._served('lonely', 0.9, 'settle'), 'lonely')
        self.assertEqual(self._served('lonely', 0.9, 'close'), 'calm')

    def test_an_ambiguous_reading_is_not_matched_even_at_settle(self):
        """Matching a signal this weak would be presuming the distress."""
        for emotion in ('angry', 'depressing', 'lonely'):
            with self.subTest(emotion=emotion):
                self.assertEqual(self._served(emotion, 0.4, 'settle'), 'calm')

    def test_the_arc_never_rests_on_the_escalating_emotion(self):
        """Matching `angry` is the iso-principle's first step; ending there is
        the failure mode. No phase may land on it."""
        for phase in ('support', 'close'):
            with self.subTest(phase=phase):
                self.assertEqual(self._served('angry', 0.99, phase), 'calm')

    def test_target_weight_rises_across_the_arc(self):
        weights = [outcome_target_weight('calm_me_down', p)
                   for p in ('settle', 'support', 'close')]
        self.assertEqual(weights, sorted(weights))
        self.assertLess(weights[0], weights[-1])

    def test_an_unknown_or_absent_phase_keeps_the_flat_weight(self):
        """Callers that know nothing about session progress must not silently
        get a different blend than before the arc existed."""
        flat = OUTCOME_MODE_CONFIG['calm_me_down']['target_weight']
        for phase in (None, '', 'nonsense'):
            with self.subTest(phase=phase):
                self.assertEqual(outcome_target_weight('calm_me_down', phase), flat)

    def test_the_phase_is_reported_back(self):
        profile = apply_outcome_mode(
            self._reading('angry', 0.9), 'calm_me_down', phase='settle',
        )
        self.assertEqual(profile['outcome_phase'], 'settle')
        self.assertEqual(profile['outcome_target_weight'], 0.40)
