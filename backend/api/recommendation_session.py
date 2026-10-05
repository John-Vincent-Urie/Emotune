"""Outcome modes, session planning, and taste controls for recommendations."""

from __future__ import annotations

from typing import Mapping


# Only two modes ship. "Match My Mood" mirrors the detected emotion;
# "Calm Me Down" steers it toward something steadier. The focus, lift and
# sleep modes were cut -- they were never reachable from the app, and a
# therapy tool is easier to defend with one clearly-stated regulating
# direction than with five that were each only half-tuned.
OUTCOME_MODE_CONFIG = {
    "match_mood": {
        "label": "Match My Mood",
        "description": "Stay close to the emotion the classifier detected.",
        "target_weights": {},
        "target_weight": 0.0,
        "default_session_minutes": 20,
        "default_check_in_tracks": 5,
        "check_in_prompt": "Is this session matching how you want to feel right now?",
        "completion_message": "Session locked in. I will stop interrupting and let the music carry you.",
    },
    "calm_me_down": {
        "label": "Calm Me Down",
        "description": "Gently de-escalate intense feelings into a steadier state.",
        "target_weights": {
            "calm": 0.55,
            "stressed": 0.15,
            "fear": 0.1,
            "sad": 0.1,
            "mixed": 0.1,
        },
        "target_weight": 0.58,
        # The iso-principle (Altshuler 1944; see docs/music_therapy_guidelines.md)
        # is match-then-shift: meet the listener where they are, then move the
        # music toward the steadier state over the session rather than jumping
        # there immediately. A single fixed target_weight cannot express that --
        # it lands on one point of the arc and stays there -- so the weight is
        # read per session phase, using the settle/support/close clock that
        # `update_session_plan_progress` already advances on every track end.
        #
        # `settle` stays above 0.0 on purpose. A full match would hand someone
        # who just said they feel hopeless a playlist that only deepens it, and
        # the shift here is reactive (it needs the listener to answer a check-in),
        # so the arc is not guaranteed to complete. Leaning toward their emotion
        # without ever abandoning the steadier pull is the safer reading while
        # that remains true.
        "phase_target_weights": {
            "settle": 0.40,
            "support": 0.58,
            "close": 0.78,
        },
        "default_session_minutes": 20,
        "default_check_in_tracks": 3,
        "check_in_prompt": "Has this session helped you settle down a little?",
        "completion_message": "Nice. I will keep the session calm and steady from here.",
    },
}

# Which of the two modes an emotion routes to (docs/arch).
#
# The classifier picks the mode; there is no user-facing switch. Emotions the
# listener has no reason to be moved out of are mirrored, and the distressing
# ones are steered toward something steadier rather than deepened -- playing
# heartbreak songs at someone who just said they feel hopeless is the failure
# mode a therapy tool has to avoid.
#
# "mixed" is mirrored: it means the classifier could not commit, and steering
# someone toward calm when there is no evidence they are distressed presumes
# more than the signal supports.
EMOTION_OUTCOME_MODES = {
    # Match My Mood
    "happy": "match_mood",
    "surprising": "match_mood",
    "motivational": "match_mood",
    "calm": "match_mood",
    "romantic": "match_mood",
    "nostalgic": "match_mood",
    "mixed": "match_mood",
    # Calm Me Down
    "sad": "calm_me_down",
    "stressed": "calm_me_down",
    "depressing": "calm_me_down",
    "angry": "calm_me_down",
    "fear": "calm_me_down",
    "lonely": "calm_me_down",
}


def outcome_mode_for_emotion(emotion) -> str:
    """The mode this emotion routes to, per docs/arch."""
    normalized = str(emotion or "").strip().lower()
    return EMOTION_OUTCOME_MODES.get(normalized, "match_mood")


def normalize_requested_outcome_mode(value) -> str | None:
    """A caller's explicit mode, or None to let the emotion decide.

    Distinct from `normalize_outcome_mode`, which collapses anything unknown to
    "match_mood". Here an absent or retired mode has to stay None, or a stage-2
    continuation carrying a mode that no longer exists would silently pin the
    session to Match My Mood instead of routing on the emotion.
    """
    candidate = str(value or "").strip().lower()
    return candidate if candidate in OUTCOME_MODE_CONFIG else None


def resolve_outcome_mode(emotion, requested=None) -> str:
    """An explicit request wins; otherwise the detected emotion decides."""
    return normalize_requested_outcome_mode(requested) or outcome_mode_for_emotion(emotion)


TASTE_FAMILIARITY_OPTIONS = {"balanced", "familiar", "discovery"}


