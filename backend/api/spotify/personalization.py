"""
Spotify personalization: builds per-user taste context (top tracks, saved
tracks, recently played) and scores candidate tracks against it.
"""
import logging

from .constants import EMOTION_SEARCH_PARAMS, EMOTION_SPECIFIC_PERSONALIZATION_REASONS
from .utils import (
    _append_unique_tracks,
    _compact_failure,
    _format_nested_track_items,
    _format_tracks,
    _history_allows_learning,
    _normalize_scopes,
    _personalization_scope_map,
    _safe_int,
)

logger = logging.getLogger('api.spotify_service')


class SpotifyPersonalizationEngine:
    def __init__(self, service):
        self.service = service

    def _build_personalization_context(self, emotion, user=None, preferred_artists=None):
        context_config = EMOTION_SEARCH_PARAMS.get(emotion, EMOTION_SEARCH_PARAMS['mixed'])
        context = {
            'emotion': str(emotion or 'mixed').strip().lower() or 'mixed',
            'keywords': [
                str(keyword or '').strip().lower()
                for keyword in context_config.get('keywords', [])
                if str(keyword or '').strip()
            ],
            'genres': [
                str(genre or '').strip().lower()
                for genre in context_config.get('genres', [])
                if str(genre or '').strip()
            ],
            'preferred_artists': {
                str(artist or '').strip().lower()
                for artist in (preferred_artists or [])
                if str(artist or '').strip()
            },
            'preferred_track_scores': {},
            'preferred_artist_scores': {},
            'favorite_track_ids': set(),
            'history_track_ids': set(),
            'recent_recommended_track_counts': {},
            'cross_emotion_recent_track_counts': {},
        }

        if not user:
            return context

        from users.models import FavoriteTrack, PromptHistory, UserPreference

        preferences = UserPreference.objects.filter(
            user=user,
            emotion=emotion,
        ).only('spotify_track_id', 'artist_name', 'play_count')
        for pref in preferences:
            track_id = str(pref.spotify_track_id or '').strip()
            artist_name = str(pref.artist_name or '').strip().lower()
            play_count = max(_safe_int(pref.play_count, 0), 0)
            if track_id:
                context['preferred_track_scores'][track_id] = max(
                    context['preferred_track_scores'].get(track_id, 0),
                    play_count,
                )
            if artist_name:
                context['preferred_artist_scores'][artist_name] = max(
                    context['preferred_artist_scores'].get(artist_name, 0),
                    play_count,
                )

        context['favorite_track_ids'] = {
            str(track_id).strip()
            for track_id in FavoriteTrack.objects.filter(user=user)
            .values_list('spotify_track_id', flat=True)
            if str(track_id).strip()
        }

        histories = PromptHistory.objects.filter(
            user=user,
            detected_emotion=emotion,
        ).only('playlist_data')[:10]
        for history in histories:
            if not _history_allows_learning(history):
                continue
            playlist_data = history.playlist_data if isinstance(history.playlist_data, list) else []
            for item in playlist_data:
                if not isinstance(item, dict):
                    continue
                track_id = str(item.get('id') or '').strip()
                uri = str(item.get('uri') or '').strip()
                if not track_id and uri.startswith('spotify:track:'):
                    track_id = uri.split(':', 2)[-1]
                if track_id:
                    context['history_track_ids'].add(track_id)

        recent_histories = PromptHistory.objects.filter(
            user=user,
        ).only('detected_emotion', 'playlist_data')[:15]
        for history in recent_histories:
            if not _history_allows_learning(history):
                continue
            playlist_data = history.playlist_data if isinstance(history.playlist_data, list) else []
            history_track_ids = set()
            for item in playlist_data:
                if not isinstance(item, dict):
                    continue
                track_id = str(item.get('id') or '').strip()
                uri = str(item.get('uri') or '').strip()
                if not track_id and uri.startswith('spotify:track:'):
                    track_id = uri.split(':', 2)[-1]
                if track_id:
                    history_track_ids.add(track_id)
            for track_id in history_track_ids:
                context['recent_recommended_track_counts'][track_id] = (
                    context['recent_recommended_track_counts'].get(track_id, 0) + 1
                )
                if history.detected_emotion != emotion:
                    context['cross_emotion_recent_track_counts'][track_id] = (
                        context['cross_emotion_recent_track_counts'].get(track_id, 0) + 1
                    )

        return context

    def _score_personalized_track(self, track, context):
        track = track if isinstance(track, dict) else {}
        context = context if isinstance(context, dict) else {}
        requested_emotion = str(context.get('emotion') or 'mixed').strip().lower() or 'mixed'

        source_bonus = {
            'spotify_top_tracks': 1.6,
            'spotify_saved_tracks': 1.4,
            'spotify_recently_played': 1.1,
        }
        score = source_bonus.get(
            str(track.get('recommendation_source') or '').strip(),
            0.9,
        )

        selection_reasons = [
            str(track.get('recommendation_source') or 'spotify_catalog')
        ]
        track_id = str(track.get('id') or '').strip()
        artist_text = str(track.get('artist') or '').strip().lower()
        match_text = ' '.join([
            str(track.get('name') or '').strip().lower(),
            artist_text,
            str(track.get('album') or '').strip().lower(),
        ])
        has_emotion_signal = False

        preference_play_count = context.get('preferred_track_scores', {}).get(track_id, 0)
        if preference_play_count:
            score += 1.5 + min(preference_play_count, 8) * 0.12
            selection_reasons.append('emotion_preference')
            has_emotion_signal = True

        artist_preference_score = 0
        for preferred_artist, play_count in context.get('preferred_artist_scores', {}).items():
            if preferred_artist and preferred_artist in artist_text:
                artist_preference_score = max(artist_preference_score, play_count)
        if artist_preference_score:
            score += 0.8 + min(artist_preference_score, 8) * 0.08
            selection_reasons.append('artist_preference_history')

        preferred_artist_match = False
        for preferred_artist in context.get('preferred_artists', set()):
            if preferred_artist and preferred_artist in artist_text:
                preferred_artist_match = True
                score += 1.1
        if preferred_artist_match:
            selection_reasons.append('preferred_artist_match')

        if track_id and track_id in context.get('favorite_track_ids', set()):
            score += 0.7
            selection_reasons.append('favorite_track')

        if track_id and track_id in context.get('history_track_ids', set()):
            score += 0.35
            selection_reasons.append('recent_emotion_history')
            has_emotion_signal = True

        recent_recommended_count = context.get('recent_recommended_track_counts', {}).get(track_id, 0)
        if recent_recommended_count:
            score -= min(recent_recommended_count, 4) * 0.45
            selection_reasons.append('repeat_penalty')

        cross_emotion_repeat_count = context.get(
            'cross_emotion_recent_track_counts',
            {},
        ).get(track_id, 0)
        if cross_emotion_repeat_count:
            score -= min(cross_emotion_repeat_count, 4) * 0.9
            selection_reasons.append('cross_emotion_repeat_penalty')

        keyword_hits = 0
        for keyword in context.get('keywords', []):
            if keyword and keyword in match_text:
                keyword_hits += 1
        if keyword_hits:
            score += min(keyword_hits, 3) * 0.65
            selection_reasons.append('emotion_keyword_match')
            has_emotion_signal = True

        genre_hits = 0
        for genre in context.get('genres', []):
            if genre and genre in match_text:
                genre_hits += 1
        if genre_hits:
            score += min(genre_hits, 2) * 0.3
            selection_reasons.append('emotion_genre_match')
            has_emotion_signal = True

        if requested_emotion != 'mixed' and not has_emotion_signal:
            # Generic top/saved tracks should not dominate a clearly different mood.
            score -= 1.35
            selection_reasons.append('generic_personalization_penalty')

        score += min(max(_safe_int(track.get('popularity'), 0), 0), 100) / 1000

        unique_reasons = []
        seen_reasons = set()
        for reason in selection_reasons:
            if reason in seen_reasons:
                continue
            seen_reasons.add(reason)
            unique_reasons.append(reason)

        enriched = dict(track)
        enriched['personalization_score'] = round(score, 3)
        enriched['selection_reasons'] = unique_reasons
        return enriched

    def _track_has_personalized_emotion_signal(self, track, emotion):
        normalized_emotion = str(emotion or 'mixed').strip().lower() or 'mixed'
        if normalized_emotion == 'mixed':
            return True

        selection_reasons = {
            str(reason or '').strip()
            for reason in (track.get('selection_reasons') or [])
            if str(reason or '').strip()
        }
        return bool(selection_reasons.intersection(
            EMOTION_SPECIFIC_PERSONALIZATION_REASONS
        ))

    def get_user_music_candidates(
        self,
        emotion,
        user=None,
        preferred_artists=None,
        limit=20,
    ):
        result = {
            'ok': False,
            'tracks': [],
            'sources_used': [],
            'missing_scopes': [],
            'errors': [],
            'token_error': None,
        }

        if not user or not getattr(user, 'is_spotify_connected', False):
            return result

        token_details = self.service.ensure_valid_token_with_details(user)
        token = token_details.get('access_token')
        if not token:
            result['token_error'] = token_details.get('refresh_error') or 'token_missing'
            return result

        granted_scopes = set(_normalize_scopes(token_details.get('granted_scopes')))
        source_configs = [
            (
                'top_tracks',
                'spotify_top_tracks',
                '/me/top/tracks',
                {'time_range': 'medium_term', 'limit': min(max(limit, 10), 25)},
            ),
            (
                'saved_tracks',
                'spotify_saved_tracks',
                '/me/tracks',
                {'limit': min(max(limit, 10), 25)},
            ),
            (
                'recently_played',
                'spotify_recently_played',
                '/me/player/recently-played',
                {'limit': min(max(limit, 10), 20)},
            ),
        ]

        candidates = []
        seen_keys = set()
        personalization_context = self.service._build_personalization_context(
            emotion,
            user=user,
            preferred_artists=preferred_artists,
        )

        for source_key, recommendation_source, endpoint, params in source_configs:
            required_scope = _personalization_scope_map().get(source_key)
            if required_scope and required_scope not in granted_scopes:
                result['missing_scopes'].append(required_scope)
                continue

            upstream_result = self.service._spotify_get(token, endpoint, params=params)
            if not upstream_result.get('ok'):
                result['errors'].append(
                    _compact_failure(
                        upstream_result,
                        source=source_key,
                        extra={'endpoint': endpoint},
                    )
                )
                continue

            payload = upstream_result.get('data') or {}
            if source_key == 'top_tracks':
                tracks = _format_tracks(payload.get('items', []))
                for track in tracks:
                    track['recommendation_source'] = recommendation_source
                    track['catalog_source'] = recommendation_source
            elif source_key == 'saved_tracks':
                tracks = _format_nested_track_items(
                    payload.get('items', []),
                    recommendation_source=recommendation_source,
                    added_at_key='added_at',
                )
            else:
                tracks = _format_nested_track_items(
                    payload.get('items', []),
                    recommendation_source=recommendation_source,
                    played_at_key='played_at',
                )

            scored_tracks = [
                self.service._score_personalized_track(track, personalization_context)
                for track in tracks
            ]
            _append_unique_tracks(
                candidates,
                seen_keys,
                scored_tracks,
                limit=max(limit * 2, limit),
            )
            if scored_tracks:
                result['sources_used'].append(source_key)

        candidates.sort(
            key=lambda item: (
                -float(item.get('personalization_score', 0.0)),
                str(item.get('name') or '').lower(),
            )
        )
        normalized_emotion = str(emotion or 'mixed').strip().lower() or 'mixed'
        if normalized_emotion != 'mixed':
            emotion_specific_candidates = []
            generic_candidates = []
            for candidate in candidates:
                if self.service._track_has_personalized_emotion_signal(candidate, normalized_emotion):
                    emotion_specific_candidates.append(candidate)
                else:
                    generic_candidates.append(candidate)

            if emotion_specific_candidates:
                generic_cap = min(max(limit // 5, 1), 2)
                candidates = [
                    *emotion_specific_candidates,
                    *generic_candidates[:generic_cap],
                ]
            else:
                candidates = []

        result['tracks'] = candidates[:limit]
        result['ok'] = bool(result['tracks'])

        if result['sources_used']:
            logger.info(
                "Spotify user music candidates user=%s emotion=%s sources=%s count=%s",
                user.id,
                emotion,
                ','.join(result['sources_used']),
                len(result['tracks']),
            )

        return result
