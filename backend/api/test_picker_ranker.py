"""Tests for the linear music picker."""
import json
import tempfile
from pathlib import Path

from django.test import SimpleTestCase, override_settings

from api.picker_ranker import (
    DEFAULT_WEIGHTS,
    FEATURE_ORDER,
    PickerRanker,
    build_feature_rows,
)
from api.music_picker import MusicPicker


def _track(track_id, **overrides):
    track = {
        'id': track_id,
        'name': f'Song {track_id}',
        'artist': 'Artist',
        'album': 'Album',
        'spotify_url': f'https://open.spotify.com/track/{track_id}',
        'popularity': 50,
        'item_type': 'track',
    }
    track.update(overrides)
    return track


class FeatureExtractionTests(SimpleTestCase):
    def test_scores_are_normalized_within_the_candidate_set(self):
        """Weights stay portable only if the trainer and the ranker see the
        same 0-1 ranges, whatever scale the engine emitted that day."""
        rows = build_feature_rows([
            _track('a', emotion_alignment_score=2.0),
            _track('b', emotion_alignment_score=10.0),
            _track('c', emotion_alignment_score=6.0),
        ])
        values = [row['features']['emotion_alignment'] for row in rows]
        self.assertEqual(values[0], 0.0)
        self.assertEqual(values[1], 1.0)
        self.assertEqual(values[2], 0.5)

    def test_a_flat_signal_does_not_arrive_looking_decisive(self):
        rows = build_feature_rows([
            _track('a', emotion_alignment_score=4.0),
            _track('b', emotion_alignment_score=4.0),
        ])
        self.assertEqual({row['features']['emotion_alignment'] for row in rows}, {0.5})

    def test_every_declared_feature_is_produced(self):
        rows = build_feature_rows([_track('a')])
        self.assertEqual(set(rows[0]['features']), set(FEATURE_ORDER))

    def test_an_unplayable_candidate_scores_below_a_playable_one(self):
        rows = build_feature_rows([_track('a'), _track('b', spotify_url='')])
        by_id = {row['track']['id']: row['features']['availability'] for row in rows}
        self.assertGreater(by_id['a'], by_id['b'])

    def test_junk_candidates_are_dropped_rather_than_crashing(self):
        rows = build_feature_rows([None, 'nonsense', _track('a'), 42])
        self.assertEqual([row['track']['id'] for row in rows], ['a'])

    def test_a_missing_score_does_not_produce_nan(self):
        rows = build_feature_rows([_track('a', popularity=None, emotion_alignment_score='oops')])
        for value in rows[0]['features'].values():
            self.assertEqual(value, value)  # NaN != NaN


class DefaultWeightTests(SimpleTestCase):
    def setUp(self):
        self.ranker = PickerRanker()

    def test_emotion_alignment_decides_when_nothing_else_differs(self):
        ranked, version = self.ranker.rank([
            _track('low', emotion_alignment_score=1.0),
            _track('high', emotion_alignment_score=9.0),
        ])
        self.assertEqual(version, 'default')
        self.assertEqual(ranked[0]['id'], 'high')

    def test_personalization_breaks_a_tie_on_emotion(self):
        ranked, _ = self.ranker.rank([
            _track('plain', emotion_alignment_score=5.0, personalization_score=0.0),
            _track('known', emotion_alignment_score=5.0, personalization_score=4.0),
        ])
        self.assertEqual(ranked[0]['id'], 'known')

    def test_emotion_outweighs_personalization(self):
        """A well-loved track for the wrong mood must not win the pick."""
        ranked, _ = self.ranker.rank([
            _track('right_mood', emotion_alignment_score=9.0, personalization_score=0.0),
            _track('wrong_mood', emotion_alignment_score=1.0, personalization_score=9.0),
        ])
        self.assertEqual(ranked[0]['id'], 'right_mood')

    def test_ranking_annotates_score_and_features(self):
        ranked, _ = self.ranker.rank([_track('a'), _track('b')])
        self.assertIn('recommendation_score', ranked[0])
        self.assertEqual(set(ranked[0]['picker_features']), set(FEATURE_ORDER))
        self.assertIn('default_weight_ranker', ranked[0]['recommendation_reasons'])

    def test_an_empty_candidate_set_is_not_an_error(self):
        self.assertEqual(self.ranker.rank([]), ([], 'default'))

    def test_familiar_taste_promotes_a_track_the_user_already_knows(self):
        candidates = [
            _track('saved', recommendation_source='spotify_saved_tracks'),
            _track('fresh', recommendation_source='spotify_catalog'),
        ]
        familiar, _ = self.ranker.rank(candidates, taste_profile={'familiarity': 'familiar'})
        discovery, _ = self.ranker.rank(candidates, taste_profile={'familiarity': 'discovery'})
        self.assertEqual(familiar[0]['id'], 'saved')
        self.assertEqual(discovery[0]['id'], 'fresh')


