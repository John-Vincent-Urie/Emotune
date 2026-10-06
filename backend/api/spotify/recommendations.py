"""
Spotify recommendation engine: building search queries per emotion, ranking
and blending candidate tracks, curated/user fallbacks, and the top-level
get_recommendations_with_details orchestration.
"""
import logging
import random
import re
import time

from .auth import SpotifyAuthError
from . import pool
from .utils import (
    _append_unique_tracks,
    _canonical_track_title,
    _clamp_spotify_search_limit,
    _compact_failure,
    _history_allows_learning,
    _normalize_playable_item,
    _normalize_taste_profile,
    _safe_int,
    _taste_discovery_bonus,
    _taste_instrumental_bonus,
    _is_non_music_track,
    _track_match_key,
    _unique_text_values,
)
from .constants import (
    EMOTION_SEARCH_PARAMS,
    EMOTION_QUERY_PROFILES,
    EMOTION_ALIGNMENT_HINTS,
    EMOTION_SELECTION_REASON_WEIGHTS,
    EMOTION_SPECIFIC_PERSONALIZATION_REASONS,
    EMOTION_SOURCE_WEIGHTS,
    CURATED_CONTEXT_LIBRARY,
    CURATED_PLAYABLE_CONTEXTS,
    MUSIC_PICKER_DOC_SEED_SOURCE,
    MUSIC_PICKER_DOC_SEED_TRACKS,
    HAPPY_SEED_TRACKS,
    SAD_SEED_TRACKS,
    ANGRY_SEED_TRACKS,
    MOTIVATIONAL_SEED_TRACKS,
    SOOTHING_SEED_TRACKS,
    SURPRISING_SEED_TRACKS,
    ROMANTIC_SEED_TRACKS,
    NOSTALGIC_SEED_TRACKS,
    FEAR_SEED_TRACKS,
    DEPRESSING_SEED_TRACKS,
    STRESSED_SEED_TRACKS,
    CALM_SEED_TRACKS,
    LONELY_SEED_TRACKS,
)

logger = logging.getLogger('api.spotify_service')

# Sources that are the same for everyone regardless of what Spotify holds.
STATIC_TRACK_SOURCES = frozenset({'curated_fallback'})

# What a track resolved from the docs/music.md list is tagged with.
MUSIC_DOC_TRACK_SOURCE = 'music_md_playlist'
MUSIC_DOC_SEED_REASON = 'music_md_playlist_seed'


def _without_static_tracks(tracks):
    """Drop the hardcoded curated tracks from a candidate group."""
    return [
        track for track in (tracks or [])
        if str((track or {}).get('recommendation_source') or '').strip().lower()
        not in STATIC_TRACK_SOURCES
    ]


def _shuffled(tracks):
    """Return a shuffled copy; isolated so tests can pin the order."""
    shuffled = list(tracks or [])
    random.shuffle(shuffled)
    return shuffled


def _music_doc_seeds(emotion):
    """The docs/music.md songs for an emotion as (title, artist) match keys."""
    seeds = MUSIC_PICKER_DOC_SEED_TRACKS.get(str(emotion or '').strip().lower()) or []
    return [
        (
            _canonical_track_title(seed.get('track')),
            str(seed.get('artist') or '').strip().lower(),
        )
        for seed in seeds
        if _canonical_track_title(seed.get('track'))
    ]


def _music_doc_position(track, seeds):
    """Where a track sits in the document, or None when it is not on it."""
    title = _canonical_track_title(
        track.get('playlist_seed_track') or track.get('name')
    )
    if not title:
        return None

    artist = str(
        track.get('playlist_seed_artist') or track.get('artist') or ''
    ).strip().lower()
    for position, (seed_title, seed_artist) in enumerate(seeds):
        if seed_title != title:
            continue
        if (
            not seed_artist
            or not artist
            or seed_artist in artist
            or artist in seed_artist
        ):
            return position
    return None


def music_doc_tracks(tracks, emotion, limit=None):
    """The docs/music.md songs for this emotion, in document order.

    "Balanced" is the lane that promises that static per-emotion list, so the
    blender and the taste-control pass in views both need the same answer to
    "which of these candidates came from the document". Matches come back
    flagged, so the app can say which songs are the static ones -- a document
    song that Spotify returned for a mood phrase rather than for its own title
    query carries no seed metadata of its own.
    """
    seeds = _music_doc_seeds(emotion)
    if not seeds:
        return []

    matched = []
    seen_keys = set()
    for track in tracks or []:
        if not isinstance(track, dict):
            continue
        position = _music_doc_position(track, seeds)
        if position is None:
            continue
        key = track.get('uri') or track.get('id')
        if key:
            if key in seen_keys:
                continue
            seen_keys.add(key)
        matched.append((position, len(matched), track))

    matched.sort(key=lambda item: (item[0], item[1]))
    ordered = [{**track, 'is_music_doc_pick': True} for _, _, track in matched]
    return ordered[:limit] if limit else ordered


