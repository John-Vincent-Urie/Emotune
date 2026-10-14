"""Listening-session plans: the session-length card, its progress, and when the
app asks "is this helping?".

This used to be api/recommendation_session.py, which also blended the detected
emotion toward a "Calm Me Down" target to pick songs and carried the taste
toggles. Songs now come only from the therapist-approved list for the detected
emotion (api/models.py), so all that is left here is the session itself: each
emotion's mode only sets the check-in wording and how often it is asked.
"""
from __future__ import annotations

from typing import Mapping

OUTCOME_MODE_CONFIG = {
    "match_mood": {
        "label": "Match My Mood",
        "description": "Stay close to the emotion the classifier detected.",
        "default_session_minutes": 20,
        "default_check_in_tracks": 5,
        "check_in_prompt": "Is this session matching how you want to feel right now?",
        "completion_message": "Session locked in. I will stop interrupting and let the music carry you.",
    },
    "calm_me_down": {
        "label": "Calm Me Down",
        "description": "Gently de-escalate intense feelings into a steadier state.",
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
