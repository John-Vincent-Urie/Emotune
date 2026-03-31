"""Helpers for deriving a Plutchik-style profile from EmoTune scores."""

from __future__ import annotations

from typing import Mapping


EMOTUNE_EMOTIONS = [
    "happy",
    "sad",
    "angry",
    "motivational",
    "fear",
    "depressing",
    "surprising",
    "stressed",
    "calm",
    "lonely",
    "romantic",
    "nostalgic",
    "mixed",
]

PLUTCHIK_EMOTIONS = [
    "joy",
    "trust",
    "fear",
    "surprise",
    "sadness",
    "disgust",
    "anger",
    "anticipation",
]

PLUTCHIK_PROFILE_VERSION = "v1"

# These weights are intentionally heuristic and meant for a secondary,
# visualization-friendly hybrid profile rather than for replacing EmoTune's
# primary 13-label prediction schema.
EMOTUNE_TO_PLUTCHIK_WEIGHTS = {
    "happy": {
        "joy": 1.0,
        "trust": 0.35,
    },
    "sad": {
        "sadness": 1.0,
    },
    "angry": {
        "anger": 1.0,
        "disgust": 0.35,
    },
    "motivational": {
        "anticipation": 0.9,
        "joy": 0.35,
        "trust": 0.25,
    },
    "fear": {
        "fear": 1.0,
    },
    "depressing": {
        "sadness": 1.0,
        "fear": 0.2,
    },
    "surprising": {
        "surprise": 1.0,
        "anticipation": 0.2,
    },
    "stressed": {
        "fear": 0.7,
        "anticipation": 0.55,
        "anger": 0.15,
    },
    "calm": {
        "trust": 0.7,
        "joy": 0.25,
    },
    "lonely": {
        "sadness": 0.8,
        "fear": 0.15,
    },
    "romantic": {
        "trust": 0.8,
        "joy": 0.45,
        "anticipation": 0.25,
    },
    "nostalgic": {
        "sadness": 0.55,
        "joy": 0.35,
        "trust": 0.15,
    },
    "mixed": {
        "joy": 0.15,
        "trust": 0.15,
        "fear": 0.15,
        "surprise": 0.15,
        "sadness": 0.15,
        "disgust": 0.1,
        "anger": 0.1,
        "anticipation": 0.15,
    },
}


def _safe_float(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _normalize_emotune_scores(scores: Mapping[str, float] | None) -> dict[str, float]:
    sanitized = {
        emotion: max(0.0, _safe_float((scores or {}).get(emotion, 0.0)))
        for emotion in EMOTUNE_EMOTIONS
    }
    max_value = max(sanitized.values(), default=0.0)
    if max_value > 1.0:
        sanitized = {
            emotion: min(value / 100.0, 1.0)
            for emotion, value in sanitized.items()
        }
    return sanitized


def rank_plutchik_scores(scores: Mapping[str, float] | None) -> list[dict]:
    ranking = [
        {
            "emotion": emotion,
            "confidence": max(0.0, min(_safe_float((scores or {}).get(emotion, 0.0)), 1.0)),
        }
        for emotion in PLUTCHIK_EMOTIONS
    ]
    ranking.sort(key=lambda item: (-item["confidence"], item["emotion"]))
    return ranking


def build_plutchik_scores(emotune_scores: Mapping[str, float] | None) -> dict[str, float]:
    normalized_emotune = _normalize_emotune_scores(emotune_scores)
    plutchik_scores = {emotion: 0.0 for emotion in PLUTCHIK_EMOTIONS}

    for emotion, source_score in normalized_emotune.items():
        for plutchik_emotion, weight in EMOTUNE_TO_PLUTCHIK_WEIGHTS.get(emotion, {}).items():
            plutchik_scores[plutchik_emotion] += source_score * float(weight)

    return {
        emotion: max(0.0, min(score, 1.0))
        for emotion, score in plutchik_scores.items()
    }


def build_plutchik_profile(emotune_scores: Mapping[str, float] | None) -> dict:
    plutchik_scores = build_plutchik_scores(emotune_scores)
    ranking = rank_plutchik_scores(plutchik_scores)
    dominant_emotion = ranking[0]["emotion"] if ranking else None
    return {
        "plutchik_scores": plutchik_scores,
        "plutchik_top_emotions": ranking[:3],
        "plutchik_dominant_emotion": dominant_emotion,
        "plutchik_profile_version": PLUTCHIK_PROFILE_VERSION,
    }
