"""
Feature-based linear ranker for the EmoTune music picker.

This is the model that actually decides which track plays. It scores every
candidate as a weighted sum of signals the recommendation engine has already
computed, so ranking a candidate set costs one dot product per track -- no
model fitting, no native extension, no extra process memory.

Two things live here on purpose:

* The weights are data, not code. `ml_model/train_picker_ranker.py` fits them
  offline from real listening outcomes and writes a small JSON artifact. Until
  that artifact exists the built-in defaults reproduce the hand-tuned blend
  that shipped before, so an untrained deployment ranks exactly as it used to.
* The taste helpers (familiarity, instrumental) live here rather than in
  api/music_picker.py, so every caller reads a taste profile the same way
  instead of each growing its own interpretation of "familiar".
"""
import json
import logging
import math
import os
import threading

from django.conf import settings

from api.spotify.utils import _taste_instrumental_signal

logger = logging.getLogger(__name__)

# Order matters: the trainer writes weights by name, but the feature vector it
# fits and the vector we score with have to agree, so both sides import this.
FEATURE_ORDER = (
    'emotion_alignment',
    'personalization',
    'popularity',
    'availability',
    'is_preferred',
    'familiar_source',
    'discovery_fit',
    'instrumental_fit',
)

# Defaults are not guesses -- they are the hand-tuned blend the picker shipped
# with, written as weights. Emotion carries 0.80 because it absorbed the 0.40
# share once reserved for a collaborative-filtering term that never ran;
# personalization 0.10, and availability and popularity split the old 0.10
# presentation term 0.7/0.3. The two taste
# terms pass through at 1.0 because they arrive pre-scaled.
DEFAULT_WEIGHTS = {
    'emotion_alignment': 0.80,
    'personalization': 0.10,
    'popularity': 0.03,
    'availability': 0.07,
    'is_preferred': 0.0,
    'familiar_source': 0.0,
    'discovery_fit': 1.0,
    'instrumental_fit': 1.0,
}
DEFAULT_BIAS = 0.0

FAMILIAR_SOURCES = frozenset({
    'spotify_top_tracks',
    'spotify_saved_tracks',
    'user_preference',
    'favorite_track',
})
DISCOVERY_SOURCES = frozenset({'spotify_catalog', 'curated_fallback'})


def normalize_taste_profile(taste_profile):
    working = taste_profile if isinstance(taste_profile, dict) else {}
    familiarity = str(working.get('familiarity') or 'balanced').strip().lower()
    if familiarity not in {'balanced', 'familiar', 'discovery'}:
        familiarity = 'balanced'
    return {
        'familiarity': familiarity,
        'prefer_instrumental': bool(working.get('prefer_instrumental', False)),
    }


def discovery_bonus(track, taste_profile):
    """Signed nudge for how well a track's source matches the taste setting."""
    familiarity = normalize_taste_profile(taste_profile).get('familiarity')
    source = str(track.get('recommendation_source') or '').strip().lower()
    if familiarity == 'discovery':
        if source in DISCOVERY_SOURCES:
            return 0.08
        if source in FAMILIAR_SOURCES - {'favorite_track'}:
            return -0.06
    if familiarity == 'familiar':
        if source in FAMILIAR_SOURCES:
            return 0.08
        if source in DISCOVERY_SOURCES:
            return -0.05
    return 0.0


def instrumental_bonus(track, taste_profile):
    """The shared instrumental reading, scaled for the blended 0-1 range."""
    text_blob = ' '.join([
        str(track.get('name') or '').strip().lower(),
        str(track.get('artist') or '').strip().lower(),
        str(track.get('album') or '').strip().lower(),
    ])
    signal, reason = _taste_instrumental_signal(text_blob, normalize_taste_profile(taste_profile))
    return signal * 0.12, reason


def _safe_float(value, default=0.0):
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return default if math.isnan(result) or math.isinf(result) else result


def _min_max(values, *, default):
    """Spread raw scores across 0-1. A flat field gets `default` throughout, so
    a signal with nothing to say does not arrive looking decisive."""
    if not values:
        return {}
    numbers = list(values.values())
    lowest = min(numbers)
    highest = max(numbers)
    if abs(highest - lowest) < 1e-9:
        return {key: default for key in values}
    return {
        key: (value - lowest) / (highest - lowest)
        for key, value in values.items()
    }


