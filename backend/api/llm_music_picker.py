"""
LLM-backed music reranker for EmoTune.

This service does not replace Spotify search or the existing heuristic selector.
It reranks a small candidate set and can order a short playlist when an LLM
provider is configured. When disabled or unavailable, callers should fall back
to the heuristic selector.
"""
import json
import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

GEMINI_API_BASE = 'https://generativelanguage.googleapis.com'

EMOTION_PLAYLIST_GUIDANCE = {
    'happy': {
        'target_vibe': 'uplifting, bright, warm, and feel-good',
        'avoid_vibe': 'bleak, sleepy, grief-heavy, or emotionally flat',
    },
    'sad': {
        'target_vibe': 'gentle, reflective, comforting, and emotionally supportive',
        'avoid_vibe': 'party, workout, rage, or aggressively celebratory',
    },
    'angry': {
        'target_vibe': 'cathartic, intense, powerful, and channeling energy',
        'avoid_vibe': 'cute, sleepy, meditation-first, or mismatched cheerfulness',
    },
    'motivational': {
        'target_vibe': 'driven, energetic, victorious, and momentum-building',
        'avoid_vibe': 'hopeless, sleepy, or emotionally collapsing',
    },
    'fear': {
        'target_vibe': 'grounding, steadying, calm, and reassuring',
        'avoid_vibe': 'aggressive, chaotic, panic-inducing, or rage-heavy',
    },
    'depressing': {
        'target_vibe': 'soft, gentle, comforting, and emotionally safe',
        'avoid_vibe': 'party, rage, or abrasive high-energy tracks',
    },
    'surprising': {
        'target_vibe': 'fresh, eclectic, unexpected, and alive',
        'avoid_vibe': 'flat, generic, lullaby-like, or emotionally dead',
    },
    'stressed': {
        'target_vibe': 'calming, soothing, focused, and decompressive',
        'avoid_vibe': 'workout, rage, hype, or extra-overwhelming intensity',
    },
    'calm': {
        'target_vibe': 'peaceful, spacious, gentle, and settled',
        'avoid_vibe': 'rage, workout, party, or harsh intensity',
    },
    'lonely': {
        'target_vibe': 'warm, companionable, reflective, and intimate',
        'avoid_vibe': 'hollow party energy or abrasive aggression',
    },
    'romantic': {
        'target_vibe': 'tender, intimate, warm, and affectionate',
        'avoid_vibe': 'rage, workout, or emotionally cold intensity',
    },
    'nostalgic': {
        'target_vibe': 'memory-rich, reflective, classic, and sentimental',
        'avoid_vibe': 'abrasive rage or emotionally disconnected hype',
    },
    'mixed': {
        'target_vibe': 'balanced, nuanced, emotionally blended, and flexible',
        'avoid_vibe': 'one-note extremes unless the prompt strongly asks for them',
    },
}


