"""
Local LightFM-based music ranker for EmoTune.

This module replaces the network LLM ranking step with a local hybrid
recommender. Spotify candidate retrieval still happens elsewhere; this ranker
only reorders the candidate set using historical interactions, user features,
item features, and the current emotion context.
"""
from collections import Counter, defaultdict
import logging
import platform
import re

import numpy as np
from django.conf import settings

from users.models import FavoriteTrack, ListeningSession, PromptHistory, UserPreference

logger = logging.getLogger(__name__)

SAFE_TRACK_DEFAULT_LIMIT = 20


class LightFMMusicRanker:
    def __init__(self):
        self.enabled = bool(getattr(settings, 'LIGHTFM_RECOMMENDER_ENABLED', True))
        self.runtime_block_reason = None
        self.allow_windows = bool(
            getattr(settings, 'LIGHTFM_RECOMMENDER_ALLOW_WINDOWS', False)
        )
        self.running_on_windows = platform.system().lower().startswith('windows')
        if self.enabled and self.running_on_windows and not self.allow_windows:
            self.enabled = False
            self.runtime_block_reason = 'lightfm_windows_disabled'
            logger.warning(
                "LightFM is disabled on Windows to avoid native runtime crashes. "
                "Enable LIGHTFM_RECOMMENDER_ALLOW_WINDOWS only if you are sure the "
                "local LightFM build is stable on this machine."
            )
        self.loss = self._normalize_loss(
            getattr(settings, 'LIGHTFM_RECOMMENDER_LOSS', 'warp')
        )
        self.no_components = max(
            int(getattr(settings, 'LIGHTFM_RECOMMENDER_COMPONENTS', 16) or 16),
            4,
        )
        self.epochs = max(
            int(getattr(settings, 'LIGHTFM_RECOMMENDER_EPOCHS', 20) or 20),
            1,
        )
        self.item_alpha = max(
            float(getattr(settings, 'LIGHTFM_RECOMMENDER_ITEM_ALPHA', 1e-6) or 1e-6),
            0.0,
        )
        self.user_alpha = max(
            float(getattr(settings, 'LIGHTFM_RECOMMENDER_USER_ALPHA', 1e-6) or 1e-6),
            0.0,
        )
        self.min_interactions = max(
            int(getattr(settings, 'LIGHTFM_RECOMMENDER_MIN_INTERACTIONS', 3) or 3),
            1,
        )

    def pick_track(
        self,
        *,
        prompt_text,
        emotion,
        top_emotions,
        all_scores=None,
        confidence_band=None,
        confidence_margin=None,
        candidates,
        preferred_artists=None,
        user=None,
        taste_profile=None,
    ):
        playlist_result = self.pick_playlist(
            prompt_text=prompt_text,
            emotion=emotion,
            top_emotions=top_emotions,
            all_scores=all_scores,
            confidence_band=confidence_band,
            confidence_margin=confidence_margin,
            candidates=candidates,
            preferred_artists=preferred_artists,
            user=user,
            playlist_size=1,
            taste_profile=taste_profile,
        )
        return {
            'ok': bool(playlist_result.get('ok')),
            'strategy': playlist_result.get('strategy'),
            'selected_track': playlist_result.get('selected_track'),
            'reason': playlist_result.get('reason'),
            'confidence': playlist_result.get('confidence'),
            'provider': playlist_result.get('provider'),
            'model': playlist_result.get('model'),
            'used_fallback': bool(playlist_result.get('used_fallback', True)),
            'error': playlist_result.get('error'),
            'candidates': playlist_result.get('candidates', []),
        }

    def pick_playlist(
        self,
        *,
        prompt_text,
        emotion,
        top_emotions,
        all_scores=None,
        confidence_band=None,
        confidence_margin=None,
        candidates,
        preferred_artists=None,
        user=None,
        playlist_size=None,
        taste_profile=None,
    ):
        resolved_size = max(int(playlist_size or SAFE_TRACK_DEFAULT_LIMIT), 1)
        normalized_candidates = self._normalize_candidates(candidates)
        fallback_result = self._heuristic_playlist_result(
            candidates=normalized_candidates,
            emotion=emotion,
            prompt_text=prompt_text,
            playlist_size=resolved_size,
            error='lightfm_unavailable',
        )
        if not normalized_candidates:
            return fallback_result

        if not self.enabled:
            fallback_result['error'] = self.runtime_block_reason or 'lightfm_disabled'
            return fallback_result

        try:
            ranking_result = self._rank_candidates(
                user=user,
                emotion=emotion,
                top_emotions=top_emotions,
                confidence_band=confidence_band,
                candidates=normalized_candidates,
                preferred_artists=preferred_artists or [],
                taste_profile=taste_profile,
            )
        except ImportError as error:
            logger.warning("LightFM is not installed: %s", error)
            fallback_result['error'] = 'lightfm_not_installed'
            return fallback_result
        except Exception:
            logger.exception("LightFM ranking failed for emotion %r", emotion)
            fallback_result['error'] = 'lightfm_runtime_error'
            return fallback_result

        if not ranking_result.get('ok'):
            fallback_result['error'] = ranking_result.get('error') or 'lightfm_not_ready'
            return fallback_result

        ranked_tracks = (ranking_result.get('tracks') or [])[:resolved_size]
        selected_track = ranked_tracks[0] if ranked_tracks else None
        return {
            'ok': bool(ranked_tracks),
            'strategy': 'lightfm_playlist',
            'tracks': ranked_tracks,
            'selected_track': selected_track,
            'playlist_track_ids': [
                str(track.get('id'))
                for track in ranked_tracks
                if str(track.get('id') or '').strip()
            ],
            'reason': ranking_result.get('reason'),
            'confidence': ranking_result.get('confidence'),
            'provider': 'lightfm',
            'model': self.loss,
            'used_fallback': False,
            'error': None,
            'candidates': normalized_candidates[: min(len(normalized_candidates), 12)],
            'intent': 'track' if resolved_size == 1 else 'playlist',
            'artist_name': (
                str(selected_track.get('artist') or '').strip() or None
                if isinstance(selected_track, dict)
                else None
            ),
            'track_name': (
                str(selected_track.get('name') or '').strip() or None
                if isinstance(selected_track, dict)
                else None
            ),
            'playlist_category': self._playlist_category(emotion, top_emotions),
            'confirmation': self._build_confirmation(selected_track, emotion),
        }

    def _rank_candidates(
        self,
        *,
        user,
        emotion,
        top_emotions,
        confidence_band,
        candidates,
        preferred_artists,
        taste_profile,
    ):
        LightFM, Dataset = self._get_lightfm_classes()
        corpus = self._build_training_corpus(
            user=user,
            emotion=emotion,
            top_emotions=top_emotions,
            confidence_band=confidence_band,
            candidates=candidates,
            preferred_artists=preferred_artists,
        )
        interactions_by_pair = corpus['interactions']
        if len(interactions_by_pair) < self.min_interactions:
            return {
                'ok': False,
                'error': 'lightfm_insufficient_interactions',
            }

        dataset = Dataset()
        dataset.fit(
            sorted(corpus['user_ids']),
            sorted(corpus['item_ids']),
            user_features=sorted(corpus['all_user_features']),
            item_features=sorted(corpus['all_item_features']),
        )

        interactions, weights = dataset.build_interactions(
            (
                user_id,
                item_id,
                float(weight),
            )
            for (user_id, item_id), weight in interactions_by_pair.items()
        )

        if interactions.nnz < self.min_interactions:
            return {
                'ok': False,
                'error': 'lightfm_sparse_interactions',
            }

        user_features = dataset.build_user_features(
            (
                user_id,
                sorted(features),
            )
            for user_id, features in corpus['user_feature_map'].items()
            if features
        )
        item_features = dataset.build_item_features(
            (
                item_id,
                sorted(features),
            )
            for item_id, features in corpus['item_feature_map'].items()
            if features
        )

        model = LightFM(
            loss=self.loss,
            no_components=self.no_components,
            item_alpha=self.item_alpha,
            user_alpha=self.user_alpha,
            random_state=42,
        )
        model.fit(
            interactions,
            sample_weight=weights,
            user_features=user_features,
            item_features=item_features,
            epochs=self.epochs,
            num_threads=1,
        )

        user_id_map, _user_feature_map, item_id_map, _item_feature_map = dataset.mapping()
        request_user_id = corpus['request_user_id']
        if request_user_id not in user_id_map:
            return {
                'ok': False,
                'error': 'lightfm_request_user_missing',
            }

        candidate_ids = [
            str(track.get('id') or '').strip()
            for track in candidates
            if str(track.get('id') or '').strip() in item_id_map
        ]
        if not candidate_ids:
            return {
                'ok': False,
                'error': 'lightfm_candidate_mapping_missing',
            }

        candidate_indexes = np.array(
            [item_id_map[item_id] for item_id in candidate_ids],
            dtype=np.int32,
        )
        prediction_scores = model.predict(
            user_ids=user_id_map[request_user_id],
            item_ids=candidate_indexes,
            user_features=user_features,
            item_features=item_features,
            num_threads=1,
        )
        lightfm_scores = {
            item_id: float(score)
            for item_id, score in zip(candidate_ids, prediction_scores)
        }
        ranked_tracks = self._blend_scores(
            candidates,
            lightfm_scores,
            taste_profile=taste_profile,
        )
        confidence = self._ranking_confidence(lightfm_scores)
        return {
            'ok': True,
            'tracks': ranked_tracks,
            'reason': (
                'LightFM re-ranked Spotify candidates using favorites, listening '
                'history, emotion context, and track metadata.'
            ),
            'confidence': confidence,
        }

    def _build_training_corpus(
        self,
        *,
        user,
        emotion,
        top_emotions,
        confidence_band,
        candidates,
        preferred_artists,
    ):
        request_user_id = self._request_user_id(user, emotion)
        user_ids = {request_user_id}
        item_ids = set()
        all_user_features = set()
        all_item_features = set()
        user_feature_map = defaultdict(set)
        item_feature_map = defaultdict(set)
        interactions = defaultdict(float)
        user_emotion_counts = defaultdict(Counter)

        def add_user_feature(user_id, feature):
            user_id = str(user_id or '').strip()
            if not user_id:
                return
            feature = self._feature_token(feature)
            if not feature:
                return
            user_ids.add(user_id)
            user_feature_map[user_id].add(feature)
            all_user_features.add(feature)

        def add_item_features(item_id, features):
            item_id = str(item_id or '').strip()
            if not item_id:
                return
            item_ids.add(item_id)
            for feature in features:
                token = self._feature_token(feature)
                if not token:
                    continue
                item_feature_map[item_id].add(token)
                all_item_features.add(token)

        def record_interaction(user_id, item_id, weight):
            user_id = str(user_id or '').strip()
            item_id = str(item_id or '').strip()
            if not user_id or not item_id:
                return
            user_ids.add(user_id)
            item_ids.add(item_id)
            interactions[(user_id, item_id)] += max(float(weight or 0.0), 0.0)

        for candidate in candidates:
            track_id = str(candidate.get('id') or '').strip()
            if not track_id:
                continue
            add_item_features(
                track_id,
                self._candidate_item_features(candidate),
            )

        for track in FavoriteTrack.objects.select_related('user').all():
            user_id = self._user_id(track.user_id)
            artist_feature = self._artist_feature(track.artist_name)
            add_user_feature(user_id, artist_feature)
            add_item_features(
                track.spotify_track_id,
                {
                    artist_feature,
                    'source:favorite_track',
                    'mood:favorited',
                },
            )
            record_interaction(user_id, track.spotify_track_id, 3.0)

        for preference in UserPreference.objects.select_related('user').all():
            user_id = self._user_id(preference.user_id)
            artist_feature = self._artist_feature(preference.artist_name)
            emotion_feature = self._emotion_feature(preference.emotion)
            add_user_feature(user_id, artist_feature)
            add_user_feature(user_id, f'user_pref:{emotion_feature}')
            add_item_features(
                preference.spotify_track_id,
                {
                    artist_feature,
                    emotion_feature,
                    'source:user_preference',
                },
            )
            user_emotion_counts[user_id][emotion_feature] += max(preference.play_count or 1, 1)
            record_interaction(
                user_id,
                preference.spotify_track_id,
                1.0
                + min(max(preference.play_count or 0, 0), 10) * 0.35
                + min(max(preference.total_listen_time or 0, 0) / 900.0, 1.5),
            )

        for session in ListeningSession.objects.select_related('user', 'prompt_history').all():
            if not self._history_allows_learning(getattr(session, 'prompt_history', None)):
                continue
            user_id = self._user_id(session.user_id)
            emotion_feature = self._emotion_feature(
                getattr(session.prompt_history, 'detected_emotion', '')
            )
            add_user_feature(user_id, emotion_feature)
            add_item_features(
                session.spotify_track_id,
                {
                    emotion_feature,
                    self._track_text_feature('title', session.track_name),
                    'source:listening_session',
                },
            )
            if emotion_feature:
                user_emotion_counts[user_id][emotion_feature] += 1
            record_interaction(
                user_id,
                session.spotify_track_id,
                0.8
                + min(max(session.listen_duration or 0, 0) / 180.0, 1.5)
                + (0.8 if session.completed else 0.0),
            )

        for history in PromptHistory.objects.select_related('user').all():
            if not self._history_allows_learning(history):
                continue
            user_id = self._user_id(history.user_id)
            emotion_feature = self._emotion_feature(history.detected_emotion)
            if emotion_feature:
                add_user_feature(user_id, emotion_feature)
                user_emotion_counts[user_id][emotion_feature] += 1

            selected_track = self._selected_history_track(history)
            if not selected_track:
                continue

            track_id = str(selected_track.get('id') or '').strip()
            if not track_id:
                continue

            add_item_features(
                track_id,
                {
                    emotion_feature,
                    self._artist_feature(selected_track.get('artist')),
                    self._source_feature(selected_track.get('recommendation_source')),
                },
            )
            if history.session_duration or history.felt_better_response is True:
                record_interaction(
                    user_id,
                    track_id,
                    0.9
                    + min(max(history.session_duration or 0, 0) / 600.0, 1.5)
                    + (0.9 if history.felt_better_response is True else 0.0),
                )

        for user_id, counter in user_emotion_counts.items():
            for emotion_feature, _count in counter.most_common(2):
                add_user_feature(user_id, f'history:{emotion_feature}')

        for preferred_artist in preferred_artists or []:
            add_user_feature(request_user_id, self._artist_feature(preferred_artist))

        for item in top_emotions or []:
            if not isinstance(item, dict):
                continue
            emotion_name = self._emotion_feature(item.get('emotion'))
            if emotion_name:
                add_user_feature(request_user_id, f'context:{emotion_name}')

        add_user_feature(request_user_id, self._emotion_feature(emotion))
        add_user_feature(request_user_id, f'confidence:{str(confidence_band or "high").strip().lower()}')

        return {
            'request_user_id': request_user_id,
            'user_ids': user_ids,
            'item_ids': item_ids,
            'user_feature_map': user_feature_map,
            'item_feature_map': item_feature_map,
            'all_user_features': all_user_features,
            'all_item_features': all_item_features,
            'interactions': interactions,
        }

    def _blend_scores(self, candidates, lightfm_scores, *, taste_profile=None):
        emotion_scores = {
            str(track.get('id') or '').strip(): float(track.get('emotion_alignment_score', 0.0) or 0.0)
            for track in candidates
        }
        personalization_scores = {
            str(track.get('id') or '').strip(): float(track.get('personalization_score', 0.0) or 0.0)
            for track in candidates
        }
        popularity_scores = {
            str(track.get('id') or '').strip(): float(track.get('popularity', 0.0) or 0.0)
            for track in candidates
        }

        normalized_lightfm = self._normalize_score_map(lightfm_scores, default=0.5)
        normalized_emotion = self._normalize_score_map(emotion_scores, default=0.5)
        normalized_personal = self._normalize_score_map(personalization_scores, default=0.0)
        normalized_popularity = self._normalize_score_map(popularity_scores, default=0.0)
        normalized_taste = self._normalize_taste_profile(taste_profile)

        familiarity = normalized_taste.get('familiarity')
        if familiarity == 'familiar':
            emotion_weight = 0.34
            lightfm_weight = 0.42
            personalization_weight = 0.16
        elif familiarity == 'discovery':
            emotion_weight = 0.44
            lightfm_weight = 0.32
            personalization_weight = 0.08
        else:
            emotion_weight = 0.40
            lightfm_weight = 0.40
            personalization_weight = 0.10

        ranked = []
        for index, raw_track in enumerate(candidates):
            track = dict(raw_track)
            track_id = str(track.get('id') or '').strip()
            availability_score = 1.0 if str(track.get('spotify_url') or '').strip() else 0.5
            discovery_bonus = self._discovery_bonus(track, normalized_taste)
            instrumental_bonus, instrumental_reason = self._instrumental_bonus(track, normalized_taste)
            final_score = (
                normalized_emotion.get(track_id, 0.5) * emotion_weight
                + normalized_lightfm.get(track_id, 0.5) * lightfm_weight
                + normalized_personal.get(track_id, 0.0) * personalization_weight
                + (
                    (availability_score * 0.7)
                    + (normalized_popularity.get(track_id, 0.0) * 0.3)
                ) * 0.10
                + discovery_bonus
                + instrumental_bonus
            )
            reasons = list(track.get('emotion_alignment_reasons') or [])
            if track_id in lightfm_scores:
                reasons.append('lightfm_personalized_ranking')
            if familiarity == 'familiar':
                reasons.append('taste:familiar')
            elif familiarity == 'discovery':
                reasons.append('taste:discovery')
            if instrumental_reason:
                reasons.append(instrumental_reason)
            track['lightfm_score'] = round(float(lightfm_scores.get(track_id, 0.0) or 0.0), 5)
            track['recommendation_score'] = round(final_score, 5)
            track['recommendation_reasons'] = self._unique_list(reasons)
            ranked.append(track)

        ranked.sort(
            key=lambda item: (
                -float(item.get('recommendation_score', 0.0)),
                -float(item.get('emotion_alignment_score', 0.0)),
                -float(item.get('personalization_score', 0.0)),
                -float(item.get('popularity', 0.0) or 0.0),
                str(item.get('name') or '').lower(),
            )
        )
        return ranked

    def _history_allows_learning(self, history):
        if history is None:
            return True
        music_picker_data = (
            history.music_picker_data
            if isinstance(history.music_picker_data, dict)
            else {}
        )
        personalization = music_picker_data.get('personalization')
        return not (isinstance(personalization, dict) and personalization.get('train_session') is False)

    def _normalize_taste_profile(self, taste_profile):
        working = taste_profile if isinstance(taste_profile, dict) else {}
        familiarity = str(working.get('familiarity') or 'balanced').strip().lower()
        if familiarity not in {'balanced', 'familiar', 'discovery'}:
            familiarity = 'balanced'
        return {
            'familiarity': familiarity,
            'prefer_instrumental': bool(working.get('prefer_instrumental', False)),
        }

    def _discovery_bonus(self, track, taste_profile):
        familiarity = taste_profile.get('familiarity')
        source = str(track.get('recommendation_source') or '').strip().lower()
        if familiarity == 'discovery':
            if source in {'spotify_catalog', 'curated_fallback'}:
                return 0.08
            if source in {'spotify_top_tracks', 'spotify_saved_tracks', 'user_preference'}:
                return -0.06
        if familiarity == 'familiar':
            if source in {'spotify_top_tracks', 'spotify_saved_tracks', 'user_preference', 'favorite_track'}:
                return 0.08
            if source in {'spotify_catalog', 'curated_fallback'}:
                return -0.05
        return 0.0

    def _instrumental_bonus(self, track, taste_profile):
        if not taste_profile.get('prefer_instrumental'):
            return 0.0, None

        text_blob = ' '.join([
            str(track.get('name') or '').strip().lower(),
            str(track.get('artist') or '').strip().lower(),
            str(track.get('album') or '').strip().lower(),
        ])
        instrumental_terms = (
            'instrumental',
            'ambient',
            'lofi',
            'lo-fi',
            'piano',
            'study',
            'meditation',
            'sleep',
            'focus',
            'classical',
            'soundtrack',
        )
        vocal_terms = (
            'feat.',
            'featuring',
            'karaoke',
            'remix',
            'version',
            'live',
        )

        bonus = 0.0
        if any(term in text_blob for term in instrumental_terms):
            bonus += 0.12
        if any(term in text_blob for term in vocal_terms):
            bonus -= 0.06
        if bonus > 0:
            return bonus, 'taste:instrumental'
        if bonus < 0:
            return bonus, 'taste:less_instrumental_fit'
        return 0.0, None

    def _heuristic_playlist_result(
        self,
        *,
        candidates,
        emotion,
        prompt_text,
        playlist_size,
        error,
    ):
        fallback_tracks = list(candidates[:playlist_size])
        selected_track = fallback_tracks[0] if fallback_tracks else None
        return {
            'ok': bool(fallback_tracks),
            'strategy': 'heuristic_playlist',
            'tracks': fallback_tracks,
            'selected_track': selected_track,
            'playlist_track_ids': [
                str(track.get('id'))
                for track in fallback_tracks
                if str(track.get('id') or '').strip()
            ],
            'reason': None,
            'confidence': None,
            'provider': 'disabled',
            'model': None,
            'used_fallback': True,
            'error': error,
            'candidates': list(candidates[: min(len(candidates), 12)]),
            'intent': 'track' if playlist_size == 1 else 'playlist',
            'artist_name': (
                str(selected_track.get('artist') or '').strip() or None
                if isinstance(selected_track, dict)
                else None
            ),
            'track_name': (
                str(selected_track.get('name') or '').strip() or None
                if isinstance(selected_track, dict)
                else None
            ),
            'playlist_category': self._playlist_category(emotion, []),
            'confirmation': self._build_confirmation(selected_track, emotion, prompt_text=prompt_text),
        }

    def _normalize_candidates(self, candidates):
        normalized = []
        seen_ids = set()
        for candidate in candidates or []:
            if not isinstance(candidate, dict):
                continue
            track_id = str(candidate.get('id') or '').strip()
            if not track_id or track_id in seen_ids:
                continue
            seen_ids.add(track_id)
            normalized.append(dict(candidate))
        return normalized

    def _normalize_score_map(self, score_map, *, default=0.0):
        cleaned = {
            str(key): float(value or 0.0)
            for key, value in (score_map or {}).items()
            if str(key).strip()
        }
        if not cleaned:
            return {}
        values = list(cleaned.values())
        minimum = min(values)
        maximum = max(values)
        if abs(maximum - minimum) < 1e-9:
            return {key: default for key in cleaned}
        return {
            key: (value - minimum) / (maximum - minimum)
            for key, value in cleaned.items()
        }

    def _ranking_confidence(self, lightfm_scores):
        if not lightfm_scores:
            return None
        sorted_scores = sorted(
            (float(value or 0.0) for value in lightfm_scores.values()),
            reverse=True,
        )
        if len(sorted_scores) == 1:
            return 1.0
        gap = sorted_scores[0] - sorted_scores[1]
        spread = max(sorted_scores[0] - sorted_scores[-1], 1e-6)
        return round(max(min(gap / spread, 1.0), 0.0), 3)

    def _selected_history_track(self, history):
        history_data = history.music_picker_data if isinstance(history.music_picker_data, dict) else {}
        selected_track_id = str(history_data.get('selected_track_id') or '').strip()
        for track in history.playlist_data or []:
            if not isinstance(track, dict):
                continue
            if selected_track_id and str(track.get('id') or '').strip() == selected_track_id:
                return track
        for track in history.playlist_data or []:
            if isinstance(track, dict):
                return track
        return None

    def _candidate_item_features(self, track):
        features = {
            self._artist_feature(track.get('artist')),
            self._source_feature(track.get('recommendation_source')),
            self._track_text_feature('type', track.get('item_type') or 'track'),
            self._popularity_feature(track.get('popularity')),
        }
        features.update(
            self._reason_emotion_features(track.get('emotion_alignment_reasons') or [])
        )
        features.update(
            self._reason_emotion_features(track.get('selection_reasons') or [])
        )
        return {feature for feature in features if feature}

    def _reason_emotion_features(self, reasons):
        features = set()
        for reason in reasons or []:
            normalized_reason = str(reason or '').strip().lower()
            if ':' not in normalized_reason:
                continue
            prefix, value = normalized_reason.split(':', 1)
            if prefix in {'keyword_fit', 'genre_fit', 'profile_fit', 'avoid_penalty'}:
                features.add(self._emotion_feature(value))
        return features

    def _user_id(self, user_id):
        return f'user:{int(user_id)}'

    def _request_user_id(self, user, emotion):
        if user and getattr(user, 'id', None):
            return self._user_id(user.id)
        return f'guest:{self._slug(emotion or "mixed") or "mixed"}'

    def _feature_token(self, value):
        normalized = str(value or '').strip().lower()
        return normalized or None

    def _emotion_feature(self, emotion):
        slug = self._slug(emotion)
        if not slug:
            return None
        return f'emotion:{slug}'

    def _artist_feature(self, artist):
        slug = self._slug(artist)
        if not slug:
            return None
        return f'artist:{slug}'

    def _source_feature(self, source):
        slug = self._slug(source)
        if not slug:
            return None
        return f'source:{slug}'

    def _track_text_feature(self, prefix, value):
        slug = self._slug(value)
        if not slug:
            return None
        return f'{prefix}:{slug}'

    def _popularity_feature(self, popularity):
        try:
            popularity_value = float(popularity or 0.0)
        except (TypeError, ValueError):
            popularity_value = 0.0
        if popularity_value >= 80:
            bucket = 'very_high'
        elif popularity_value >= 55:
            bucket = 'high'
        elif popularity_value >= 25:
            bucket = 'medium'
        else:
            bucket = 'low'
        return f'popularity:{bucket}'

    def _playlist_category(self, emotion, top_emotions):
        normalized_emotion = self._slug(emotion or 'mixed') or 'mixed'
        secondary = None
        for item in top_emotions or []:
            if not isinstance(item, dict):
                continue
            candidate = self._slug(item.get('emotion'))
            if candidate and candidate != normalized_emotion:
                secondary = candidate
                break
        if secondary:
            return f'{normalized_emotion}_{secondary}'
        return normalized_emotion

    def _build_confirmation(self, selected_track, emotion, prompt_text=None):
        if isinstance(selected_track, dict):
            track_name = str(selected_track.get('name') or '').strip()
            artist_name = str(selected_track.get('artist') or '').strip()
            if track_name and artist_name:
                return f'Playing {track_name} by {artist_name} for your {emotion} mood.'
            if track_name:
                return f'Playing {track_name} for your {emotion} mood.'
        return (
            f'Ranking the best available tracks for your {emotion} mood.'
            if str(prompt_text or '').strip()
            else f'Ranking tracks for your {emotion} mood.'
        )

    def _unique_list(self, values):
        unique = []
        seen = set()
        for value in values or []:
            normalized = str(value or '').strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            unique.append(normalized)
        return unique

    def _slug(self, value):
        normalized = re.sub(r'[^a-z0-9]+', '_', str(value or '').strip().lower())
        return normalized.strip('_')

    def _normalize_loss(self, value):
        normalized = str(value or 'warp').strip().lower() or 'warp'
        if normalized in {'warp', 'bpr', 'logistic', 'warp-kos'}:
            return normalized
        return 'warp'

    def _get_lightfm_classes(self):
        try:
            from lightfm import LightFM
            from lightfm.data import Dataset
        except ImportError as error:
            raise ImportError("Install lightfm to enable local ranking.") from error
        return LightFM, Dataset


lightfm_music_ranker = LightFMMusicRanker()
