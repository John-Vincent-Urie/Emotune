"""Taste control: what "prefer instrumental" changes, and when LightFM is
allowed to rank at all."""

from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from api.lightfm_ranker import LightFMMusicRanker
from api.spotify.utils import _taste_instrumental_signal
from api.spotify_service import spotify_service
from users.models import FavoriteTrack


def _track(track_id, name, artist, album='Album', source='spotify_catalog'):
    return {
        'id': track_id,
        'item_type': 'track',
        'name': name,
        'artist': artist,
        'album': album,
        'uri': f'spotify:track:{track_id}',
        'spotify_url': f'https://open.spotify.com/track/{track_id}',
        'recommendation_source': source,
        'popularity': 50,
    }


class InstrumentalSignalTests(TestCase):
    """The reading is shared by both rankers, so it is tested on its own."""

    def _signal(self, blob):
        return _taste_instrumental_signal(blob, {'prefer_instrumental': True})[0]

    def test_off_by_default(self):
        self.assertEqual(
            _taste_instrumental_signal('ambient piano', {}), (0, None),
        )

    def test_reads_instrumental_music_as_instrumental(self):
        self.assertEqual(self._signal('weightless marconi union ambient'), 1)
        self.assertEqual(self._signal('peaceful piano study'), 1)

    def test_reads_a_feature_credit_as_vocal(self):
        self.assertEqual(self._signal('halik pt. 2 flow g ft. skusta clee'), -1)
        self.assertEqual(self._signal('someone like you (live) adele'), -1)

    def test_does_not_match_inside_other_words(self):
        # "Alive" is not a live recording and "Sleepless" is not sleep music.
        self.assertEqual(self._signal('alive pearl jam ten'), 0)
        self.assertEqual(self._signal('sleepless nights'), 0)
        self.assertEqual(self._signal('delivery man'), 0)

    def test_a_song_that_reads_both_ways_is_left_alone(self):
        self.assertEqual(self._signal('piano ballads feat. someone'), 0)


class InstrumentalRankingTests(TestCase):
    def test_instrumental_track_outranks_a_stronger_sourced_vocal_track(self):
        candidates = [
            _track('doc', 'Birds of a Feather', 'Billie Eilish',
                   source='music_md_playlist'),
            _track('amb', 'Weightless', 'Marconi Union', 'Ambient Transmissions'),
        ]

        without = spotify_service.rank_tracks_for_emotion(
            list(candidates), emotion='calm', confidence_band='medium', limit=5,
            taste_profile={'familiarity': 'balanced', 'prefer_instrumental': False},
        )
        with_toggle = spotify_service.rank_tracks_for_emotion(
            list(candidates), emotion='calm', confidence_band='medium', limit=5,
            taste_profile={'familiarity': 'balanced', 'prefer_instrumental': True},
        )

        self.assertEqual(without[0]['id'], 'doc')
        self.assertEqual(with_toggle[0]['id'], 'amb')

    def test_the_reason_is_reported_on_the_track(self):
        ranked = spotify_service.rank_tracks_for_emotion(
            [_track('amb', 'Weightless', 'Marconi Union', 'Ambient Transmissions')],
            emotion='calm', confidence_band='medium', limit=5,
            taste_profile={'prefer_instrumental': True},
        )
        self.assertIn('taste:instrumental', ranked[0]['emotion_alignment_reasons'])

    def test_search_asks_spotify_for_instrumental_music(self):
        queries = spotify_service._build_recommendation_queries(
            'calm', taste_profile={'prefer_instrumental': True},
        )
        instrumental_queries = [
            query for query in queries if 'instrumental' in query.lower()
        ]
        self.assertTrue(instrumental_queries)
        # Ahead of the seed songs: a request rarely gets past the first few
        # queries before its candidate slots run out.
        self.assertEqual(queries[:1], instrumental_queries[:1])

    def test_an_instrumental_request_does_not_lead_with_the_vocal_doc_list(self):
        doc_song = _track('doc', 'Kyoto', 'Phoebe Bridgers',
                          source='music_md_playlist')
        instrumental = _track('amb', 'Weightless', 'Marconi Union',
                              'Ambient Transmissions')

        without = spotify_service.blend_recommendation_groups(
            emotion='mixed',
            search_tracks=[instrumental, doc_song],
            limit=5,
            taste_profile={'familiarity': 'balanced'},
        )
        with_toggle = spotify_service.blend_recommendation_groups(
            emotion='mixed',
            search_tracks=[instrumental, doc_song],
            limit=5,
            taste_profile={'familiarity': 'balanced', 'prefer_instrumental': True},
        )

        self.assertEqual(without[0]['id'], 'doc')
        self.assertEqual(with_toggle[0]['id'], 'amb')

    def test_the_second_page_asks_for_instrumental_music_too(self):
        # The continuation stage runs its own query list, and it opens with the
        # per-emotion seed songs -- which would spend every candidate slot
        # before an instrumental query ever ran.
        queries = spotify_service._build_recommendation_queries(
            'calm',
            query_mode='continuation',
            taste_profile={'prefer_instrumental': True},
        )
        self.assertIn('instrumental', queries[0].lower())

    def test_search_is_unchanged_when_the_toggle_is_off(self):
        for query_mode in ('default', 'continuation'):
            queries = spotify_service._build_recommendation_queries(
                'calm', query_mode=query_mode,
            )
            self.assertEqual(
                [query for query in queries if 'instrumental' in query.lower()],
                [],
                query_mode,
            )