class LLMMusicPicker:
    def __init__(self):
        self.enabled = bool(getattr(settings, 'LLM_MUSIC_PICKER_ENABLED', False))
        self.api_url = str(getattr(settings, 'LLM_MUSIC_PICKER_API_URL', '') or '').strip()
        self.provider = self._normalize_provider(
            getattr(settings, 'LLM_MUSIC_PICKER_PROVIDER', ''),
            api_url=self.api_url,
        )
        self.api_key = str(getattr(settings, 'LLM_MUSIC_PICKER_API_KEY', '') or '').strip()
        self.model = str(getattr(settings, 'LLM_MUSIC_PICKER_MODEL', '') or '').strip()
        self.gemini_api_version = str(
            getattr(settings, 'LLM_MUSIC_PICKER_GEMINI_API_VERSION', 'v1beta') or 'v1beta'
        ).strip() or 'v1beta'
        self.timeout_seconds = max(
            float(getattr(settings, 'LLM_MUSIC_PICKER_TIMEOUT_SECONDS', 8.0) or 8.0),
            1.0,
        )
        self.max_candidates = max(
            int(getattr(settings, 'LLM_MUSIC_PICKER_MAX_CANDIDATES', 8) or 8),
            2,
        )
        self.playlist_size = max(
            int(getattr(settings, 'LLM_MUSIC_PICKER_PLAYLIST_SIZE', 5) or 5),
            1,
        )
        self.temperature = float(
            getattr(settings, 'LLM_MUSIC_PICKER_TEMPERATURE', 0.2) or 0.2
        )
        self.search_query_count = max(
            int(getattr(settings, 'LLM_MUSIC_PICKER_SEARCH_QUERY_COUNT', 6) or 6),
            3,
        )

    def is_configured(self):
        if not self.enabled or not self.api_key or not self.model:
            return False
        if self.provider == 'gemini':
            return True
        return bool(self.api_url)

    def build_search_plan(
        self,
        *,
        prompt_text,
        emotion,
        top_emotions,
        all_scores=None,
        confidence_band=None,
        confidence_margin=None,
        preferred_artists=None,
        search_query_count=None,
    ):
        resolved_query_count = self._resolve_search_query_count(search_query_count)
        fallback_queries = self._fallback_search_queries(
            prompt_text=prompt_text,
            emotion=emotion,
            top_emotions=top_emotions,
            all_scores=all_scores,
            confidence_band=confidence_band,
            confidence_margin=confidence_margin,
            preferred_artists=preferred_artists,
            search_query_count=resolved_query_count,
        )
        base_result = {
            'ok': False,
            'strategy': 'heuristic_search_plan',
            'search_queries': fallback_queries,
            'reason': None,
            'confidence': None,
            'provider': 'disabled',
            'model': None,
            'used_fallback': True,
            'error': None,
            **self._fallback_structured_fields(
                selected_track=None,
                prompt_text=prompt_text,
                emotion=emotion,
            ),
        }

        if not self.is_configured():
            base_result['error'] = 'llm_picker_not_configured'
            return base_result

        payload = self._build_search_plan_request_payload(
            prompt_text=prompt_text,
            emotion=emotion,
            top_emotions=top_emotions,
            all_scores=all_scores,
            confidence_band=confidence_band,
            confidence_margin=confidence_margin,
            preferred_artists=preferred_artists or [],
            search_query_count=resolved_query_count,
        )

        try:
            response = self._post_completion_request(payload)
        except requests.RequestException as error:
            logger.warning("LLM music search-plan request failed: %s", error)
            base_result['error'] = 'llm_search_plan_request_failed'
            return base_result

        if response.status_code >= 400:
            logger.warning(
                "LLM music search-plan upstream failed status=%s body=%s",
                response.status_code,
                response.text[:500],
            )
            base_result['error'] = f'llm_search_plan_http_{response.status_code}'
            return base_result

        response_payload = self._parse_response_payload(response)
        if not isinstance(response_payload, dict):
            base_result['error'] = 'llm_search_plan_invalid_response'
            return base_result

        llm_queries = self._normalize_search_queries(
            response_payload.get('search_queries'),
            limit=resolved_query_count,
        )
        if not llm_queries:
            base_result['error'] = 'llm_search_plan_missing_queries'
            return base_result

        completed_queries = self._merge_search_queries(
            llm_queries,
            fallback_queries,
            limit=resolved_query_count,
        )
        structured_fields = self._extract_structured_fields(
            response_payload,
            selected_track=None,
            prompt_text=prompt_text,
            emotion=emotion,
        )
        return {
            'ok': True,
            'strategy': 'llm_search_plan',
            'search_queries': completed_queries,
            'reason': str(response_payload.get('reason') or '').strip() or None,
            'confidence': self._safe_float(response_payload.get('confidence')),
            'provider': self.provider,
            'model': self.model,
            'used_fallback': len(completed_queries) > len(llm_queries),
            'error': None,
            **structured_fields,
        }

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
            playlist_size=1,
        )
        return {
            'ok': bool(playlist_result.get('ok')),
            'strategy': (
                'llm_reranker'
                if playlist_result.get('strategy') == 'llm_playlist'
                else 'heuristic'
            ),
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
        playlist_size=None,
    ):
        prepared_candidates = self._prepare_candidates(candidates)
        prepared_candidates = self._sort_candidates_for_llm(prepared_candidates)
        resolved_playlist_size = self._resolve_playlist_size(
            playlist_size,
            len(prepared_candidates),
        )
        fallback_tracks = self._strip_internal_fields(
            prepared_candidates[:resolved_playlist_size]
        )
        base_result = {
            'ok': False,
            'strategy': 'heuristic_playlist',
            'tracks': fallback_tracks,
            'selected_track': fallback_tracks[0] if fallback_tracks else None,
            'playlist_track_ids': [
                str(track.get('id') or '').strip()
                for track in fallback_tracks
                if str(track.get('id') or '').strip()
            ],
            'reason': None,
            'confidence': None,
            'provider': 'disabled',
            'model': None,
            'used_fallback': True,
            'error': None,
            'candidates': prepared_candidates,
            **self._fallback_structured_fields(
                selected_track=fallback_tracks[0] if fallback_tracks else None,
                prompt_text=prompt_text,
                emotion=emotion,
            ),
        }

        if not prepared_candidates:
            base_result['error'] = 'no_candidates'
            return base_result

        if not self.is_configured():
            base_result['error'] = 'llm_picker_not_configured'
            return base_result

        payload = self._build_request_payload(
            prompt_text=prompt_text,
            emotion=emotion,
            top_emotions=top_emotions,
            all_scores=all_scores,
            confidence_band=confidence_band,
            confidence_margin=confidence_margin,
            candidates=prepared_candidates,
            preferred_artists=preferred_artists or [],
            playlist_size=resolved_playlist_size,
        )

        try:
            response = self._post_completion_request(payload)
        except requests.RequestException as error:
            logger.warning("LLM music playlist request failed: %s", error)
            base_result['error'] = 'llm_request_failed'
            return base_result

        if response.status_code >= 400:
            logger.warning(
                "LLM music playlist upstream failed status=%s body=%s",
                response.status_code,
                response.text[:500],
            )
            base_result['error'] = f'llm_http_{response.status_code}'
            return base_result

        response_payload = self._parse_response_payload(response)
        if not isinstance(response_payload, dict):
            base_result['error'] = 'llm_invalid_response'
            return base_result

        playlist_candidate_ids = self._normalize_candidate_ids(
            response_payload.get('playlist_candidate_ids')
            or response_payload.get('selected_candidate_ids')
            or [response_payload.get('selected_candidate_id')]
        )
        if not playlist_candidate_ids:
            base_result['error'] = 'llm_missing_selection'
            return base_result

        ordered_tracks = self._resolve_tracks_from_ids(
            prepared_candidates,
            playlist_candidate_ids,
        )
        if not ordered_tracks:
            base_result['error'] = 'llm_selected_unknown_candidate'
            return base_result

        used_fallback = len(ordered_tracks) < resolved_playlist_size
        if used_fallback:
            ordered_tracks = self._fill_playlist_with_fallback_tracks(
                ordered_tracks,
                prepared_candidates,
                resolved_playlist_size,
            )

        playlist_tracks = self._strip_internal_fields(ordered_tracks[:resolved_playlist_size])
        structured_fields = self._extract_structured_fields(
            response_payload,
            selected_track=playlist_tracks[0] if playlist_tracks else None,
            prompt_text=prompt_text,
            emotion=emotion,
        )
        return {
            'ok': True,
            'strategy': 'llm_playlist',
            'tracks': playlist_tracks,
            'selected_track': playlist_tracks[0] if playlist_tracks else None,
            'playlist_track_ids': [
                str(track.get('id') or '').strip()
                for track in playlist_tracks
                if str(track.get('id') or '').strip()
            ],
            'reason': str(response_payload.get('reason') or '').strip() or None,
            'confidence': self._safe_float(response_payload.get('confidence')),
            'provider': self.provider,
            'model': self.model,
            'used_fallback': used_fallback,
            'error': None,
            'candidates': prepared_candidates,
            **structured_fields,
        }

    def _prepare_candidates(self, candidates):
        prepared = []
        for candidate in candidates or []:
            if not isinstance(candidate, dict):
                continue
            item_type = str(candidate.get('item_type') or '').strip().lower()
            if item_type and item_type != 'track':
                continue
            candidate_id = str(candidate.get('id') or candidate.get('uri') or '').strip()
            if not candidate_id:
                continue
            prepared_candidate = dict(candidate)
            prepared_candidate['candidate_id'] = candidate_id
            prepared.append(prepared_candidate)
            if len(prepared) >= self.max_candidates:
                break
        return prepared

    def _build_request_payload(
        self,
        *,
        prompt_text,
        emotion,
        top_emotions,
        all_scores,
        confidence_band,
        confidence_margin,
        candidates,
        preferred_artists,
        playlist_size,
    ):
        serializable_candidates = []
        for candidate in candidates:
            serializable_candidates.append({
                'candidate_id': candidate.get('candidate_id'),
                'name': candidate.get('name'),
                'artist': candidate.get('artist'),
                'album': candidate.get('album'),
                'popularity': candidate.get('popularity'),
                'recommendation_source': candidate.get('recommendation_source'),
                'selection_reasons': candidate.get('selection_reasons', []),
                'emotion_alignment_score': candidate.get('emotion_alignment_score'),
                'emotion_alignment_reasons': candidate.get('emotion_alignment_reasons', []),
                'personalization_score': candidate.get('personalization_score'),
                'is_preferred': bool(candidate.get('is_preferred')),
            })

        serialized_emotion_scores = self._serialize_emotion_scores(all_scores)
        guidance = self._build_emotion_guidance(
            emotion,
            top_emotions=top_emotions,
            all_scores=serialized_emotion_scores,
            confidence_band=confidence_band,
            confidence_margin=confidence_margin,
        )
        system_prompt = (
            "You are a helpful Music Assistant for EmoTune with access to Spotify candidate "
            "tracks. First translate the user's request into structured intent and entities, "
            "then choose up to "
            f"{playlist_size} Spotify tracks from the provided candidates and order them "
            "into a short, cohesive playlist that fits the user's emotional context and "
            "prompt. Treat emotion_alignment_score as a strong prior for emotional fit. "
            "Use all_scores and confidence_margin to judge whether the user's mood is clear "
            "or blended. If the emotional distribution is mixed or the confidence margin is "
            "small, prefer songs that can bridge the top emotions instead of overcommitting "
            "to a single extreme vibe. "
            "Do not choose tracks that obviously conflict with the target mood unless the "
            "prompt explicitly asks for contrast. Prefer directly playable tracks, emotional "
            "fit, and some artist or sound variety. Identify intent as one of "
            "track, artist, genre, mood, or mixed_request. Extract artist_name, track_name, "
            "and playlist_category when possible. If the user asks for a vibe, map it to a "
            "relevant playlist_category. Return strict JSON with keys "
            "playlist_candidate_ids, reason, confidence, intent, artist_name, track_name, "
            "playlist_category, confirmation."
        )
        user_payload = {
            'prompt_text': str(prompt_text or '').strip(),
            'emotion': str(emotion or 'mixed').strip(),
            'top_emotions': top_emotions or [],
            'all_scores': serialized_emotion_scores,
            'confidence_band': str(confidence_band or '').strip() or None,
            'confidence_margin': self._safe_float(confidence_margin),
            'emotion_guidance': guidance,
            'preferred_artists': [
                str(artist or '').strip()
                for artist in preferred_artists
                if str(artist or '').strip()
            ][:5],
            'playlist_size': playlist_size,
            'candidates': serializable_candidates,
        }
        return self._build_generation_request(
            system_prompt=system_prompt,
            user_payload=user_payload,
            response_schema=self._playlist_response_schema(),
        )

    def _build_search_plan_request_payload(
        self,
        *,
        prompt_text,
        emotion,
        top_emotions,
        all_scores,
        confidence_band,
        confidence_margin,
        preferred_artists,
        search_query_count,
    ):
        serialized_emotion_scores = self._serialize_emotion_scores(all_scores)
        guidance = self._build_emotion_guidance(
            emotion,
            top_emotions=top_emotions,
            all_scores=serialized_emotion_scores,
            confidence_band=confidence_band,
            confidence_margin=confidence_margin,
        )
        system_prompt = (
            "You are a helpful Music Assistant for EmoTune. Convert the user's prompt and "
            "emotion analysis into Spotify search queries for tracks. Use the prompt_text, "
            "emotion, top_emotions, all_scores, confidence_band, and confidence_margin to "
            "decide the best search direction. If the mood is blended, include bridge "
            "queries that combine the strongest emotions instead of forcing a single mood. "
            "If the mood is clear, you may suggest one representative seed song and artist "
            "that strongly fits the emotion, so Spotify can search that exact song first. "
            "If the user implies an artist, track, era, or genre, reflect that in the "
            "queries. Return up to "
            f"{search_query_count} concise Spotify-friendly queries and strict JSON with "
            "keys search_queries, reason, confidence, intent, artist_name, track_name, "
            "playlist_category, confirmation."
        )
        user_payload = {
            'prompt_text': str(prompt_text or '').strip(),
            'emotion': str(emotion or 'mixed').strip(),
            'top_emotions': top_emotions or [],
            'all_scores': serialized_emotion_scores,
            'confidence_band': str(confidence_band or '').strip() or None,
            'confidence_margin': self._safe_float(confidence_margin),
            'emotion_guidance': guidance,
            'preferred_artists': [
                str(artist or '').strip()
                for artist in preferred_artists
                if str(artist or '').strip()
            ][:5],
            'search_query_count': search_query_count,
        }
        return self._build_generation_request(
            system_prompt=system_prompt,
            user_payload=user_payload,
            response_schema=self._search_plan_response_schema(),
        )

    def _build_generation_request(self, *, system_prompt, user_payload, response_schema):
        serialized_payload = json.dumps(user_payload)
        if self.provider == 'gemini':
            return {
                'systemInstruction': {
                    'parts': [{'text': str(system_prompt or '').strip()}],
                },
                'contents': [
                    {
                        'role': 'user',
                        'parts': [{'text': serialized_payload}],
                    },
                ],
                'generationConfig': {
                    'temperature': self.temperature,
                    'responseMimeType': 'application/json',
                    'responseSchema': self._sanitize_gemini_response_schema(response_schema),
                },
            }

        return {
            'model': self.model,
            'temperature': self.temperature,
            'response_format': {'type': 'json_object'},
            'messages': [
                {'role': 'system', 'content': str(system_prompt or '').strip()},
                {'role': 'user', 'content': serialized_payload},
            ],
        }

    def _sanitize_gemini_response_schema(self, value):
        if isinstance(value, dict):
            sanitized = {}
            for key, item in value.items():
                if key == 'additionalProperties':
                    continue
                sanitized[key] = self._sanitize_gemini_response_schema(item)
            return sanitized
        if isinstance(value, list):
            return [self._sanitize_gemini_response_schema(item) for item in value]
        return value

    def _playlist_response_schema(self):
        return {
            'type': 'object',
            'properties': {
                'playlist_candidate_ids': {
                    'type': 'array',
                    'items': {'type': 'string'},
                },
                'reason': {'type': 'string'},
                'confidence': {'type': 'number'},
                'intent': {'type': 'string'},
                'artist_name': {'type': 'string'},
                'track_name': {'type': 'string'},
                'playlist_category': {'type': 'string'},
                'confirmation': {'type': 'string'},
            },
            'required': ['playlist_candidate_ids'],
            'additionalProperties': True,
        }

    def _search_plan_response_schema(self):
        return {
            'type': 'object',
            'properties': {
                'search_queries': {
                    'type': 'array',
                    'items': {'type': 'string'},
                },
                'reason': {'type': 'string'},
                'confidence': {'type': 'number'},
                'intent': {'type': 'string'},
                'artist_name': {'type': 'string'},
                'track_name': {'type': 'string'},
                'playlist_category': {'type': 'string'},
                'confirmation': {'type': 'string'},
            },
            'required': ['search_queries'],
            'additionalProperties': True,
        }

    def _sort_candidates_for_llm(self, candidates):
        prepared = [dict(candidate) for candidate in (candidates or []) if isinstance(candidate, dict)]
        prepared.sort(
            key=lambda item: (
                -float(item.get('emotion_alignment_score', 0.0) or 0.0),
                -float(item.get('personalization_score', 0.0) or 0.0),
                -float(item.get('popularity', 0) or 0),
                str(item.get('name') or '').lower(),
            )
        )
        return prepared

    def _serialize_emotion_scores(self, all_scores):
        if not isinstance(all_scores, dict):
            return {}

        ordered_scores = []
        for emotion_name, score in all_scores.items():
            normalized_emotion = str(emotion_name or '').strip().lower()
            if not normalized_emotion:
                continue
            normalized_score = self._safe_float(score)
            if normalized_score is None:
                continue
            ordered_scores.append((normalized_emotion, max(min(normalized_score, 1.0), 0.0)))

        ordered_scores.sort(key=lambda item: (-item[1], item[0]))
        return {
            emotion_name: round(score, 4)
            for emotion_name, score in ordered_scores
        }

    def _build_emotion_guidance(
        self,
        emotion,
        *,
        top_emotions=None,
        all_scores=None,
        confidence_band=None,
        confidence_margin=None,
    ):
        normalized_emotion = str(emotion or 'mixed').strip().lower() or 'mixed'
        profile = EMOTION_PLAYLIST_GUIDANCE.get(
            normalized_emotion,
            EMOTION_PLAYLIST_GUIDANCE['mixed'],
        )
        secondary = None
        for item in top_emotions or []:
            if not isinstance(item, dict):
                continue
            item_emotion = str(item.get('emotion') or '').strip().lower()
            if item_emotion and item_emotion != normalized_emotion:
                secondary = item_emotion
                break
        normalized_scores = self._serialize_emotion_scores(all_scores)
        top_distribution = [
            {'emotion': emotion_name, 'score': score}
            for emotion_name, score in list(normalized_scores.items())[:4]
        ]
        normalized_margin = self._safe_float(confidence_margin)
        blended_emotions = [
            item['emotion']
            for item in top_distribution[1:]
            if float(item.get('score') or 0.0) >= 0.18
        ]
        return {
            'target_vibe': profile['target_vibe'],
            'avoid_vibe': profile['avoid_vibe'],
            'secondary_emotion': secondary,
            'confidence_band': str(confidence_band or '').strip() or 'unknown',
            'confidence_margin': normalized_margin,
            'top_distribution': top_distribution,
            'blended_emotions': blended_emotions,
            'is_blended_mood': bool(
                len(blended_emotions) > 0 or
                (normalized_margin is not None and normalized_margin < 0.15)
            ),
        }

    def _fallback_structured_fields(self, *, selected_track, prompt_text, emotion):
        track = selected_track if isinstance(selected_track, dict) else {}
        prompt_text = str(prompt_text or '').strip()
        artist_name = str(track.get('artist') or '').strip() or None
        track_name = str(track.get('name') or '').strip() or None
        playlist_category = str(emotion or 'mixed').strip() or 'mixed'
        if track_name:
            confirmation = f"Playing {track_name}"
            if artist_name:
                confirmation += f" by {artist_name}."
            else:
                confirmation += "."
        else:
            confirmation = (
                f"Playing a {playlist_category} pick from Spotify."
                if playlist_category
                else 'Playing a Spotify pick.'
            )
        return {
            'intent': 'track' if track_name else 'mood',
            'artist_name': artist_name,
            'track_name': track_name,
            'playlist_category': playlist_category,
            'confirmation': confirmation,
            'original_prompt_text': prompt_text or None,
        }

    def _extract_structured_fields(self, payload, *, selected_track, prompt_text, emotion):
        fallback = self._fallback_structured_fields(
            selected_track=selected_track,
            prompt_text=prompt_text,
            emotion=emotion,
        )
        if not isinstance(payload, dict):
            return fallback

        result = dict(fallback)
        intent = str(payload.get('intent') or '').strip().lower()
        if intent:
            result['intent'] = intent

        for key in ('artist_name', 'track_name', 'playlist_category', 'confirmation'):
            value = str(payload.get(key) or '').strip()
            if value:
                result[key] = value
        return result

    def _resolve_search_query_count(self, search_query_count):
        resolved_count = (
            search_query_count
            if search_query_count is not None
            else self.search_query_count
        )
        try:
            resolved_count = int(resolved_count)
        except (TypeError, ValueError):
            resolved_count = self.search_query_count
        return max(resolved_count, 3)

    def _resolve_playlist_size(self, playlist_size, candidate_count):
        resolved_size = playlist_size if playlist_size is not None else self.playlist_size
        try:
            resolved_size = int(resolved_size)
        except (TypeError, ValueError):
            resolved_size = self.playlist_size
        resolved_size = max(resolved_size, 1)
        if candidate_count <= 0:
            return resolved_size
        return min(resolved_size, candidate_count)

    def _parse_response_payload(self, response):
        try:
            payload = response.json()
        except ValueError:
            return None

        if not isinstance(payload, dict):
            return None

        if isinstance(payload.get('choices'), list) and payload['choices']:
            message = payload['choices'][0].get('message') or {}
            content = message.get('content')
            if isinstance(content, str):
                return self._parse_json_text(content)
            if isinstance(content, list):
                text_parts = []
                for part in content:
                    if isinstance(part, dict) and part.get('type') == 'text':
                        text_parts.append(str(part.get('text') or ''))
                return self._parse_json_text(''.join(text_parts))

        if isinstance(payload.get('candidates'), list) and payload['candidates']:
            text_parts = []
            for candidate in payload['candidates']:
                content = candidate.get('content') if isinstance(candidate, dict) else None
                parts = content.get('parts') if isinstance(content, dict) else []
                for part in parts or []:
                    if isinstance(part, dict) and part.get('text'):
                        text_parts.append(str(part.get('text') or ''))
                if text_parts:
                    break
            return self._parse_json_text(''.join(text_parts))

        if 'playlist_candidate_ids' in payload or 'selected_candidate_id' in payload:
            return payload

        if 'search_queries' in payload:
            return payload

        return None

    def _parse_json_text(self, text):
        text = str(text or '').strip()
        if not text:
            return None
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            start = text.find('{')
            end = text.rfind('}')
            if start == -1 or end == -1 or end <= start:
                return None
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                return None

    def _safe_float(self, value):
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _normalize_provider(self, value, *, api_url=''):
        normalized = str(value or '').strip().lower()
        if normalized in {'gemini', 'google_gemini', 'google'}:
            return 'gemini'
        if normalized in {'openai', 'openai_compatible', 'openai-compatible'}:
            return 'openai_compatible'
        if str(api_url or '').strip():
            return 'openai_compatible'
        return 'gemini'

    def _request_url(self):
        if self.provider == 'gemini':
            if self.api_url:
                return self.api_url
            model_name = str(self.model or '').strip()
            if not model_name.startswith('models/'):
                model_name = f'models/{model_name}'
            return (
                f"{GEMINI_API_BASE}/{self.gemini_api_version}/"
                f"{model_name}:generateContent"
            )
        return self.api_url

    def _request_headers(self):
        if self.provider == 'gemini':
            return {
                'x-goog-api-key': self.api_key,
                'Content-Type': 'application/json',
            }
        return {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json',
        }

    def _post_completion_request(self, payload):
        return requests.post(
            self._request_url(),
            headers=self._request_headers(),
            json=payload,
            timeout=self.timeout_seconds,
        )

    def _normalize_candidate_ids(self, values):
        if isinstance(values, str):
            raw_values = [values]
        elif isinstance(values, (list, tuple)):
            raw_values = list(values)
        else:
            raw_values = []

        ordered = []
        seen = set()
        for value in raw_values:
            candidate_id = str(value or '').strip()
            if not candidate_id or candidate_id in seen:
                continue
            seen.add(candidate_id)
            ordered.append(candidate_id)
        return ordered

    def _normalize_search_queries(self, values, *, limit):
        if isinstance(values, str):
            raw_values = [values]
        elif isinstance(values, (list, tuple)):
            raw_values = list(values)
        else:
            raw_values = []

        ordered = []
        seen = set()
        for value in raw_values:
            query = ' '.join(str(value or '').strip().split())
            normalized = query.lower()
            if len(query) < 2 or normalized in seen:
                continue
            seen.add(normalized)
            ordered.append(query)
            if len(ordered) >= limit:
                break
        return ordered

    def _merge_search_queries(self, primary_queries, fallback_queries, *, limit):
        merged = []
        seen = set()
        for value in list(primary_queries or []) + list(fallback_queries or []):
            query = ' '.join(str(value or '').strip().split())
            normalized = query.lower()
            if len(query) < 2 or normalized in seen:
                continue
            seen.add(normalized)
            merged.append(query)
            if len(merged) >= limit:
                break
        return merged

    def _fallback_search_queries(
        self,
        *,
        prompt_text,
        emotion,
        top_emotions=None,
        all_scores=None,
        confidence_band=None,
        confidence_margin=None,
        preferred_artists=None,
        search_query_count,
    ):
        normalized_emotion = str(emotion or 'mixed').strip().lower() or 'mixed'
        guidance = self._build_emotion_guidance(
            normalized_emotion,
            top_emotions=top_emotions,
            all_scores=all_scores,
            confidence_band=confidence_band,
            confidence_margin=confidence_margin,
        )
        structured_fields = self._fallback_structured_fields(
            selected_track=None,
            prompt_text=prompt_text,
            emotion=normalized_emotion,
        )
        playlist_category = str(structured_fields.get('playlist_category') or '').strip()
        artists = [
            str(artist or '').strip()
            for artist in (preferred_artists or [])
            if str(artist or '').strip()
        ]

        queries = []
        if playlist_category:
            queries.append(playlist_category)
            if playlist_category.lower() != normalized_emotion:
                queries.append(f'{normalized_emotion} {playlist_category}')

        for artist in artists[:3]:
            queries.append(f'artist:"{artist}" {normalized_emotion}')
            if playlist_category:
                queries.append(f'artist:"{artist}" {playlist_category}')
            queries.append(f'artist:"{artist}"')

        if guidance.get('secondary_emotion'):
            queries.append(
                f"{normalized_emotion} {guidance['secondary_emotion']}"
            )

        for distribution_item in guidance.get('top_distribution') or []:
            distribution_emotion = str(distribution_item.get('emotion') or '').strip()
            if distribution_emotion:
                queries.append(distribution_emotion)
                queries.append(f'{distribution_emotion} songs')

        target_vibe = str(guidance.get('target_vibe') or '').replace(' and ', ', ')
        for fragment in target_vibe.split(','):
            cleaned_fragment = ' '.join(fragment.strip().split())
            if cleaned_fragment:
                queries.append(cleaned_fragment)
                queries.append(f'{cleaned_fragment} songs')

        queries.extend([
            normalized_emotion,
            f'{normalized_emotion} songs',
            f'{normalized_emotion} playlist',
            f'{normalized_emotion} spotify',
        ])
        return self._normalize_search_queries(
            queries,
            limit=search_query_count,
        )

    def _resolve_tracks_from_ids(self, candidates, candidate_ids):
        candidate_map = {
            str(candidate.get('candidate_id') or '').strip(): candidate
            for candidate in candidates
            if str(candidate.get('candidate_id') or '').strip()
        }
        resolved = []
        for candidate_id in candidate_ids:
            candidate = candidate_map.get(candidate_id)
            if not candidate:
                continue
            resolved.append(dict(candidate))
        return resolved

    def _fill_playlist_with_fallback_tracks(self, selected_tracks, candidates, playlist_size):
        seen_ids = {
            str(track.get('candidate_id') or '').strip()
            for track in selected_tracks
            if str(track.get('candidate_id') or '').strip()
        }
        completed_tracks = [dict(track) for track in selected_tracks]
        for candidate in candidates:
            candidate_id = str(candidate.get('candidate_id') or '').strip()
            if not candidate_id or candidate_id in seen_ids:
                continue
            completed_tracks.append(dict(candidate))
            seen_ids.add(candidate_id)
            if len(completed_tracks) >= playlist_size:
                break
        return completed_tracks

    def _strip_internal_fields(self, tracks):
        stripped = []
        for track in tracks or []:
            if not isinstance(track, dict):
                continue
            cleaned_track = dict(track)
            cleaned_track.pop('candidate_id', None)
            stripped.append(cleaned_track)
        return stripped


llm_music_picker = LLMMusicPicker()