def _safe_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def normalize_outcome_mode(value) -> str:
    normalized = str(value or "match_mood").strip().lower() or "match_mood"
    return normalized if normalized in OUTCOME_MODE_CONFIG else "match_mood"


def outcome_mode_config(mode: str | None) -> dict:
    return OUTCOME_MODE_CONFIG[normalize_outcome_mode(mode)]


def outcome_target_weight(mode: str | None, phase=None) -> float:
    """How hard this mode pulls toward its target, at this point in the session.

    An unknown or absent phase falls back to the mode's flat `target_weight`, so
    callers that know nothing about session progress keep the pre-iso behaviour.
    """
    config = outcome_mode_config(mode)
    phase_weights = config.get("phase_target_weights") or {}
    normalized_phase = str(phase or "").strip().lower()
    weight = (
        phase_weights[normalized_phase]
        if normalized_phase in phase_weights
        else config.get("target_weight")
    )
    return min(max(_safe_float(weight, 0.5), 0.0), 1.0)


def normalize_taste_profile(raw_taste_profile: Mapping | None) -> dict:
    working = raw_taste_profile if isinstance(raw_taste_profile, Mapping) else {}
    familiarity = str(working.get("familiarity") or "balanced").strip().lower()
    if familiarity not in TASTE_FAMILIARITY_OPTIONS:
        familiarity = "balanced"

    return {
        "familiarity": familiarity,
        "prefer_instrumental": bool(working.get("prefer_instrumental", False)),
        "train_session": bool(working.get("train_session", True)),
    }


def should_persist_recommendation_context(
    *,
    outcome_mode: str,
    session_length_minutes: int,
    taste_profile: Mapping | None,
) -> bool:
    normalized_mode = normalize_outcome_mode(outcome_mode)
    normalized_taste = normalize_taste_profile(taste_profile)
    return (
        normalized_mode != "match_mood"
        or max(_safe_int(session_length_minutes), 0) > 0
        or normalized_taste["familiarity"] != "balanced"
        or normalized_taste["prefer_instrumental"]
        or not normalized_taste["train_session"]
    )


def _normalize_emotune_scores(scores: Mapping[str, float] | None) -> dict[str, float]:
    scores = scores if isinstance(scores, Mapping) else {}
    sanitized = {
        emotion: max(0.0, _safe_float(scores.get(emotion), 0.0))
        for emotion in {
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
        }
    }
    max_value = max(sanitized.values(), default=0.0)
    if max_value > 1.0:
        sanitized = {
            emotion: min(value / 100.0, 1.0)
            for emotion, value in sanitized.items()
        }
    total = sum(sanitized.values())
    if total <= 0:
        sanitized["mixed"] = 1.0
        total = 1.0
    return {
        emotion: value / total
        for emotion, value in sanitized.items()
    }


def _normalize_weight_map(weight_map: Mapping[str, float] | None) -> dict[str, float]:
    weight_map = weight_map if isinstance(weight_map, Mapping) else {}
    sanitized = {
        str(emotion or "").strip().lower(): max(0.0, _safe_float(weight, 0.0))
        for emotion, weight in weight_map.items()
        if str(emotion or "").strip()
    }
    total = sum(sanitized.values())
    if total <= 0:
        return {}
    return {
        emotion: value / total
        for emotion, value in sanitized.items()
    }


def _rank_score_map(score_map: Mapping[str, float] | None) -> list[dict]:
    score_map = score_map if isinstance(score_map, Mapping) else {}
    ranking = [
        {"emotion": emotion, "confidence": max(0.0, _safe_float(confidence, 0.0))}
        for emotion, confidence in score_map.items()
    ]
    ranking.sort(key=lambda item: (-item["confidence"], item["emotion"]))
    return ranking


def _confidence_margin(ranking: list[dict]) -> float:
    if not ranking:
        return 0.0
    if len(ranking) == 1:
        return max(0.0, _safe_float(ranking[0].get("confidence"), 0.0))
    return max(
        0.0,
        _safe_float(ranking[0].get("confidence"), 0.0)
        - _safe_float(ranking[1].get("confidence"), 0.0),
    )