@override_settings(
    LIGHTFM_RECOMMENDER_ENABLED=True,
    LIGHTFM_RECOMMENDER_MIN_INTERACTIONS=200,
    LIGHTFM_RECOMMENDER_MIN_USER_INTERACTIONS=20,
)
class LightFMDataFloorTests(TestCase):
    """LightFM gets 40% of the blend, so it has to earn it first."""

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='floor', email='floor@example.com', password='pw12345!',
        )
        self.ranker = LightFMMusicRanker()
        self.candidates = [
            _track('track-a', 'Quiet Song', 'Artist A'),
            _track('track-b', 'Louder Song', 'Artist B'),
        ]

    def _favorites(self, count, user=None):
        for index in range(count):
            FavoriteTrack.objects.create(
                user=user or self.user,
                spotify_track_id=f'fav-{id(user)}-{index}',
                track_name=f'Song {index}',
                artist_name='Artist',
            )

    def _pick(self):
        """Rank with a model that would explode if it were ever built."""
        dataset_class = MagicMock(name='Dataset')
        with patch.object(
            self.ranker,
            '_get_lightfm_classes',
            return_value=(MagicMock(name='LightFM'), dataset_class),
        ):
            result = self.ranker.pick_playlist(
                prompt_text='winding down',
                emotion='calm',
                top_emotions=[{'emotion': 'calm', 'confidence': 1.0}],
                candidates=list(self.candidates),
                user=self.user,
                playlist_size=2,
            )
        return result, dataset_class

    def test_a_thin_corpus_never_reaches_the_model(self):
        self._favorites(5)
        result, dataset_class = self._pick()
        self.assertEqual(result['strategy'], 'heuristic_playlist')
        self.assertEqual(result['error'], 'lightfm_insufficient_interactions')
        dataset_class.assert_not_called()

    def test_a_stranger_is_not_ranked_off_other_peoples_listening(self):
        crowd = get_user_model().objects.create_user(
            username='crowd', email='crowd@example.com', password='pw12345!',
        )
        self._favorites(220, user=crowd)
        self._favorites(2)

        result, dataset_class = self._pick()
        self.assertEqual(result['strategy'], 'heuristic_playlist')
        self.assertEqual(result['error'], 'lightfm_insufficient_user_interactions')
        dataset_class.assert_not_called()


class LightFMBlendWeightTests(TestCase):
    """An undecided model must not arrive looking as opinionated as the
    emotion ranking, which min-max normalization would otherwise make it."""

    def setUp(self):
        self.ranker = LightFMMusicRanker()
        # Close on emotion, so the model's opinion is what decides the top.
        self.candidates = [
            {**_track('a', 'A', 'Artist'), 'emotion_alignment_score': 5.0},
            {**_track('b', 'B', 'Artist'), 'emotion_alignment_score': 4.9},
            {**_track('c', 'C', 'Artist'), 'emotion_alignment_score': 1.0},
        ]
        self.scores = {'a': 4.0, 'b': 9.0, 'c': 0.0}

    def _order(self, confidence):
        ranked = self.ranker._blend_scores(
            self.candidates, self.scores, confidence=confidence,
        )
        return [track['id'] for track in ranked]

    def test_a_confident_model_can_overturn_the_emotion_order(self):
        self.assertEqual(self._order(1.0)[0], 'b')

    def test_an_undecided_model_leaves_the_emotion_order_alone(self):
        self.assertEqual(self._order(0.0), ['a', 'b', 'c'])

    def test_a_missing_confidence_is_treated_as_no_confidence(self):
        self.assertEqual(self._order(None), ['a', 'b', 'c'])
