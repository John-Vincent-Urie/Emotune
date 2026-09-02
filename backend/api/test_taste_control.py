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