def apply_outcome_mode(result: Mapping | None, outcome_mode: str, phase=None) -> dict:
    working_result = dict(result) if isinstance(result, Mapping) else {}
    normalized_mode = normalize_outcome_mode(outcome_mode)
    config = outcome_mode_config(normalized_mode)
    base_scores = _normalize_emotune_scores(working_result.get("all_scores"))

    if normalized_mode == "match_mood":
        ranking = _rank_score_map(base_scores)
        return {
            "emotion": ranking[0]["emotion"] if ranking else "mixed",
            "confidence": ranking[0]["confidence"] if ranking else 0.0,
            "all_scores": base_scores,
            "top_emotions": ranking[:2],
            "secondary_emotion": ranking[1]["emotion"] if len(ranking) > 1 else None,
            "confidence_margin": _confidence_margin(ranking),
            "outcome_mode": normalized_mode,
            "outcome_label": config["label"],
            "outcome_description": config["description"],
        }

    target_scores = _normalize_weight_map(config.get("target_weights"))
    target_weight = outcome_target_weight(normalized_mode, phase)
    base_weight = max(0.0, 1.0 - target_weight)

    # An emotion with no seat in target_weights (e.g. calm_me_down never wants to
    # land on "angry") gets no target-side floor to compete against. Blended
    # plainly at base_weight, a confident-enough reading can still out-score every
    # target emotion and keep the top slot -- letting the mode land right back on
    # the emotion it exists to steer away from, no matter how sure the classifier
    # is. Discounting it by base_weight again (so its ceiling is base_weight**2,
    # e.g. 0.42**2 ~= 0.18 at this mode's default) keeps it available as a
    # secondary signal for ranking without ever letting it outrank a real target
    # emotion's floor (target_weight * its own share, e.g. calm's 0.55 * 0.58 ~=
    # 0.32) -- see docs/music_therapy_guidelines.md, "angry" entry.
    combined_scores = {}
    for emotion in base_scores:
        if emotion in target_scores:
            combined_scores[emotion] = (
                base_scores.get(emotion, 0.0) * base_weight
                + target_scores[emotion] * target_weight
            )
        else:
            combined_scores[emotion] = base_scores.get(emotion, 0.0) * base_weight * base_weight

    total = sum(combined_scores.values())
    if total > 0:
        combined_scores = {
            emotion: value / total
            for emotion, value in combined_scores.items()
        }

    ranking = _rank_score_map(combined_scores)
    return {
        "emotion": ranking[0]["emotion"] if ranking else "mixed",
        "confidence": ranking[0]["confidence"] if ranking else 0.0,
        "all_scores": combined_scores,
        "top_emotions": ranking[:2],
        "secondary_emotion": ranking[1]["emotion"] if len(ranking) > 1 else None,
        "confidence_margin": _confidence_margin(ranking),
        "outcome_mode": normalized_mode,
        "outcome_label": config["label"],
        "outcome_description": config["description"],
        "outcome_phase": str(phase or "").strip().lower() or None,
        "outcome_target_weight": target_weight,
    }


def build_session_plan(
    *,
    outcome_mode: str,
    session_length_minutes: int | None,
    check_in_frequency_tracks: int | None = None,
) -> dict | None:
    normalized_mode = normalize_outcome_mode(outcome_mode)
    config = outcome_mode_config(normalized_mode)
    if session_length_minutes is None:
        target_minutes = max(_safe_int(config.get("default_session_minutes"), 0), 0)
    else:
        target_minutes = max(_safe_int(session_length_minutes), 0)
    if target_minutes <= 0:
        return None

    checkpoint_tracks = max(
        _safe_int(check_in_frequency_tracks, _safe_int(config.get("default_check_in_tracks"), 4)),
        1,
    )
    phase_cutoff = max(target_minutes // 3, 1)

    return {
        "enabled": True,
        "mode": normalized_mode,
        "label": config["label"],
        "description": config["description"],
        "target_minutes": target_minutes,
        "target_seconds": target_minutes * 60,
        "check_in_after_tracks": checkpoint_tracks,
        "next_check_in_tracks": checkpoint_tracks,
        "phase": "settle",
        "phase_cutoff_minutes": phase_cutoff,
        "check_in_prompt": config["check_in_prompt"],
        "completion_message": config["completion_message"],
        "progress_seconds": 0,
        "completed": False,
        "last_response": None,
    }


def update_session_plan_progress(
    session_plan: Mapping | None,
    *,
    duration_seconds: int,
    tracks_played: int,
) -> dict | None:
    if not isinstance(session_plan, Mapping) or not session_plan.get("enabled"):
        return None

    updated = dict(session_plan)
    updated["progress_seconds"] = max(_safe_int(duration_seconds), 0)
    updated["tracks_played"] = max(_safe_int(tracks_played), 0)

    target_seconds = max(_safe_int(updated.get("target_seconds")), 0)
    if target_seconds and updated["progress_seconds"] >= target_seconds:
        updated["phase"] = "close"
    elif updated["progress_seconds"] >= max(_safe_int(updated.get("phase_cutoff_minutes")) * 60, 60):
        updated["phase"] = "support"
    else:
        updated["phase"] = "settle"

    return updated
