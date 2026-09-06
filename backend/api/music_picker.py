"""
The EmoTune music picker: turns a Spotify candidate set into a ranked playlist.

This is the orchestration layer around `api/picker_ranker.py`. The ranker scores
tracks; this module normalizes the candidate set, asks the ranker for an order,
and shapes the result into the dict `views.py` puts on the API response.

It replaces the former `lightfm_ranker.py`. That module presented LightFM as the
ranking layer and treated the linear picker as its fallback, but LightFM never
actually ran: it publishes no wheels, its bundled Cython sources do not compile
on Python 3.12, and it was absent from `requirements.txt` for exactly that
reason. Every deployment took the "fallback" path, so the fallback was the
product. Removing LightFM deletes ~700 lines of collaborative-filtering
machinery (per-request corpus building, score blending, feature hashing) that
never executed, and lets the picker say plainly what it does.

One consequence worth knowing: results now report `used_fallback: False`. Under
the old module that field meant "LightFM did not produce this ranking", which
was always true. There is nothing left to fall back from, so a successful
ranking is no longer flagged as a degraded one.
"""
import logging
import re

from api.picker_ranker import (
    discovery_bonus as _shared_discovery_bonus,
    instrumental_bonus as _shared_instrumental_bonus,
    normalize_taste_profile as _shared_normalize_taste_profile,
    picker_ranker,
)

logger = logging.getLogger(__name__)

SAFE_TRACK_DEFAULT_LIMIT = 20


class MusicPicker:
    """Ranks candidate tracks for one emotion and shapes the picker payload."""

    def pick_playlist(
        self,
        *,
        prompt_text,
        emotion,
        top_emotions=None,
        all_scores=None,
        confidence_band=None,
        confidence_margin=None,
        candidates,
        preferred_artists=None,
        user=None,
        playlist_size=None,
        taste_profile=None,
    ):
        """Return a ranked playlist plus the track to play first.

        The signature keeps the arguments the old LightFM entry point accepted
        even though the linear ranker does not read all of them: the caller in
        `views.py` passes the full emotion context, and dropping parameters here
        would only push the same conditionals up into the view.
        """
        resolved_size = max(int(playlist_size or SAFE_TRACK_DEFAULT_LIMIT), 1)
        normalized_candidates = self._normalize_candidates(candidates)

        return self._rank_playlist(
            candidates=normalized_candidates,
            emotion=emotion,
            top_emotions=top_emotions,
            prompt_text=prompt_text,
            playlist_size=resolved_size,
            taste_profile=taste_profile,
        )

    def _rank_playlist(
        self,
        *,
        candidates,
        emotion,
        prompt_text,
        playlist_size,
        top_emotions=None,
        taste_profile=None,
        error=None,
    ):
        """Score the candidates with the linear picker and take the top slice."""
        ranked_candidates, weights_version = picker_ranker.rank(
            candidates,
            taste_profile=taste_profile,
        )
        if not ranked_candidates:
            ranked_candidates = list(candidates or [])

        tracks = list(ranked_candidates[:playlist_size])
        selected_track = tracks[0] if tracks else None
        return {
            'ok': bool(tracks),
            'strategy': 'linear_ranker_playlist',
            'tracks': tracks,
            'selected_track': selected_track,
            'playlist_track_ids': [
                str(track.get('id'))
                for track in tracks
                if str(track.get('id') or '').strip()
            ],
            'reason': None,
            'confidence': None,
            'provider': 'picker_ranker',
            'model': f'picker_linear_{weights_version}',
            'used_fallback': False,
            'error': error if not tracks else None,
            'candidates': list(ranked_candidates[: min(len(ranked_candidates), 12)]),
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
            'playlist_category': self._playlist_category(emotion, top_emotions or []),
            'confirmation': self._build_confirmation(
                selected_track, emotion, prompt_text=prompt_text
            ),
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

    # The taste reading lives in picker_ranker so every caller agrees on what
    # "familiar" means. These stay as thin delegates because the picker is the
    # object callers already hold.
    def _normalize_taste_profile(self, taste_profile):
        return _shared_normalize_taste_profile(taste_profile)

    def _discovery_bonus(self, track, taste_profile):
        return _shared_discovery_bonus(track, taste_profile)

    def _instrumental_bonus(self, track, taste_profile):
        return _shared_instrumental_bonus(track, taste_profile)

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

    def _slug(self, value):
        normalized = re.sub(r'[^a-z0-9]+', '_', str(value or '').strip().lower())
        return normalized.strip('_')


music_picker = MusicPicker()
