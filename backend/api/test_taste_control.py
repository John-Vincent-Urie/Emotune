"""Taste control behavior: balanced opens with the docs/music.md list for the
emotion, familiar replays this emotion's favorites first, discovery stays off
the static curated list."""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from api.spotify_service import spotify_service
from users.models import FavoriteTrack, PromptHistory


def _track(track_id, name, source='spotify_catalog', artist='Artist'):
    return {
        'id': track_id,
        'item_type': 'track',
        'name': name,
        'artist': artist,
        'album': 'Album',
        'image': '',
        'preview_url': None,
        'duration_ms': 180000,
        'spotify_url': f'https://open.spotify.com/track/{track_id}',
        'uri': f'spotify:track:{track_id}',
        'recommendation_source': source,
    }


CATALOG_TRACKS = [_track(f'catalog-{index}', f'Catalog {index}') for index in range(1, 6)]
# docs/music.md pairs these songs with "calm"; #1 and #3 on the list, out of
# document order so the ordering is actually exercised.
MUSIC_DOC_TRACKS = [
    _track('doc-golden-hour', 'Golden Hour', artist='JVKE'),
    _track('doc-birds', 'Birds of a Feather', artist='Billie Eilish'),
]
CURATED_TRACKS = [
    _track(f'curated-{index}', f'Curated {index}', source='curated_fallback')
    for index in range(1, 4)
]

PREDICTION = {
    'emotion': 'calm', 'confidence': 0.9,
    'all_scores': {'calm': 0.9, 'happy': 0.1},
    'top_emotions': [{'emotion': 'calm', 'confidence': 0.9}],
    'prediction_source': 'bert', 'prediction_strategy': 'bert_high_confidence',
    'confidence_band': 'high', 'confidence_margin': 0.8,
    'fallback_used': False, 'fallback_reason': None, 'needs_review': False,
    'secondary_emotion': 'happy',
}


class FavoriteEmotionTaggingTests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='taste', email='taste@example.com', password='pw12345!',
        )
        self.client.force_authenticate(user=self.user)

    def _add_favorite(self, track_id, emotion):
        return self.client.post(
            '/api/users/favorites/',
            {
                'spotify_track_id': track_id,
                'track_name': f'Song {track_id}',
                'artist_name': 'Artist',
                'emotion': emotion,
            },
            format='json',
        )

    def test_favorite_stores_the_emotion_it_was_hearted_under(self):
        response = self._add_favorite('track-1', 'calm')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()['emotion'], 'calm')
        self.assertEqual(
            FavoriteTrack.objects.get(spotify_track_id='track-1').emotion, 'calm',
        )

    def test_unknown_emotion_is_dropped_rather_than_stored(self):
        self._add_favorite('track-2', 'not-an-emotion')
        self.assertEqual(
            FavoriteTrack.objects.get(spotify_track_id='track-2').emotion, '',
        )

    def test_existing_untagged_favorite_is_backfilled_once(self):
        FavoriteTrack.objects.create(
            user=self.user,
            spotify_track_id='track-3',
            track_name='Song',
            artist_name='Artist',
        )
        self._add_favorite('track-3', 'sad')
        self.assertEqual(
            FavoriteTrack.objects.get(spotify_track_id='track-3').emotion, 'sad',
        )

        # A later heart under a different emotion keeps the original tag.
        self._add_favorite('track-3', 'happy')
        self.assertEqual(
            FavoriteTrack.objects.get(spotify_track_id='track-3').emotion, 'sad',
        )

    def test_favorites_can_be_listed_per_emotion_oldest_first(self):
        self._add_favorite('track-a', 'calm')
        self._add_favorite('track-b', 'calm')
        self._add_favorite('track-c', 'angry')

        response = self.client.get('/api/users/favorites/?emotion=calm')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [item['spotify_track_id'] for item in response.json()],
            ['track-a', 'track-b'],
        )

    def test_favorites_list_exposes_the_emotion_for_the_ui(self):
        self._add_favorite('track-d', 'romantic')
        FavoriteTrack.objects.create(
            user=self.user,
            spotify_track_id='track-e',
            track_name='Untagged',
            artist_name='Artist',
        )

        payload = {
            item['spotify_track_id']: item['emotion']
            for item in self.client.get('/api/users/favorites/').json()
        }
        self.assertEqual(payload['track-d'], 'romantic')
        self.assertEqual(payload['track-e'], '')


