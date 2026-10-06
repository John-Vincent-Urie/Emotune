"""Process-wide cooldown after Spotify rate-limits us.

Spotify's rate limit is per app, not per user or per token, and a 429 comes
with a Retry-After telling us how long the block lasts. Before this existed,
each request kept calling Spotify anyway: one QA run against /api/analyze/
produced ~1,450 429s on the dev credentials, and calling during a block can
lengthen it.

So the first 429 starts a cooldown shared by every thread in the process, and
`SpotifyAuthClient._spotify_request` answers locally with a `rate_limited`
failure until it ends. Callers already treat `rate_limited` as "fall back to
the built-in lists" (and the pool refresh command waits out `retry_after`), so
nothing upstream needs to change.

The state lives in this process only: with several worker processes, each one
learns about the block from its own first 429.
"""
import logging
import math
import threading
import time

logger = logging.getLogger(__name__)

#: Used when a 429 arrives without a usable Retry-After. Spotify's limit is a
#: rolling 30-second window.
DEFAULT_COOLDOWN_SECONDS = 30
#: Upper bound on a single cooldown, so a malformed header cannot switch
#: Spotify off for days.
MAX_COOLDOWN_SECONDS = 24 * 60 * 60

_lock = threading.Lock()
_cooldown_until = 0.0  # time.monotonic() deadline; 0 means no cooldown
_resume_logged = True


def remaining_seconds():
    """Seconds left in the current cooldown, or 0 when Spotify may be called."""
    global _resume_logged
    with _lock:
        remaining = _cooldown_until - time.monotonic()
        if remaining > 0:
            return remaining
        if not _resume_logged:
            _resume_logged = True
            logger.info("Spotify rate-limit cooldown is over; calling Spotify again.")
        return 0.0


def retry_after_seconds():
    """The remaining cooldown as whole seconds, the way Retry-After reports it."""
    return math.ceil(remaining_seconds())


def start_cooldown(retry_after):
    """Pause Spotify calls for `retry_after` seconds (from the 429's header).

    Logs once per cooldown, not once per request: concurrent searches that hit
    the same block only extend it.
    """
    global _cooldown_until, _resume_logged
    seconds = DEFAULT_COOLDOWN_SECONDS if retry_after is None else retry_after
    seconds = min(max(float(seconds), 1.0), MAX_COOLDOWN_SECONDS)
    with _lock:
        now = time.monotonic()
        deadline = now + seconds
        if deadline <= _cooldown_until:
            return
        already_cooling = _cooldown_until > now
        _cooldown_until = deadline
        _resume_logged = False
    if not already_cooling:
        logger.warning(
            "Spotify rate-limited EmoTune (Retry-After=%s); skipping Spotify calls "
            "for %.0fs and serving built-in lists meanwhile.",
            'missing' if retry_after is None else retry_after,
            seconds,
        )


def reset():
    """Clear any cooldown. For tests."""
    global _cooldown_until, _resume_logged
    with _lock:
        _cooldown_until = 0.0
        _resume_logged = True