class TrainedWeightTests(SimpleTestCase):
    """The artifact is data, so a bad one must never take a request down."""

    def _rank_with_artifact(self, payload, candidates):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'picker_weights.json'
            path.write_text(payload if isinstance(payload, str) else json.dumps(payload))
            with override_settings(PICKER_RANKER_WEIGHTS_PATH=str(path)):
                return PickerRanker().rank(candidates)

    def test_trained_weights_can_overturn_the_default_order(self):
        candidates = [
            _track('emotional', emotion_alignment_score=9.0, popularity=0),
            _track('popular', emotion_alignment_score=1.0, popularity=100),
        ]
        default_ranked, _ = PickerRanker().rank(candidates)
        self.assertEqual(default_ranked[0]['id'], 'emotional')

        weights = dict.fromkeys(FEATURE_ORDER, 0.0)
        weights['popularity'] = 5.0
        ranked, version = self._rank_with_artifact(
            {'version': 'test-1', 'weights': weights, 'bias': 0.0}, candidates,
        )
        self.assertEqual(ranked[0]['id'], 'popular')
        self.assertEqual(version, 'test-1')
        self.assertIn('learned_ranker', ranked[0]['recommendation_reasons'])

    def test_a_partial_artifact_falls_back_per_feature(self):
        ranked, version = self._rank_with_artifact(
            {'version': 'partial', 'weights': {'popularity': 0.5}},
            [_track('a', emotion_alignment_score=9.0), _track('b', emotion_alignment_score=1.0)],
        )
        self.assertEqual(version, 'partial')
        # emotion_alignment was absent from the artifact, so it keeps its default
        # weight and still decides the order.
        self.assertEqual(ranked[0]['id'], 'a')

    def test_corrupt_json_keeps_the_defaults(self):
        ranked, version = self._rank_with_artifact(
            '{not json at all',
            [_track('a', emotion_alignment_score=9.0), _track('b', emotion_alignment_score=1.0)],
        )
        self.assertEqual(version, 'default')
        self.assertEqual(ranked[0]['id'], 'a')

    def test_a_missing_artifact_keeps_the_defaults(self):
        with override_settings(PICKER_RANKER_WEIGHTS_PATH='/nonexistent/picker_weights.json'):
            _ranked, version = PickerRanker().rank([_track('a')])
        self.assertEqual(version, 'default')

    def test_the_ranker_can_be_switched_off(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'picker_weights.json'
            weights = dict.fromkeys(FEATURE_ORDER, 0.0)
            weights['popularity'] = 5.0
            path.write_text(json.dumps({'version': 'x', 'weights': weights}))
            with override_settings(
                PICKER_RANKER_WEIGHTS_PATH=str(path), PICKER_RANKER_ENABLED=False,
            ):
                _ranked, version = PickerRanker().rank([_track('a')])
        self.assertEqual(version, 'default')

    def test_defaults_cover_every_declared_feature(self):
        self.assertEqual(set(DEFAULT_WEIGHTS), set(FEATURE_ORDER))


class PickerIsAlwaysUsedTests(SimpleTestCase):
    """The picker must score the candidate set, never hand it back in arrival
    order -- the regression that shipped while the ranking lived behind a
    collaborative-filtering layer that never ran."""

    def test_pick_playlist_ranks_rather_than_preserving_order(self):
        picker = MusicPicker()
        result = picker.pick_playlist(
            candidates=[
                _track('weak', emotion_alignment_score=1.0),
                _track('strong', emotion_alignment_score=9.0),
            ],
            emotion='calm',
            prompt_text='winding down',
            playlist_size=2,
        )
        self.assertEqual(result['strategy'], 'linear_ranker_playlist')
        self.assertEqual(result['provider'], 'picker_ranker')
        self.assertEqual(result['selected_track']['id'], 'strong')
        # A ranked playlist is the product now, not a degraded fallback.
        self.assertFalse(result['used_fallback'])
        self.assertIsNone(result['error'])