class TasteControlPlaylistTests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='taste2', email='taste2@example.com', password='pw12345!',
        )
        self.client.force_authenticate(user=self.user)

    def _analyze(self, familiarity, tracks=None):
        """The progressive first response: one track, chosen to play now."""
        with self._spotify_returning(tracks):
            response = self.client.post(
                '/api/analyze/',
                {
                    'text': 'winding down',
                    'taste_profile': {'familiarity': familiarity},
                },
                format='json',
            )
        self.assertEqual(response.status_code, 200)
        return response.json()

    def _full_playlist(self, familiarity, tracks=None):
        """The second response: the whole playlist behind the first track."""
        body = self._analyze(familiarity, tracks=tracks)
        self.assertTrue(body['continuation_token'])
        with self._spotify_returning(tracks):
            response = self.client.post(
                '/api/recommendation-playlist/',
                {'continuation_token': body['continuation_token']},
                format='json',
            )
        self.assertEqual(response.status_code, 200)
        return response.json()

    def _spotify_returning(self, tracks=None):
        classifier_patch = patch('api.views.get_classifier')
        spotify_patch = patch(
            'api.views.spotify_service.get_recommendations_with_details'
        )

        class _Patches:
            def __enter__(self):
                classifier_patch.start().return_value.predict.return_value = PREDICTION
                spotify_patch.start().return_value = {
                    'tracks': list(CATALOG_TRACKS if tracks is None else tracks),
                    'source': 'spotify',
                    'used_fallback': False,
                    'fallback_reason': None,
                    'personalized': False,
                    'personalization_sources': [],
                    'personalization_missing_scopes': [],
                }
                return self

            def __exit__(self, *exc_info):
                patch.stopall()
                return False

        return _Patches()

    def _favorite(self, track_id, emotion):
        return FavoriteTrack.objects.create(
            user=self.user,
            spotify_track_id=track_id,
            track_name=f'Loved {track_id}',
            artist_name='Loved Artist',
            emotion=emotion,
        )

    def test_familiar_opens_with_the_first_favorite_for_that_emotion(self):
        self._favorite('fav-first', 'calm')
        self._favorite('fav-second', 'calm')
        self._favorite('fav-other-emotion', 'angry')

        body = self._analyze('familiar')
        self.assertEqual(body['tracks'][0]['id'], 'fav-first')
        self.assertEqual(body['selected_track']['id'], 'fav-first')
        self.assertEqual(body['selected_track_source'], 'favorite_track')
        self.assertNotIn(
            'fav-other-emotion',
            [track['id'] for track in body['tracks']],
        )

    def test_familiar_with_no_favorites_for_the_emotion_keeps_the_ranking(self):
        self._favorite('fav-angry', 'angry')
        body = self._analyze('familiar')
        self.assertTrue(body['tracks'])
        self.assertNotEqual(body['tracks'][0]['id'], 'fav-angry')

    def test_familiar_playlist_still_recommends_new_songs(self):
        # More favorites than the playlist has room for: the lane must still
        # hand back music the user has not heard, or it stops recommending.
        for index in range(1, 8):
            self._favorite(f'fav-{index}', 'calm')

        track_ids = [
            track['id'] for track in self._full_playlist('familiar')['tracks']
        ]
        favorites = [track_id for track_id in track_ids if track_id.startswith('fav-')]
        new_songs = [
            track_id for track_id in track_ids if not track_id.startswith('fav-')
        ]

        self.assertTrue(new_songs)
        self.assertLessEqual(len(favorites), max(len(track_ids) // 2, 1))

    def test_familiar_playlist_still_opens_with_the_first_favorite(self):
        for index in range(1, 8):
            self._favorite(f'fav-{index}', 'calm')

        body = self._full_playlist('familiar')
        self.assertEqual(body['tracks'][0]['id'], 'fav-1')
        self.assertEqual(body['selected_track']['id'], 'fav-1')

    def test_balanced_plays_the_music_doc_song_first(self):
        # The first stage only asks Spotify for a handful of candidates, so the
        # fixture stays inside that window.
        body = self._analyze('balanced', tracks=CATALOG_TRACKS[:2] + MUSIC_DOC_TRACKS)
        self.assertEqual(body['selected_track']['id'], 'doc-birds')
        self.assertEqual([track['id'] for track in body['tracks']], ['doc-birds'])

    def test_balanced_playlist_opens_in_document_order(self):
        body = self._full_playlist('balanced', tracks=CATALOG_TRACKS + MUSIC_DOC_TRACKS)
        self.assertEqual(
            [track['id'] for track in body['tracks']][:2],
            ['doc-birds', 'doc-golden-hour'],
        )

    def test_balanced_playlist_keeps_the_ranked_picks_behind_the_doc_songs(self):
        body = self._full_playlist('balanced', tracks=CATALOG_TRACKS + MUSIC_DOC_TRACKS)
        self.assertEqual(
            sorted(track['id'] for track in body['tracks']),
            sorted(
                track['id'] for track in CATALOG_TRACKS + MUSIC_DOC_TRACKS
            ),
        )

    def test_balanced_flags_the_doc_songs_for_the_app(self):
        body = self._full_playlist('balanced', tracks=CATALOG_TRACKS + MUSIC_DOC_TRACKS)
        flagged = {
            track['id'] for track in body['tracks']
            if track.get('is_music_doc_pick')
        }
        self.assertEqual(flagged, {'doc-birds', 'doc-golden-hour'})

    def test_balanced_keeps_the_ranking_when_no_doc_song_was_found(self):
        body = self._full_playlist('balanced')
        self.assertEqual(
            [track['id'] for track in body['tracks']],
            [track['id'] for track in CATALOG_TRACKS],
        )

    def test_familiar_still_beats_the_music_doc_list(self):
        self._favorite('fav-first', 'calm')
        body = self._full_playlist('familiar', tracks=CATALOG_TRACKS + MUSIC_DOC_TRACKS)
        self.assertEqual(body['tracks'][0]['id'], 'fav-first')

    def test_balanced_does_not_pull_favorites_forward(self):
        self._favorite('fav-first', 'calm')
        body = self._analyze('balanced')
        self.assertNotEqual(body['tracks'][0]['id'], 'fav-first')

    def test_discovery_drops_the_static_curated_tracks(self):
        body = self._analyze('discovery', tracks=CURATED_TRACKS + CATALOG_TRACKS)
        sources = {
            track.get('recommendation_source') for track in body['tracks']
        }
        self.assertNotIn('curated_fallback', sources)
        self.assertTrue(body['tracks'])

    def test_discovery_keeps_curated_tracks_when_they_are_all_there_is(self):
        body = self._analyze('discovery', tracks=CURATED_TRACKS)
        self.assertTrue(body['tracks'])

    def test_favorites_lead_is_recorded_in_history(self):
        self._favorite('fav-first', 'calm')
        self._analyze('familiar')
        history = PromptHistory.objects.filter(user=self.user).first()
        self.assertEqual(
            history.music_picker_data['playlist_track_ids'][0], 'fav-first',
        )


class BlendTasteControlTests(APITestCase):
    """The blender is shared by every recommendation path, including the ones
    that never reach Spotify."""

    def test_discovery_blend_excludes_curated_candidates(self):
        blended = spotify_service.blend_recommendation_groups(
            emotion='calm',
            search_tracks=list(CATALOG_TRACKS),
            fallback_tracks=list(CURATED_TRACKS),
            limit=10,
            taste_profile={'familiarity': 'discovery'},
        )
        self.assertTrue(blended)
        self.assertNotIn(
            'curated_fallback',
            {track.get('recommendation_source') for track in blended},
        )

    def test_discovery_blend_varies_the_order(self):
        orders = set()
        for _ in range(12):
            blended = spotify_service.blend_recommendation_groups(
                emotion='calm',
                search_tracks=list(CATALOG_TRACKS),
                limit=5,
                taste_profile={'familiarity': 'discovery'},
            )
            orders.add(tuple(track['id'] for track in blended))
        self.assertGreater(len(orders), 1)

    def test_balanced_blend_leads_with_the_music_doc_songs(self):
        blended = spotify_service.blend_recommendation_groups(
            emotion='calm',
            search_tracks=list(CATALOG_TRACKS) + list(MUSIC_DOC_TRACKS),
            limit=10,
            taste_profile={'familiarity': 'balanced'},
        )
        self.assertEqual(
            [track['id'] for track in blended][:2],
            ['doc-birds', 'doc-golden-hour'],
        )

    def test_balanced_blend_matches_doc_songs_by_seed_metadata(self):
        renamed = dict(MUSIC_DOC_TRACKS[1])
        renamed['name'] = 'Birds of a Feather (Live)'
        renamed['playlist_seed_track'] = 'Birds of a Feather'
        renamed['playlist_seed_artist'] = 'Billie Eilish'
        blended = spotify_service.blend_recommendation_groups(
            emotion='calm',
            search_tracks=list(CATALOG_TRACKS) + [renamed],
            limit=10,
            taste_profile={'familiarity': 'balanced'},
        )
        self.assertEqual(blended[0]['id'], 'doc-birds')

    def test_balanced_blend_is_deterministic(self):
        orders = {
            tuple(
                track['id']
                for track in spotify_service.blend_recommendation_groups(
                    emotion='calm',
                    search_tracks=list(CATALOG_TRACKS),
                    limit=5,
                    taste_profile={'familiarity': 'balanced'},
                )
            )
            for _ in range(5)
        }
        self.assertEqual(len(orders), 1)

    def test_discovery_fallback_builder_skips_the_curated_list(self):
        user = get_user_model().objects.create_user(
            username='blend', email='blend@example.com', password='pw12345!',
        )
        FavoriteTrack.objects.create(
            user=user,
            spotify_track_id='fav-1',
            track_name='Loved',
            artist_name='Artist',
            emotion='calm',
        )
        tracks = spotify_service._build_fallback_tracks(
            'calm',
            user=user,
            limit=10,
            taste_profile={'familiarity': 'discovery'},
        )
        self.assertTrue(tracks)
        self.assertNotIn(
            'curated_fallback',
            {track.get('recommendation_source') for track in tracks},
        )

    def test_balanced_fallback_builder_still_tops_up_with_curated(self):
        tracks = spotify_service._build_fallback_tracks('calm', limit=10)
        self.assertIn(
            'curated_fallback',
            {track.get('recommendation_source') for track in tracks},
        )

    def test_familiar_blend_caps_the_favorites_at_half_the_playlist(self):
        user = get_user_model().objects.create_user(
            username='blendfam', email='blendfam@example.com', password='pw12345!',
        )
        for index in range(1, 9):
            FavoriteTrack.objects.create(
                user=user,
                spotify_track_id=f'fav-{index}',
                track_name=f'Loved {index}',
                artist_name='Artist',
                emotion='calm',
            )

        blended = spotify_service.blend_recommendation_groups(
            emotion='calm',
            search_tracks=list(CATALOG_TRACKS),
            limit=6,
            taste_profile={'familiarity': 'familiar'},
            user=user,
        )
        track_ids = [str(track.get('id') or '') for track in blended]
        favorites = [track_id for track_id in track_ids if track_id.startswith('fav-')]

        self.assertLessEqual(len(favorites), 3)
        self.assertTrue(
            [track_id for track_id in track_ids if not track_id.startswith('fav-')],
        )


class DocumentLaneWeightTests(APITestCase):
    """The docs/music.md lane is boosted twice -- a 3.4 source weight (against
    1.2 for the catalog) and a 3.0 selection reason, so 5.2 in total. Taste
    settings that opt out of the lane have to shed both, or a static list keeps
    outranking the catalog music the setting asked for.
    """

    # The document lane leading by roughly this much is the default, and the
    # point of the opt-outs is to remove it.
    LANE_ADVANTAGE = 5.2

    def _gap(self, taste_profile=None):
        """Rank one music.md track against one catalog track; return the gap.

        Positive means the document track outranks the catalog track.
        """
        doc_track = {
            **_track('doc-1', 'Golden Hour', source='music_md_playlist', artist='JVKE'),
            'selection_reasons': ['music_md_playlist_seed'],
        }
        catalog_track = _track('catalog-1', 'Some Other Song')

        ranked = spotify_service.rank_tracks_for_emotion(
            [doc_track, catalog_track],
            emotion='calm',
            limit=10,
            taste_profile=taste_profile,
        )
        by_id = {track['id']: track for track in ranked}
        return (
            by_id['doc-1']['emotion_alignment_score']
            - by_id['catalog-1']['emotion_alignment_score']
        )

    def test_the_document_lane_leads_by_default(self):
        self.assertGreaterEqual(self._gap(), self.LANE_ADVANTAGE)

    def test_discovery_strips_the_document_lane_advantage(self):
        """A cached music.md track used to arrive 5.2 ahead of the catalog even
        under discovery, which is the opposite of what the setting asked for."""
        default_gap = self._gap()
        discovery_gap = self._gap({'familiarity': 'discovery'})

        self.assertGreaterEqual(default_gap - discovery_gap, self.LANE_ADVANTAGE)
        self.assertLessEqual(discovery_gap, 0.0)

    def test_instrumental_strips_it_too(self):
        """This opt-out already existed, but shed only the source weight."""
        gap = self._gap({'prefer_instrumental': True})

        self.assertGreaterEqual(self._gap() - gap, self.LANE_ADVANTAGE)
        self.assertLessEqual(gap, 0.1)

    def test_balanced_is_unchanged(self):
        self.assertAlmostEqual(
            self._gap({'familiarity': 'balanced'}), self._gap(), places=3,
        )

    def test_familiar_still_keeps_the_document_lane(self):
        """Only discovery and instrumental opt out; familiar must not regress."""
        self.assertGreaterEqual(
            self._gap({'familiarity': 'familiar'}), self.LANE_ADVANTAGE,
        )

    def test_discovery_ranks_a_document_track_below_the_catalog(self):
        """Two tracks the emotion scoring cannot separate on their own -- same
        keyword, different titles so neither is deduplicated. Under discovery
        the catalog track has to come first."""
        doc_track = {
            **_track(
                'doc-1', 'Calm Song One', source='music_md_playlist', artist='Artist One',
            ),
            'selection_reasons': ['music_md_playlist_seed'],
        }
        catalog_track = _track('catalog-1', 'Calm Song Two', artist='Artist Two')

        ranked = spotify_service.rank_tracks_for_emotion(
            [doc_track, catalog_track],
            emotion='calm',
            limit=10,
            taste_profile={'familiarity': 'discovery'},
        )
        self.assertEqual(ranked[0]['id'], 'catalog-1')