def build_feature_rows(candidates, taste_profile=None):
    """Turn a candidate set into per-track feature dicts.

    Normalization is within the candidate set, which is what makes the weights
    portable: the trainer sees the same 0-1 ranges at fit time that the ranker
    sees at serve time, even though absolute score scales drift as the
    recommendation engine changes.
    """
    tracks = [track for track in (candidates or []) if isinstance(track, dict)]
    if not tracks:
        return []

    profile = normalize_taste_profile(taste_profile)
    keys = [str(track.get('id') or index) for index, track in enumerate(tracks)]

    emotion_norm = _min_max(
        {key: _safe_float(track.get('emotion_alignment_score')) for key, track in zip(keys, tracks)},
        default=0.5,
    )
    personal_norm = _min_max(
        {key: _safe_float(track.get('personalization_score')) for key, track in zip(keys, tracks)},
        default=0.0,
    )

    rows = []
    for key, track in zip(keys, tracks):
        source = str(track.get('recommendation_source') or '').strip().lower()
        instrumental_value, instrumental_reason = instrumental_bonus(track, profile)
        rows.append({
            'track': track,
            'reason': instrumental_reason,
            'features': {
                'emotion_alignment': emotion_norm.get(key, 0.5),
                'personalization': personal_norm.get(key, 0.0),
                'popularity': min(max(_safe_float(track.get('popularity')) / 100.0, 0.0), 1.0),
                'availability': 1.0 if str(track.get('spotify_url') or '').strip() else 0.5,
                'is_preferred': 1.0 if track.get('is_preferred') else 0.0,
                'familiar_source': 1.0 if source in FAMILIAR_SOURCES else 0.0,
                'discovery_fit': discovery_bonus(track, profile),
                'instrumental_fit': instrumental_value,
            },
        })
    return rows


class PickerRanker:
    """Scores candidates from a weight artifact, or from the built-in defaults."""

    def __init__(self):
        self._lock = threading.Lock()
        self._cache = None
        self._cache_key = None

    def weights_path(self):
        return str(getattr(settings, 'PICKER_RANKER_WEIGHTS_PATH', '') or '').strip()

    def _load_weights(self):
        """Read the artifact at most once per file revision.

        Keyed on (path, mtime, size) so retraining is picked up by a restart or
        a touched file without a redeploy, and a missing or malformed artifact
        silently keeps the defaults rather than taking a request down.
        """
        path = self.weights_path()
        if not path or not getattr(settings, 'PICKER_RANKER_ENABLED', True):
            return dict(DEFAULT_WEIGHTS), DEFAULT_BIAS, 'default'

        try:
            stat = os.stat(path)
            key = (path, stat.st_mtime_ns, stat.st_size)
        except OSError:
            return dict(DEFAULT_WEIGHTS), DEFAULT_BIAS, 'default'

        with self._lock:
            if self._cache_key == key and self._cache is not None:
                return self._cache

            try:
                with open(path, 'r', encoding='utf-8') as handle:
                    payload = json.load(handle)
                raw_weights = payload.get('weights')
                if not isinstance(raw_weights, dict):
                    raise ValueError('artifact has no weights object')
                weights = {
                    name: _safe_float(raw_weights.get(name), DEFAULT_WEIGHTS[name])
                    for name in FEATURE_ORDER
                }
                bias = _safe_float(payload.get('bias'), DEFAULT_BIAS)
                version = str(payload.get('version') or 'trained')
            except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
                logger.warning("Picker weights at %s are unusable (%s); using defaults.", path, error)
                loaded = (dict(DEFAULT_WEIGHTS), DEFAULT_BIAS, 'default')
            else:
                loaded = (weights, bias, version)

            self._cache_key = key
            self._cache = loaded
            return loaded

    def score_rows(self, rows):
        weights, bias, version = self._load_weights()
        scored = []
        for row in rows:
            score = bias + sum(
                row['features'][name] * weights[name]
                for name in FEATURE_ORDER
            )
            scored.append((score, row))
        return scored, version

    def rank(self, candidates, *, taste_profile=None):
        """Return candidates ordered best-first, annotated with their score.

        Ties fall back to the same secondary keys the blended ranker used, so a
        model with no opinion leaves the emotion ordering intact.
        """
        rows = build_feature_rows(candidates, taste_profile)
        if not rows:
            return [], 'default'

        scored, version = self.score_rows(rows)
        profile = normalize_taste_profile(taste_profile)
        familiarity = profile.get('familiarity')

        ranked = []
        for score, row in scored:
            track = dict(row['track'])
            reasons = list(track.get('recommendation_reasons') or track.get('emotion_alignment_reasons') or [])
            reasons.append(
                'learned_ranker' if version != 'default' else 'default_weight_ranker'
            )
            if familiarity in {'familiar', 'discovery'}:
                reasons.append(f'taste:{familiarity}')
            if row['reason']:
                reasons.append(row['reason'])

            seen = set()
            track['recommendation_reasons'] = [
                reason for reason in reasons
                if reason and not (reason in seen or seen.add(reason))
            ]
            track['recommendation_score'] = round(score, 5)
            track['picker_features'] = {
                name: round(row['features'][name], 5) for name in FEATURE_ORDER
            }
            ranked.append(track)

        ranked.sort(
            key=lambda item: (
                -_safe_float(item.get('recommendation_score')),
                -_safe_float(item.get('emotion_alignment_score')),
                -_safe_float(item.get('personalization_score')),
                -_safe_float(item.get('popularity')),
                str(item.get('name') or '').lower(),
            )
        )
        return ranked, version


picker_ranker = PickerRanker()