def familiar_favorite_quota(limit):
    """How many hearted favorites "More familiar" may take of one playlist.

    The favorites still open the session -- the first song hearted for an
    emotion is the first one heard when that emotion comes back -- but they
    never fill it. Half the slots stay reserved for songs the user has not
    heard yet, so the lane keeps recommending new music as the favorites for
    an emotion pile up.
    """
    slots = max(_safe_int(limit, 0), 0) or 20
    return max(slots // 2, 1)


def _pool_candidates(
    pool_tracks,
    *,
    emotion,
    limit,
    seen_track_ids,
    seen_track_match_keys,
    taste_profile,
):
    """Sample the shared pool, leading with the document list for Balanced.

    The pool is built from the same queries a live request runs, so it already
    holds this emotion's docs/music.md songs -- but a random sample of six out
    of a hundred almost never contains one, which is how Balanced ended up
    opening on an arbitrary pooled track instead of the list it promises.
    """
    if limit <= 0:
        return []

    normalized_taste = _normalize_taste_profile(taste_profile)
    leads = []
    if (
        normalized_taste.get('familiarity') == 'balanced'
        and not normalized_taste.get('prefer_instrumental')
    ):
        working_ids = set(seen_track_ids or ())
        working_keys = set(seen_track_match_keys or ())
        for track in music_doc_tracks(
            pool_tracks, emotion, limit=max(limit // 2, 1),
        ):
            track_id = track.get('id')
            match_key = _track_match_key(track)
            if not track_id or track_id in working_ids:
                continue
            if match_key and match_key in working_keys:
                continue
            working_ids.add(track_id)
            if match_key:
                working_keys.add(match_key)
            leads.append(track)
        seen_track_ids = working_ids
        seen_track_match_keys = working_keys

    sampled = pool.sample_tracks(
        pool_tracks,
        limit=max(limit - len(leads), 0),
        seen_track_ids=seen_track_ids,
        seen_track_match_keys=seen_track_match_keys,
    )
    return leads + sampled


class SpotifyRecommendationEngine:
    def __init__(self, service):
        self.service = service

    def _build_recommendation_queries(
        self,
        emotion,
        preferred_artists=None,
        top_emotions=None,
        all_scores=None,
        llm_queries=None,
        playlist_category=None,
        seed_artist_name=None,
        seed_track_name=None,
        query_mode='default',
        taste_profile=None,
    ):
        """Build layered Spotify search queries from strongest to broadest match."""
        normalized_emotion = str(emotion or 'mixed').strip().lower() or 'mixed'
        normalized_query_mode = str(query_mode or 'default').strip().lower() or 'default'
        continuation_mode = normalized_query_mode == 'continuation'
        emotion_candidates = [normalized_emotion]
        for item in top_emotions or []:
            if not isinstance(item, dict):
                continue
            item_emotion = str(item.get('emotion') or '').strip().lower()
            if item_emotion and item_emotion not in emotion_candidates:
                emotion_candidates.append(item_emotion)
            if len(emotion_candidates) >= 3:
                break

        if isinstance(all_scores, dict):
            scored_emotions = []
            for emotion_name, score in all_scores.items():
                normalized_name = str(emotion_name or '').strip().lower()
                if not normalized_name or normalized_name in emotion_candidates:
                    continue
                try:
                    normalized_score = float(score)
                except (TypeError, ValueError):
                    continue
                scored_emotions.append((normalized_name, normalized_score))
            scored_emotions.sort(key=lambda item: (-item[1], item[0]))
            for emotion_name, score in scored_emotions:
                if score < 0.14:
                    continue
                emotion_candidates.append(emotion_name)
                if len(emotion_candidates) >= 4:
                    break

        artists = [a.strip() for a in (preferred_artists or []) if str(a).strip()]
        playlist_category = ' '.join(str(playlist_category or '').strip().split())
        normalized_llm_queries = [
            ' '.join(str(query or '').strip().split())
            for query in (llm_queries or [])
            if ' '.join(str(query or '').strip().split())
        ]

        primary_profile = EMOTION_QUERY_PROFILES.get(
            normalized_emotion,
            EMOTION_QUERY_PROFILES['mixed'],
        )

        queries = []

        # "Prefer instrumental" has to reach the search, not just the ranking:
        # no amount of re-ordering turns a pool of vocal pop into instrumental
        # music. A request only gets through the first handful of queries before
        # its candidate slots or its time budget run out, so these open the list
        # in both stages -- the per-emotion document songs are all vocal, and
        # this listener asked for the opposite.
        #
        # The emotion word alone is a poor instrumental query: "mixed
        # instrumental" comes back as songs titled "Mixed Signals". The mood
        # phrase and a genre filter return music that is actually instrumental,
        # and usually says so in its title -- which is the only instrumental
        # signal available, because Spotify's audio-features endpoint answers
        # 403 for apps registered after November 2024.
        if _normalize_taste_profile(taste_profile).get('prefer_instrumental'):
            instrumental_phrase = (
                primary_profile.get('phrases', [normalized_emotion])[0]
                if isinstance(primary_profile, dict)
                else normalized_emotion
            )
            queries.extend([
                f'instrumental {instrumental_phrase}',
                'genre:"ambient" instrumental',
                f'{instrumental_phrase} piano instrumental',
            ])

        if continuation_mode:
            queries.extend(
                self.service._build_curated_emotion_queries(
                    normalized_emotion,
                    playlist_category=playlist_category,
                    exact_seed_limit=self.service.emotion_seed_track_limit,
                    phrase_limit=4,
                )
            )
            queries.extend(normalized_llm_queries)
        else:
            queries.extend(
                self.service._build_seed_track_queries(
                    seed_track_name=seed_track_name,
                    seed_artist_name=seed_artist_name,
                    emotion=normalized_emotion,
                    playlist_category=playlist_category,
                )
            )
            queries.extend(normalized_llm_queries)

        queries.extend(
            self.service._build_curated_emotion_queries(
                normalized_emotion,
                playlist_category=playlist_category,
                exact_seed_limit=0 if continuation_mode else self.service.emotion_seed_track_limit,
                phrase_limit=4 if continuation_mode else 3,
            )
        )

        if playlist_category:
            queries.append(playlist_category)
            if playlist_category.lower() != normalized_emotion:
                queries.append(f'{normalized_emotion} {playlist_category}')

        for emotion_name in emotion_candidates[1:3]:
            queries.extend(
                self.service._build_curated_emotion_queries(
                    emotion_name,
                    playlist_category=playlist_category,
                    exact_seed_limit=0 if continuation_mode else min(self.service.emotion_seed_track_limit, 3),
                    phrase_limit=2 if continuation_mode else 1,
                )
            )
            if emotion_name != normalized_emotion:
                queries.append(f'{normalized_emotion} {emotion_name} songs')

        primary_phrase = (
            primary_profile.get('phrases', [normalized_emotion])[0]
            if isinstance(primary_profile, dict)
            else normalized_emotion
        )
        fallback_terms = list(
            dict.fromkeys(
                (primary_profile.get('fallback') if isinstance(primary_profile, dict) else None)
                or [f'{normalized_emotion} songs', normalized_emotion]
            )
        )

        for artist in artists[:3]:
            queries.append(f'artist:"{artist}" {primary_phrase}')
            queries.append(f'artist:"{artist}" {normalized_emotion}')
            if playlist_category:
                queries.append(f'artist:"{artist}" {playlist_category}')

        for emotion_name in emotion_candidates[:3]:
            emotion_params = EMOTION_SEARCH_PARAMS.get(
                emotion_name,
                EMOTION_SEARCH_PARAMS['mixed'],
            )
            keywords = list(
                dict.fromkeys(emotion_params.get('keywords', [])[:2] or [emotion_name])
            )
            genres = list(dict.fromkeys(emotion_params.get('genres', [])[:2]))

            for keyword, genre in zip(keywords, genres):
                queries.append(f'genre:"{genre}" {keyword}')
            for keyword in keywords:
                queries.append(keyword)
                if emotion_name != keyword:
                    queries.append(f'{emotion_name} {keyword}')

        if len(emotion_candidates) >= 2:
            blended_pair = ' '.join(emotion_candidates[:2])
            queries.append(blended_pair)
            if playlist_category:
                queries.append(f'{playlist_category} {blended_pair}')

        queries.extend(fallback_terms)
        queries.append(normalized_emotion)
        queries.append(f'{normalized_emotion} music')

        ordered_unique_queries = []
        seen = set()
        for query in queries:
            normalized = query.strip().lower()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            ordered_unique_queries.append(query)
        return ordered_unique_queries

    def _build_curated_emotion_queries(
        self,
        emotion,
        *,
        playlist_category='',
        exact_seed_limit=2,
        phrase_limit=2,
    ):
        profile = EMOTION_QUERY_PROFILES.get(
            str(emotion or 'mixed').strip().lower() or 'mixed',
            EMOTION_QUERY_PROFILES['mixed'],
        )
        queries = []
        seed_tracks = self.service._select_seed_tracks(
            profile.get('seed_tracks') or [],
            max(exact_seed_limit, 0),
        )

        for seed in seed_tracks:
            if not isinstance(seed, dict):
                continue
            queries.extend(
                self.service._build_exact_track_queries(
                    track_name=seed.get('track'),
                    artist_name=seed.get('artist'),
                )
            )

        for phrase in (profile.get('phrases') or [])[: max(phrase_limit, 0)]:
            normalized_phrase = ' '.join(str(phrase or '').strip().split())
            if not normalized_phrase:
                continue
            queries.append(normalized_phrase)
            if playlist_category and playlist_category.lower() not in normalized_phrase.lower():
                queries.append(f'{normalized_phrase} {playlist_category}')

        return queries

    def _select_seed_tracks(self, seed_tracks, limit):
        if limit <= 0:
            return []

        normalized_seed_tracks = [
            seed
            for seed in (seed_tracks or [])
            if isinstance(seed, dict)
        ]
        if len(normalized_seed_tracks) <= limit:
            return normalized_seed_tracks
        if limit == 1:
            return normalized_seed_tracks[:1]

        selected = []
        seen_indexes = set()
        max_index = len(normalized_seed_tracks) - 1
        for position in range(limit):
            index = round((max_index * position) / max(limit - 1, 1))
            if index in seen_indexes:
                continue
            seen_indexes.add(index)
            selected.append(normalized_seed_tracks[index])

        if len(selected) >= limit:
            return selected[:limit]

        for index, seed in enumerate(normalized_seed_tracks):
            if index in seen_indexes:
                continue
            selected.append(seed)
            if len(selected) >= limit:
                break
        return selected

    def _build_seed_track_queries(
        self,
        *,
        seed_track_name=None,
        seed_artist_name=None,
        emotion='mixed',
        playlist_category='',
    ):
        if not self.service.llm_exact_seed_enabled:
            return []

        queries = self.service._build_exact_track_queries(
            track_name=seed_track_name,
            artist_name=seed_artist_name,
        )
        if not queries:
            return []

        if playlist_category and seed_track_name:
            queries.append(
                f'"{str(seed_track_name or "").strip().replace(chr(34), "")}" {playlist_category}'
            )
        elif playlist_category and seed_artist_name:
            queries.append(
                f'artist:"{str(seed_artist_name or "").strip().replace(chr(34), "")}" {playlist_category}'
            )
        elif seed_artist_name and not seed_track_name:
            queries.append(
                f'artist:"{str(seed_artist_name or "").strip().replace(chr(34), "")}" {emotion}'
            )

        return queries[:self.service.llm_exact_seed_query_limit]

    def _build_exact_track_queries(
        self,
        *,
        track_name=None,
        artist_name=None,
    ):
        track_name = str(track_name or '').strip().replace('"', '')
        artist_name = str(artist_name or '').strip().replace('"', '')
        if not track_name and not artist_name:
            return []

        queries = []
        if track_name and artist_name:
            queries.extend([
                f'track:"{track_name}" artist:"{artist_name}"',
                f'"{track_name}" "{artist_name}"',
                f'artist:"{artist_name}" "{track_name}"',
            ])
        elif track_name:
            queries.extend([
                f'track:"{track_name}"',
                f'"{track_name}"',
            ])
        elif artist_name:
            queries.append(f'artist:"{artist_name}"')

        return queries

    def _extract_exact_query_constraints(self, query):
        normalized_query = str(query or '').strip()
        if not normalized_query:
            return None, None

        title_match = re.search(r'track:\"([^\"]+)\"', normalized_query, flags=re.IGNORECASE)
        artist_match = re.search(r'artist:\"([^\"]+)\"', normalized_query, flags=re.IGNORECASE)
        if title_match or artist_match:
            return (
                _canonical_track_title(title_match.group(1) if title_match else ''),
                str(artist_match.group(1) if artist_match else '').strip().lower() or None,
            )

        quoted_parts = re.findall(r'"([^"]+)"', normalized_query)
        if len(quoted_parts) >= 2:
            return (
                _canonical_track_title(quoted_parts[0]),
                str(quoted_parts[1]).strip().lower() or None,
            )
        if len(quoted_parts) == 1:
            return _canonical_track_title(quoted_parts[0]), None
        return None, None

    def _seed_metadata_for_query(self, emotion, query):
        title_constraint, artist_constraint = self.service._extract_exact_query_constraints(query)
        if not title_constraint:
            return None

        normalized_emotion = str(emotion or 'mixed').strip().lower() or 'mixed'
        profile = EMOTION_QUERY_PROFILES.get(
            normalized_emotion,
            EMOTION_QUERY_PROFILES['mixed'],
        )

        for seed in profile.get('seed_tracks') or []:
            if not isinstance(seed, dict):
                continue
            seed_title = _canonical_track_title(seed.get('track'))
            seed_artist = str(seed.get('artist') or '').strip().lower()
            if seed_title != title_constraint:
                continue
            if artist_constraint and artist_constraint not in seed_artist:
                continue
            return {
                'emotion': normalized_emotion,
                'track': str(seed.get('track') or '').strip(),
                'artist': str(seed.get('artist') or '').strip(),
                'source': str(seed.get('source') or '').strip(),
            }
        return None

    def _annotate_tracks_for_query(self, query, tracks, *, emotion):
        seed_metadata = self.service._seed_metadata_for_query(emotion, query)
        if not seed_metadata:
            return list(tracks or [])

        source = (
            'music_md_playlist'
            if seed_metadata.get('source') == MUSIC_PICKER_DOC_SEED_SOURCE
            else 'curated_seed'
        )
        seed_reason = (
            'music_md_playlist_seed'
            if source == 'music_md_playlist'
            else 'curated_seed'
        )

        annotated_tracks = []
        for track in tracks or []:
            if not isinstance(track, dict):
                continue
            annotated_track = dict(track)
            annotated_track['recommendation_source'] = source
            annotated_track['selection_reasons'] = _unique_text_values([
                *(annotated_track.get('selection_reasons') or []),
                seed_reason,
            ])
            annotated_track['playlist_seed_emotion'] = seed_metadata['emotion']
            annotated_track['playlist_seed_track'] = seed_metadata['track']
            annotated_track['playlist_seed_artist'] = seed_metadata['artist']
            annotated_tracks.append(annotated_track)
        return annotated_tracks

    def _filter_tracks_for_query(self, query, tracks, *, strict=False):
        title_constraint, artist_constraint = self.service._extract_exact_query_constraints(query)
        if not title_constraint and not artist_constraint:
            return list(tracks or [])

        filtered = []
        for track in tracks or []:
            if not isinstance(track, dict):
                continue
            track_title = _canonical_track_title(track.get('name'))
            track_artist = str(track.get('artist') or '').strip().lower()

            if title_constraint and track_title != title_constraint:
                continue
            if artist_constraint and artist_constraint not in track_artist:
                continue
            filtered.append(track)

        return filtered or ([] if strict else list(tracks or []))

    def _build_saved_track_reference(
        self,
        track_id,
        name,
        artist,
        *,
        album='',
        image='',
        preview_url=None,
        duration_ms=0,
        source='saved_track',
        extra=None,
    ):
        item = _normalize_playable_item(
            {
                'id': track_id,
                'item_type': 'track',
                'name': name,
                'artist': artist,
                'album': album,
                'image': image,
                'preview_url': preview_url,
                'duration_ms': duration_ms,
            },
            default_source=source,
        )
        if item and extra:
            item.update(extra)
        return item

    def sanitize_recommendations(self, tracks, limit=20):
        """Normalize mixed recommendation payloads into directly playable items."""
        sanitized = []
        seen_keys = set()
        seen_match_keys = set()
        for candidate in tracks or []:
            if not isinstance(candidate, dict):
                continue
            item = _normalize_playable_item(
                candidate,
                default_source=candidate.get('recommendation_source', 'spotify'),
            )
            if not item:
                continue
            item_key = item.get('uri') or item.get('id')
            if not item_key or item_key in seen_keys:
                continue
            match_key = _track_match_key(item)
            if match_key and match_key in seen_match_keys:
                continue
            seen_keys.add(item_key)
            if match_key:
                seen_match_keys.add(match_key)
            sanitized.append(item)
            if len(sanitized) >= limit:
                break
        return sanitized[:limit]

    def _emotion_candidate_weight_map(
        self,
        emotion,
        top_emotions=None,
        confidence_band='high',
    ):
        weights = {}
        normalized_emotion = str(emotion or 'mixed').strip().lower() or 'mixed'
        weights[normalized_emotion] = 1.0

        secondary_weight = {
            'high': 0.18,
            'medium': 0.28,
            'low': 0.38,
        }.get(str(confidence_band or 'high').strip().lower(), 0.25)

        for item in top_emotions or []:
            if not isinstance(item, dict):
                continue
            item_emotion = str(item.get('emotion') or '').strip().lower()
            if not item_emotion or item_emotion == normalized_emotion:
                continue
            item_confidence = max(min(float(item.get('confidence') or 0.0), 1.0), 0.0)
            weights[item_emotion] = max(
                weights.get(item_emotion, 0.0),
                round(item_confidence * secondary_weight, 4),
            )

        if str(confidence_band or '').strip().lower() == 'low':
            weights['mixed'] = max(weights.get('mixed', 0.0), 0.35)

        return weights

    def rank_tracks_for_emotion(
        self,
        tracks,
        *,
        emotion,
        top_emotions=None,
        preferred_artists=None,
        confidence_band='high',
        limit=20,
        taste_profile=None,
        preserve_order=False,
    ):
        """Score candidates for an emotion, best first.

        ``preserve_order`` keeps the caller's order instead of sorting by score;
        favorites are ranked only to pick up their scoring metadata, and their
        order (oldest favorite first) is the point.
        """
        sanitized = self.service.sanitize_recommendations(tracks or [], limit=max(limit * 2, limit))
        if not sanitized:
            return []

        preferred_artist_terms = {
            str(artist or '').strip().lower()
            for artist in (preferred_artists or [])
            if str(artist or '').strip()
        }
        normalized_taste_profile = _normalize_taste_profile(taste_profile)

        # The docs/music.md lane is boosted twice: once as a source weight
        # (3.4, against 1.2 for the catalog) and again as a selection reason
        # (3.0). That is right for the default lane, but two taste settings
        # explicitly opt out of it, and both boosts have to go with it or the
        # setting is only half honoured.
        #
        #   instrumental -- the document list is vocal pop.
        #   discovery    -- a static list outranking real catalog finds is the
        #                   opposite of the request. Blending already drops the
        #                   document lane here, but these tracks also arrive
        #                   through the cached pool, where nothing demotes them.
        opted_out_of_document_lane = bool(
            normalized_taste_profile.get('prefer_instrumental')
            or normalized_taste_profile.get('familiarity') == 'discovery'
        )
        emotion_weights = self.service._emotion_candidate_weight_map(
            emotion,
            top_emotions=top_emotions,
            confidence_band=confidence_band,
        )

        ranked = []
        for index, raw_track in enumerate(sanitized):
            track = dict(raw_track)
            score = 0.0
            reasons = []

            item_type = str(track.get('item_type') or 'track').strip().lower()
            if item_type == 'track':
                score += 1.0
                reasons.append('direct_track')
            else:
                score -= 4.0
                reasons.append('non_track_penalty')

            base_source = str(track.get('recommendation_source') or '').strip()
            source_weight = EMOTION_SOURCE_WEIGHTS.get(base_source, 1.0)
            if opted_out_of_document_lane and base_source.lower() == MUSIC_DOC_TRACK_SOURCE:
                # Rank as an ordinary catalog track instead.
                source_weight = EMOTION_SOURCE_WEIGHTS['spotify_catalog']
            if source_weight:
                score += source_weight
                if base_source:
                    reasons.append(f'source:{base_source}')

            score += float(track.get('personalization_score', 0.0) or 0.0)
            if float(track.get('personalization_score', 0.0) or 0.0) > 0:
                reasons.append('personalization_score')

            selection_reasons = [
                str(reason or '').strip()
                for reason in (track.get('selection_reasons') or [])
                if str(reason or '').strip()
            ]
            for selection_reason in selection_reasons:
                if (
                    opted_out_of_document_lane
                    and selection_reason == MUSIC_DOC_SEED_REASON
                ):
                    # The other half of the document-lane boost. Dropping the
                    # source weight alone still left this one standing.
                    continue
                weight = EMOTION_SELECTION_REASON_WEIGHTS.get(selection_reason)
                if weight:
                    score += weight
                    reasons.append(f'reason:{selection_reason}')

            if track.get('is_preferred'):
                score += 1.6
                reasons.append('preferred_seed')

            text_blob = ' '.join([
                str(track.get('name') or '').strip().lower(),
                str(track.get('artist') or '').strip().lower(),
                str(track.get('album') or '').strip().lower(),
                base_source.lower(),
                ' '.join(selection_reasons).lower(),
            ]).strip()

            for weighted_emotion, weight in emotion_weights.items():
                profile = EMOTION_SEARCH_PARAMS.get(
                    weighted_emotion,
                    EMOTION_SEARCH_PARAMS['mixed'],
                )
                hints = EMOTION_ALIGNMENT_HINTS.get(
                    weighted_emotion,
                    EMOTION_ALIGNMENT_HINTS['mixed'],
                )
                keyword_hits = 0
                for keyword in profile.get('keywords', []):
                    keyword_text = str(keyword or '').strip().lower()
                    if keyword_text and keyword_text in text_blob:
                        keyword_hits += 1
                if keyword_hits:
                    score += min(keyword_hits, 3) * 0.8 * weight
                    reasons.append(f'keyword_fit:{weighted_emotion}')

                genre_hits = 0
                for genre in profile.get('genres', []):
                    genre_text = str(genre or '').strip().lower()
                    if genre_text and genre_text in text_blob:
                        genre_hits += 1
                if genre_hits:
                    score += min(genre_hits, 2) * 0.55 * weight
                    reasons.append(f'genre_fit:{weighted_emotion}')

                boost_hits = 0
                for term in hints.get('boost_terms', []):
                    term_text = str(term or '').strip().lower()
                    if term_text and term_text in text_blob:
                        boost_hits += 1
                if boost_hits:
                    score += min(boost_hits, 2) * 0.45 * weight
                    reasons.append(f'profile_fit:{weighted_emotion}')

                avoid_hits = 0
                for term in hints.get('avoid_terms', []):
                    term_text = str(term or '').strip().lower()
                    if term_text and term_text in text_blob:
                        avoid_hits += 1
                if avoid_hits:
                    score -= min(avoid_hits, 2) * 0.65 * weight
                    reasons.append(f'avoid_penalty:{weighted_emotion}')

            artist_text = str(track.get('artist') or '').strip().lower()
            if preferred_artist_terms and any(
                artist_term in artist_text
                for artist_term in preferred_artist_terms
            ):
                score += 1.2
                reasons.append('preferred_artist_runtime')

            discovery_bonus, discovery_reason = _taste_discovery_bonus(
                track,
                normalized_taste_profile,
            )
            score += discovery_bonus
            if discovery_reason:
                reasons.append(discovery_reason)

            instrumental_bonus, instrumental_reason = _taste_instrumental_bonus(
                text_blob,
                normalized_taste_profile,
            )
            score += instrumental_bonus
            if instrumental_reason:
                reasons.append(instrumental_reason)

            popularity = min(max(_safe_int(track.get('popularity'), 0), 0), 100)
            score += popularity / 1000.0

            score -= index * 0.01

            unique_reasons = []
            seen_reasons = set()
            for reason in reasons:
                if reason in seen_reasons:
                    continue
                seen_reasons.add(reason)
                unique_reasons.append(reason)

            track['emotion_alignment_score'] = round(score, 3)
            track['emotion_alignment_reasons'] = unique_reasons
            ranked.append(track)

        if not preserve_order:
            ranked.sort(
                key=lambda item: (
                    -float(item.get('emotion_alignment_score', 0.0)),
                    -float(item.get('personalization_score', 0.0)),
                    -float(item.get('popularity', 0) or 0),
                    str(item.get('name') or '').lower(),
                )
            )
        return ranked[:limit]

    def blend_recommendation_groups(
        self,
        *,
        emotion,
        personalized_tracks=None,
        search_tracks=None,
        fallback_tracks=None,
        preferred_artists=None,
        limit=20,
        taste_profile=None,
        user=None,
    ):
        familiarity = _normalize_taste_profile(taste_profile).get('familiarity')

        # "More discovery" asks for real catalog music, so the curated list --
        # the same static tracks every user would get -- is dropped before
        # ranking. It only comes back when it is the only thing left to play.
        if familiarity == 'discovery':
            fresh_search = _without_static_tracks(search_tracks)
            fresh_personalized = _without_static_tracks(personalized_tracks)
            fresh_fallback = _without_static_tracks(fallback_tracks)
            if fresh_search or fresh_personalized or fresh_fallback:
                search_tracks = fresh_search
                personalized_tracks = fresh_personalized
                fallback_tracks = fresh_fallback

        personalized_ranked = self.service.rank_tracks_for_emotion(
            personalized_tracks or [],
            emotion=emotion,
            preferred_artists=preferred_artists,
            confidence_band='medium',
            limit=max(limit * 2, limit),
            taste_profile=taste_profile,
        )
        search_ranked = self.service.rank_tracks_for_emotion(
            search_tracks or [],
            emotion=emotion,
            preferred_artists=preferred_artists,
            confidence_band='medium',
            limit=max(limit * 2, limit),
            taste_profile=taste_profile,
        )
        fallback_ranked = self.service.rank_tracks_for_emotion(
            fallback_tracks or [],
            emotion=emotion,
            preferred_artists=preferred_artists,
            confidence_band='medium',
            limit=max(limit * 2, limit),
            taste_profile=taste_profile,
        )

        if not personalized_ranked and not search_ranked and not fallback_ranked:
            return []

        # Discovery shuffles the ranked pools so the same emotion does not
        # replay the same opening tracks on every request.
        if familiarity == 'discovery':
            personalized_ranked = _shuffled(personalized_ranked)
            search_ranked = _shuffled(search_ranked)
            fallback_ranked = _shuffled(fallback_ranked)

        blended = []
        seen_keys = set()

        def append_from(group, quota):
            added = 0
            for item in group:
                item_key = item.get('uri') or item.get('id')
                if not item_key or item_key in seen_keys:
                    continue
                seen_keys.add(item_key)
                blended.append(item)
                added += 1
                if added >= quota or len(blended) >= limit:
                    break

        non_mixed_emotion = str(emotion or 'mixed').strip().lower() != 'mixed'

        if familiarity == 'familiar':
            # Open with what the user already hearted under this emotion,
            # oldest favorite first, then fill the rest normally. The quota
            # keeps the favorites from swallowing the playlist once there are
            # more of them than there are slots.
            favorite_quota = familiar_favorite_quota(limit)
            favorite_leads = self.service.rank_tracks_for_emotion(
                self._build_emotion_favorite_tracks(
                    emotion,
                    user=user,
                    limit=favorite_quota,
                ),
                emotion=emotion,
                preferred_artists=preferred_artists,
                confidence_band='medium',
                limit=favorite_quota,
                taste_profile=taste_profile,
                preserve_order=True,
            )
            append_from(favorite_leads, favorite_quota)

            search_quota = min(len(search_ranked), max(1 if non_mixed_emotion else 0, limit // 3))
            fallback_quota = min(len(fallback_ranked), max(1, limit // 5)) if fallback_ranked and not search_ranked else 0
        elif familiarity == 'discovery':
            search_quota = min(len(search_ranked), max(3 if non_mixed_emotion else 2, (limit * 3) // 5))
            fallback_quota = min(len(fallback_ranked), max(2, limit // 4)) if fallback_ranked and not search_ranked else 0
        else:
            # Balanced is the static lane: the docs/music.md songs for this
            # emotion open the playlist in document order, and the ranked picks
            # fill in behind them. Not when the listener asked for instrumental
            # music, though -- that list is vocal pop, and the explicit ask
            # wins over the default lane.
            if not _normalize_taste_profile(taste_profile).get('prefer_instrumental'):
                append_from(
                    music_doc_tracks(
                        [*search_ranked, *personalized_ranked, *fallback_ranked],
                        emotion,
                        limit=max(limit // 2, 1),
                    ),
                    limit,
                )

            if search_ranked:
                search_quota = min(
                    len(search_ranked),
                    max(2 if non_mixed_emotion else 1, limit // 2),
                )
            else:
                search_quota = 0
            fallback_quota = 0
            if fallback_ranked and not search_ranked:
                fallback_quota = min(
                    len(fallback_ranked),
                    max(2 if non_mixed_emotion else 1, limit // 2),
                )

        personalized_quota = min(
            len(personalized_ranked),
            max(limit - search_quota - fallback_quota, 0),
        )

        if search_quota:
            append_from(search_ranked, search_quota)
        elif fallback_quota:
            append_from(fallback_ranked, fallback_quota)

        if personalized_quota:
            append_from(personalized_ranked, personalized_quota)

        if len(blended) < limit:
            append_from(search_ranked, limit)
        if len(blended) < limit:
            append_from(fallback_ranked, limit)
        if len(blended) < limit:
            append_from(personalized_ranked, limit)

        return blended[:limit]

    def select_primary_track(self, tracks):
        """Pick the single best directly playable track candidate."""
        sanitized = self.service.sanitize_recommendations(tracks or [], limit=max(len(tracks or []), 1))
        if not sanitized:
            return None

        track_candidates = [
            track for track in sanitized
            if str(track.get('item_type') or '').strip().lower() == 'track'
        ]
        ranked_candidates = track_candidates or sanitized
        return dict(ranked_candidates[0]) if ranked_candidates else None

    def _build_emotion_favorite_tracks(self, emotion, user=None, limit=20):
        """Favorites hearted under this emotion, oldest first.

        Order matters: the user asked that the first song they favorited for an
        emotion is the first one they hear the next time that emotion comes up.
        """
        if not user or not getattr(user, 'is_authenticated', False):
            return []

        normalized_emotion = str(emotion or '').strip().lower()
        if not normalized_emotion:
            return []

        from users.models import FavoriteTrack

        tracks = []
        seen_keys = set()
        favorites = FavoriteTrack.objects.filter(
            user=user,
            emotion=normalized_emotion,
        ).order_by('added_at')[:limit]
        for favorite in favorites:
            _append_unique_tracks(
                tracks,
                seen_keys,
                [
                    self.service._build_saved_track_reference(
                        favorite.spotify_track_id,
                        favorite.track_name,
                        favorite.artist_name,
                        album=favorite.album_name,
                        image=favorite.album_image,
                        preview_url=favorite.preview_url,
                        duration_ms=favorite.duration_ms,
                        source='favorite_track',
                        extra={'is_favorite': True, 'favorite_emotion': normalized_emotion},
                    )
                ],
                limit,
            )
            if len(tracks) >= limit:
                break
        return tracks

    def _build_user_fallback_tracks(self, emotion, user=None, limit=20):
        if not user:
            return []

        from users.models import FavoriteTrack, PromptHistory, UserPreference

        tracks = []
        seen_keys = set()

        preferences = UserPreference.objects.filter(
            user=user,
            emotion=emotion,
        ).order_by('-play_count', '-last_played')[:limit]
        for pref in preferences:
            _append_unique_tracks(
                tracks,
                seen_keys,
                [
                    self.service._build_saved_track_reference(
                        pref.spotify_track_id,
                        pref.track_name,
                        pref.artist_name,
                        source='user_preference',
                        extra={'is_preferred': True},
                    )
                ],
                limit,
            )
            if len(tracks) >= limit:
                return tracks

        histories = PromptHistory.objects.filter(
            user=user,
            detected_emotion=emotion,
        ).order_by('-created_at')[:5]
        for history in histories:
            if not _history_allows_learning(history):
                continue
            playlist_data = history.playlist_data if isinstance(history.playlist_data, list) else []
            # Skip the static curated playlists a past fallback stored: they say
            # nothing about this listener, and replaying them kept serving the
            # old padded list (with "Sad Songs") to happy users long after the
            # padding was removed. The curated step below adds today's set.
            learned = [
                track for track in playlist_data
                if not (isinstance(track, dict) and track.get('recommendation_source') == 'curated_fallback')
            ]
            _append_unique_tracks(tracks, seen_keys, learned, limit)
            if len(tracks) >= limit:
                return tracks

        favorites = FavoriteTrack.objects.filter(user=user).order_by('-added_at')[:limit]
        for favorite in favorites:
            _append_unique_tracks(
                tracks,
                seen_keys,
                [
                    self.service._build_saved_track_reference(
                        favorite.spotify_track_id,
                        favorite.track_name,
                        favorite.artist_name,
                        album=favorite.album_name,
                        image=favorite.album_image,
                        preview_url=favorite.preview_url,
                        duration_ms=favorite.duration_ms,
                        source='favorite_track',
                    )
                ],
                limit,
            )
            if len(tracks) >= limit:
                return tracks

        return tracks

    def _build_curated_fallback_tracks(self, emotion, limit=20):
        # Only this emotion's own playlists. This used to pad every emotion with
        # the 'mixed' list, whose first entry is Sad Songs, so a happy, angry,
        # calm or stressed listener got "Sad Songs" whenever search fell back.
        # A shorter list beats a mismatched one; choosing related playlists to
        # pad with would be a music-therapy decision, not a code default.
        context_keys = CURATED_PLAYABLE_CONTEXTS.get(emotion) or CURATED_PLAYABLE_CONTEXTS['mixed']

        tracks = []
        seen_keys = set()
        for context_key in context_keys:
            context = CURATED_CONTEXT_LIBRARY.get(context_key)
            if not context:
                continue
            _append_unique_tracks(
                tracks,
                seen_keys,
                [{**context, 'recommendation_source': 'curated_fallback'}],
                limit,
            )
            if len(tracks) >= limit:
                break
        return tracks

    def _build_fallback_tracks(
        self,
        emotion,
        user=None,
        preferred_artists=None,
        limit=20,
        taste_profile=None,
    ):
        """Return directly playable fallbacks when Spotify search fails."""
        tracks = []
        seen_keys = set()

        _append_unique_tracks(
            tracks,
            seen_keys,
            self.service._build_user_fallback_tracks(emotion, user=user, limit=limit),
            limit,
        )

        # Discovery would rather have a short playlist of real catalog tracks
        # than the static curated list, so it only tops up when nothing else
        # was found at all.
        familiarity = _normalize_taste_profile(taste_profile).get('familiarity')
        if familiarity == 'discovery' and tracks:
            return tracks[:limit]

        if len(tracks) < limit:
            _append_unique_tracks(
                tracks,
                seen_keys,
                self.service._build_curated_fallback_tracks(emotion, limit=limit),
                limit,
            )

        return tracks[:limit]

    def _collect_tracks_for_queries(
        self,
        queries,
        *,
        emotion,
        token_candidates,
        token_index,
        result,
        deadline,
        seen_track_ids,
        seen_track_match_keys,
        remaining_slots,
    ):
        """Search `queries` in order until the deadline or the slots run out.

        Returns `(collected_tracks, token_index)` and mutates `result`
        (queries_tried / spotify_errors / token_sources_tried) plus the two
        `seen_*` sets. The returned `token_index` lets a caller run several
        batches of queries without re-trying tokens Spotify already rejected.
        """
        collected_tracks = []
        for query in queries:
            remaining_time = deadline - time.monotonic()
            if remaining_time <= 0:
                logger.info(
                    "Stopping Spotify recommendation lookup for %r due to time budget",
                    emotion,
                )
                break

            if remaining_slots <= 0:
                break

            while token_index < len(token_candidates):
                token_source, token = token_candidates[token_index]
                if token_source not in result['token_sources_tried']:
                    result['token_sources_tried'].append(token_source)
                try:
                    search_limit = _clamp_spotify_search_limit(
                        max(remaining_slots, 5),
                        default=5,
                    )
                    search_result = self.service.search_tracks_detailed(
                        query,
                        token,
                        limit=search_limit,
                        timeout_seconds=min(self.service.request_timeout_seconds, remaining_time),
                    )
                    if search_result['ok']:
                        seed_metadata = self.service._seed_metadata_for_query(emotion, query)
                        tracks = self.service._filter_tracks_for_query(
                            query,
                            search_result['items'],
                            strict=bool(seed_metadata),
                        )
                        tracks = self.service._annotate_tracks_for_query(
                            query,
                            tracks,
                            emotion=emotion,
                        )
                        break
                    if search_result['status_code'] in (401, 403):
                        raise SpotifyAuthError(
                            search_result['status_code'],
                            query,
                            search_result.get('response_text') or search_result.get('error') or '',
                        )
                    result['spotify_errors'].append(_compact_failure(
                        search_result,
                        source=token_source,
                        extra={'query': query},
                    ))
                    tracks = []
                    break
                except SpotifyAuthError as error:
                    logger.warning(
                        "Spotify track search using %s token failed with status %s for query %r. "
                        "Trying fallback token if available.",
                        token_source,
                        error.status_code,
                        query,
                    )
                    result['spotify_errors'].append({
                        'source': token_source,
                        'status_code': error.status_code,
                        'reason': 'spotify_auth_failed',
                        'error': error.response_text[:300] or 'Spotify rejected the token.',
                        'error_code': None,
                        'query': query,
                    })
                    token_index += 1
            else:
                logger.warning(
                    "All available Spotify tokens were rejected while searching for emotion %r",
                    emotion,
                )
                break

            result['queries_tried'].append(query)

            for track in tracks:
                if _is_non_music_track(track):
                    continue
                track_id = track.get('id')
                track_match_key = _track_match_key(track)
                if (
                    not track_id
                    or track_id in seen_track_ids
                    or (track_match_key and track_match_key in seen_track_match_keys)
                ):
                    continue
                seen_track_ids.add(track_id)
                if track_match_key:
                    seen_track_match_keys.add(track_match_key)
                collected_tracks.append(track)
                remaining_slots -= 1
                if remaining_slots <= 0:
                    break

        return collected_tracks, token_index

    def get_recommendations_with_details(
        self,
        emotion,
        user=None,
        preferred_artists=None,
        top_emotions=None,
        all_scores=None,
        llm_queries=None,
        playlist_category=None,
        seed_artist_name=None,
        seed_track_name=None,
        limit=20,
        include_personalization=True,
        time_budget_seconds=None,
        query_mode='default',
        taste_profile=None,
    ):
        """Get track recommendations with explicit fallback metadata."""
        result = {
            'ok': False,
            'tracks': [],
            'source': 'spotify',
            'used_fallback': False,
            'fallback_reason': None,
            'queries_tried': [],
            'token_sources_tried': [],
            'spotify_errors': [],
            'token_failures': [],
            'personalized': False,
            'personalization_sources': [],
            'personalization_missing_scopes': [],
            'personalization_errors': [],
            'pool_used': False,
            'pool_state': None,
            'pool_age_seconds': None,
            'pool_tracks_used': 0,
        }

        all_tracks = []
        search_tracks = []
        seen_track_ids = set()
        seen_track_match_keys = set()
        desired_candidate_total = limit

        personalized_tracks = []
        if include_personalization:
            user_music_result = self.service.get_user_music_candidates(
                emotion,
                user=user,
                preferred_artists=preferred_artists,
                limit=limit,
            )
            result['personalization_sources'] = user_music_result.get('sources_used') or []
            result['personalization_missing_scopes'] = (
                user_music_result.get('missing_scopes') or []
            )
            result['personalization_errors'] = user_music_result.get('errors') or []
            personalized_tracks = user_music_result.get('tracks') or []
            if personalized_tracks:
                result['personalized'] = True
                result['source'] = 'user_music'
                all_tracks.extend(personalized_tracks)
                seen_track_ids.update(
                    track.get('id')
                    for track in personalized_tracks
                    if track.get('id')
                )
                seen_track_match_keys.update(
                    match_key
                    for match_key in (
                        _track_match_key(track)
                        for track in personalized_tracks
                    )
                    if match_key
                )
                desired_candidate_total = min(max(limit + 6, limit), limit * 2)

        token_candidates, token_failures = self.service._get_catalog_token_candidates(user=user)
        result['token_failures'] = token_failures
        if not token_candidates:
            fallback_reason = (
                token_failures[0]['reason'] if token_failures else 'token_unavailable'
            )
            # A warm pool outlives a Spotify outage: it already holds real
            # catalog tracks for this emotion, which beats the curated
            # fallback list that everyone would otherwise share.
            offline_pool_lookup = pool.read_pool(emotion)
            if offline_pool_lookup:
                pooled_tracks = _pool_candidates(
                    offline_pool_lookup['tracks'],
                    emotion=emotion,
                    limit=max(desired_candidate_total - len(all_tracks), 0),
                    seen_track_ids=seen_track_ids,
                    seen_track_match_keys=seen_track_match_keys,
                    taste_profile=taste_profile,
                )
                if pooled_tracks:
                    logger.info(
                        "No Spotify API tokens available for emotion %r reason=%s. "
                        "Serving %d pooled tracks instead.",
                        emotion,
                        fallback_reason,
                        len(pooled_tracks),
                    )
                    merged_tracks = self.service.blend_recommendation_groups(
                        emotion=emotion,
                        personalized_tracks=personalized_tracks,
                        search_tracks=pooled_tracks,
                        preferred_artists=preferred_artists,
                        limit=limit,
                        taste_profile=taste_profile,
                        user=user,
                    )
                    result.update({
                        'ok': bool(merged_tracks),
                        'tracks': merged_tracks,
                        'source': (
                            'hybrid_user_music_spotify'
                            if result['personalized']
                            else 'spotify'
                        ),
                        'fallback_reason': fallback_reason,
                        'pool_used': True,
                        'pool_state': offline_pool_lookup['state'],
                        'pool_age_seconds': offline_pool_lookup['age_seconds'],
                        'pool_tracks_used': len(pooled_tracks),
                    })
                    return result

            logger.warning(
                "No Spotify API tokens available for emotion %r reason=%s. "
                "Returning playable fallbacks.",
                emotion,
                fallback_reason,
            )
            fallback_tracks = self.service._build_fallback_tracks(
                emotion,
                user=user,
                preferred_artists=preferred_artists,
                limit=limit,
                taste_profile=taste_profile,
            )
            merged_tracks = self.service.blend_recommendation_groups(
                emotion=emotion,
                personalized_tracks=all_tracks,
                fallback_tracks=fallback_tracks,
                preferred_artists=preferred_artists,
                limit=limit,
                taste_profile=taste_profile,
                user=user,
            )
            result.update({
                'ok': bool(merged_tracks),
                'tracks': merged_tracks,
                'source': 'user_music_fallback' if result['personalized'] else 'fallback',
                'used_fallback': len(merged_tracks) > len(all_tracks),
                'fallback_reason': fallback_reason,
            })
            return result

        resolved_time_budget_seconds = max(
            float(time_budget_seconds or self.service.recommendation_budget_seconds),
            0.5,
        )
        deadline = time.monotonic() + resolved_time_budget_seconds
        queries = self.service._build_recommendation_queries(
            emotion,
            preferred_artists=preferred_artists,
            top_emotions=top_emotions,
            all_scores=all_scores,
            llm_queries=llm_queries,
            playlist_category=playlist_category,
            seed_artist_name=seed_artist_name,
            seed_track_name=seed_track_name,
            query_mode=query_mode,
            taste_profile=taste_profile,
        )
        token_index = 0
        normalized_query_mode = str(query_mode or 'default').strip().lower() or 'default'
        # A request can be served from the shared pool when its candidates are
        # allowed to be emotion-generic. "Play more like this song" requests
        # (seed track/artist) and continuation pages are not: they asked for
        # something specific, so they always go to Spotify. "Prefer
        # instrumental" is the same kind of ask -- the pool is whatever the
        # emotion returned for everyone, mostly vocal, and a share of one
        # live query cannot pull it back.
        pool_lookup = (
            pool.read_pool(emotion)
            if normalized_query_mode == 'default'
            and not seed_track_name
            and not seed_artist_name
            and not _normalize_taste_profile(taste_profile).get('prefer_instrumental')
            else None
        )

        try:
            if pool_lookup:
                # A pool hit still runs the queries this request does not share
                # with the emotion baseline -- LLM picks, preferred artists,
                # playlist category -- because those are what make the playlist
                # this user's. They get a short leash, then the pool covers the
                # rest instantly instead of a dozen more round trips.
                baseline_queries = {
                    baseline_query.strip().lower()
                    for baseline_query in self.service._build_recommendation_queries(emotion)
                }
                user_specific_queries = [
                    query
                    for query in queries
                    if query.strip().lower() not in baseline_queries
                ]
                live_slots = min(
                    int(desired_candidate_total * pool.live_query_share()),
                    max(desired_candidate_total - len(all_tracks), 0),
                )
                if user_specific_queries and live_slots > 0:
                    live_tracks, token_index = self._collect_tracks_for_queries(
                        user_specific_queries,
                        emotion=emotion,
                        token_candidates=token_candidates,
                        token_index=token_index,
                        result=result,
                        deadline=min(
                            deadline,
                            time.monotonic() + pool.live_query_budget_seconds(),
                        ),
                        seen_track_ids=seen_track_ids,
                        seen_track_match_keys=seen_track_match_keys,
                        remaining_slots=live_slots,
                    )
                    search_tracks.extend(live_tracks)
                    all_tracks.extend(live_tracks)

                pooled_tracks = _pool_candidates(
                    pool_lookup['tracks'],
                    emotion=emotion,
                    limit=max(desired_candidate_total - len(all_tracks), 0),
                    seen_track_ids=seen_track_ids,
                    seen_track_match_keys=seen_track_match_keys,
                    taste_profile=taste_profile,
                )
                for track in pooled_tracks:
                    seen_track_ids.add(track['id'])
                    pooled_match_key = _track_match_key(track)
                    if pooled_match_key:
                        seen_track_match_keys.add(pooled_match_key)
                search_tracks.extend(pooled_tracks)
                all_tracks.extend(pooled_tracks)
                result.update({
                    'pool_used': bool(pooled_tracks),
                    'pool_state': pool_lookup['state'],
                    'pool_age_seconds': pool_lookup['age_seconds'],
                    'pool_tracks_used': len(pooled_tracks),
                })

                if len(all_tracks) < limit:
                    # The pool was too thin to fill a playlist on its own, so
                    # pay for the live searches it could not cover.
                    tried_queries = {
                        tried_query.strip().lower()
                        for tried_query in result['queries_tried']
                    }
                    rescue_tracks, token_index = self._collect_tracks_for_queries(
                        [
                            query
                            for query in queries
                            if query.strip().lower() not in tried_queries
                        ],
                        emotion=emotion,
                        token_candidates=token_candidates,
                        token_index=token_index,
                        result=result,
                        deadline=deadline,
                        seen_track_ids=seen_track_ids,
                        seen_track_match_keys=seen_track_match_keys,
                        remaining_slots=max(desired_candidate_total - len(all_tracks), 0),
                    )
                    search_tracks.extend(rescue_tracks)
                    all_tracks.extend(rescue_tracks)
            else:
                collected_tracks, token_index = self._collect_tracks_for_queries(
                    queries,
                    emotion=emotion,
                    token_candidates=token_candidates,
                    token_index=token_index,
                    result=result,
                    deadline=deadline,
                    seen_track_ids=seen_track_ids,
                    seen_track_match_keys=seen_track_match_keys,
                    remaining_slots=max(desired_candidate_total - len(all_tracks), 0),
                )
                search_tracks.extend(collected_tracks)
                all_tracks.extend(collected_tracks)

                # Warm the pool from real traffic, but only from a request whose
                # queries were purely emotion-driven. Anything shaped by one
                # user (preferred artists, LLM picks, a playlist category, the
                # detected secondary emotions) must not become everyone's
                # baseline.
                if search_tracks and not any([
                    preferred_artists,
                    top_emotions,
                    all_scores,
                    llm_queries,
                    playlist_category,
                    normalized_query_mode != 'default',
                ]):
                    pool.store_pool(emotion, search_tracks, result['queries_tried'])
        except Exception:
            logger.exception("Spotify recommendation generation failed for emotion %r", emotion)
            fallback_tracks = self.service._build_fallback_tracks(
                emotion,
                user=user,
                preferred_artists=preferred_artists,
                limit=limit,
                taste_profile=taste_profile,
            )
            merged_tracks = self.service.blend_recommendation_groups(
                emotion=emotion,
                personalized_tracks=personalized_tracks,
                search_tracks=search_tracks,
                fallback_tracks=fallback_tracks,
                preferred_artists=preferred_artists,
                limit=limit,
                taste_profile=taste_profile,
                user=user,
            )
            result.update({
                'ok': bool(merged_tracks),
                'tracks': merged_tracks,
                'source': 'user_music_fallback' if result['personalized'] else 'fallback',
                'used_fallback': len(merged_tracks) > len(all_tracks),
                'fallback_reason': 'exception',
            })
            return result

        if not all_tracks:
            logger.warning(
                "No Spotify recommendations found for emotion %r. Returning playable fallbacks.",
                emotion,
            )
            fallback_tracks = self.service._build_fallback_tracks(
                emotion,
                user=user,
                preferred_artists=preferred_artists,
                limit=limit,
                taste_profile=taste_profile,
            )
            # Route the fallbacks through the blender too, so taste control
            # still applies when Spotify returned nothing at all.
            merged_tracks = self.service.blend_recommendation_groups(
                emotion=emotion,
                fallback_tracks=fallback_tracks,
                preferred_artists=preferred_artists,
                limit=limit,
                taste_profile=taste_profile,
                user=user,
            ) or fallback_tracks
            result.update({
                'ok': bool(merged_tracks),
                'tracks': merged_tracks,
                'source': 'fallback',
                'used_fallback': True,
                'fallback_reason': (
                    result['spotify_errors'][0]['reason']
                    if result['spotify_errors']
                    else 'no_results'
                ),
            })
            return result

        search_contributed_tracks = bool(search_tracks)
        ranked_tracks = self.service.blend_recommendation_groups(
            emotion=emotion,
            personalized_tracks=personalized_tracks,
            search_tracks=search_tracks,
            preferred_artists=preferred_artists,
            limit=limit,
            taste_profile=taste_profile,
            user=user,
        )
        result.update({
            'ok': True,
            'tracks': ranked_tracks or all_tracks[:limit],
            'source': (
                'hybrid_user_music_spotify'
                if result['personalized'] and search_contributed_tracks
                else 'user_music'
                if result['personalized']
                else 'spotify'
            ),
        })
        return result

    def build_emotion_pool(self, emotion, *, target_size=None, time_budget_seconds=None):
        """Fetch a fresh set of shared candidates for one emotion.

        Runs only the emotion-derived queries -- no user, no preferred
        artists, no LLM picks, no playlist category -- which is exactly what
        makes the result safe to hand to every user asking about that emotion.
        """
        normalized_emotion = pool.normalize_emotion(emotion)
        result = {
            'ok': False,
            'emotion': normalized_emotion,
            'tracks': [],
            'queries_tried': [],
            'token_sources_tried': [],
            'spotify_errors': [],
            'token_failures': [],
            'reason': None,
            'retry_after': None,
            # True when some queries failed (a 429 mid-run, say): the tracks are
            # whatever got through, not a full refresh.
            'partial': False,
        }

        resolved_target_size = max(int(target_size or pool.target_size()), 1)
        resolved_budget_seconds = max(
            float(time_budget_seconds or pool.refresh_budget_seconds()),
            1.0,
        )

        token_candidates, token_failures = self.service._get_catalog_token_candidates()
        result['token_failures'] = token_failures
        if not token_candidates:
            result['reason'] = (
                token_failures[0]['reason'] if token_failures else 'token_unavailable'
            )
            return result

        pooled_tracks, _ = self._collect_tracks_for_queries(
            self.service._build_recommendation_queries(normalized_emotion),
            emotion=normalized_emotion,
            token_candidates=token_candidates,
            token_index=0,
            result=result,
            deadline=time.monotonic() + resolved_budget_seconds,
            seen_track_ids=set(),
            seen_track_match_keys=set(),
            remaining_slots=resolved_target_size,
        )

        result['tracks'] = pooled_tracks
        result['ok'] = bool(pooled_tracks)
        result['partial'] = bool(pooled_tracks and result['spotify_errors'])
        if not pooled_tracks or result['partial']:
            first_error = (
                result['spotify_errors'][0] if result['spotify_errors'] else {}
            )
            result['reason'] = first_error.get('reason') or 'no_results'
            # Surfaced so `refresh_emotion_pools` can wait exactly as long as
            # Spotify asked instead of guessing at a backoff.
            result['retry_after'] = next(
                (
                    error['retry_after']
                    for error in result['spotify_errors']
                    if error.get('retry_after') is not None
                ),
                None,
            )
        return result

    def refresh_emotion_pool(self, emotion, *, target_size=None, time_budget_seconds=None):
        """Build the shared candidate pool for one emotion and store it.

        Only a clean build may replace the pool outright. A partial one (some
        queries failed, typically to a 429) goes through the normal size check,
        so it can fill an empty or expired pool but never shrink a live one: a
        refresh during the 2026-10-05 rate-limit storm left "happy" with one
        track. With nothing stored, the refresh command retries after the
        Retry-After it reports.
        """
        refresh_result = self.build_emotion_pool(
            emotion,
            target_size=target_size,
            time_budget_seconds=time_budget_seconds,
        )
        refresh_result['stored'] = (
            pool.store_pool(
                refresh_result['emotion'],
                refresh_result['tracks'],
                refresh_result['queries_tried'],
                force=not refresh_result['partial'],
            )
            if refresh_result['ok']
            else 0
        )
        return refresh_result

    def get_recommendations(self, emotion, user=None, preferred_artists=None, limit=20):
        """Get track recommendations based on emotion."""
        return self.service.get_recommendations_with_details(
            emotion,
            user=user,
            preferred_artists=preferred_artists,
            limit=limit,
        )['tracks']

    def get_user_profile_result(self, token):
        """Get Spotify user profile with structured upstream details."""
        return self.service._spotify_get(token, '/me')

    def get_user_profile(self, token):
        """Get Spotify user profile."""
        profile_result = self.service.get_user_profile_result(token)
        if profile_result.get('ok'):
            return profile_result.get('data')
        return None
