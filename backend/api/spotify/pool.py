"""
Shared per-emotion candidate pool ("waiting room") for recommendations.

Every recommendation request used to pay for a chain of live Spotify catalog
searches before it could answer. Those searches are the same for everyone
asking about the same emotion, so we keep their results in
`EmotionTrackPool` and serve them straight from the database, while the
per-user half of the pipeline (top tracks, saved tracks, taste profile,
preferred-artist queries) still runs live and gets blended on top.

Freshness has three bands:

* younger than SPOTIFY_TRACK_POOL_FRESH_SECONDS -- served as is;
* older than that but younger than SPOTIFY_TRACK_POOL_MAX_AGE_SECONDS --
  still served (stale beats slow), and flagged so a refresh can be scheduled;
* older than the max age -- ignored, so the request falls back to live search
  and self-heals the pool even if nobody ever runs the refresh command.

Every database call here is best-effort: a pool that cannot be read or
written must never break a recommendation, it just costs the request its
live searches.
"""
import logging
import random

from django.conf import settings
from django.utils import timezone

from .constants import EMOTION_QUERY_PROFILES
from .utils import _track_match_key

logger = logging.getLogger('api.spotify_service')

POOL_STATE_FRESH = 'fresh'
POOL_STATE_STALE = 'stale'
POOL_STATE_EXPIRED = 'expired'
POOL_STATE_MISSING = 'missing'
POOL_STATE_DISABLED = 'disabled'
POOL_STATE_ERROR = 'error'

#: Every emotion the pool can be warmed for, in a stable order.
POOL_EMOTIONS = tuple(EMOTION_QUERY_PROFILES.keys())


def normalize_emotion(emotion):
    return str(emotion or 'mixed').strip().lower() or 'mixed'


def is_enabled():
    return bool(getattr(settings, 'SPOTIFY_TRACK_POOL_ENABLED', True))


def target_size():
    return max(int(getattr(settings, 'SPOTIFY_TRACK_POOL_TARGET_SIZE', 100) or 100), 1)


def fresh_seconds():
    return max(float(getattr(settings, 'SPOTIFY_TRACK_POOL_FRESH_SECONDS', 6 * 3600)), 0.0)


def max_age_seconds():
    return max(
        float(getattr(settings, 'SPOTIFY_TRACK_POOL_MAX_AGE_SECONDS', 24 * 3600)),
        fresh_seconds(),
    )


def live_query_budget_seconds():
    """Time a pool hit may still spend on the user-specific queries."""
    return max(
        float(getattr(settings, 'SPOTIFY_TRACK_POOL_LIVE_QUERY_BUDGET_SECONDS', 1.5)),
        0.0,
    )


def live_query_share():
    """Share of the candidate target the user-specific queries may fill."""
    raw_share = float(getattr(settings, 'SPOTIFY_TRACK_POOL_LIVE_QUERY_SHARE', 0.4))
    return min(max(raw_share, 0.0), 1.0)


def refresh_budget_seconds():
    return max(
        float(getattr(settings, 'SPOTIFY_TRACK_POOL_REFRESH_BUDGET_SECONDS', 25.0)),
        1.0,
    )


def state_for_age(age_seconds):
    if age_seconds <= fresh_seconds():
        return POOL_STATE_FRESH
    if age_seconds <= max_age_seconds():
        return POOL_STATE_STALE
    return POOL_STATE_EXPIRED


def read_pool(emotion):
    """Return pool details for `emotion`, or None when it cannot be served.

    A returned dict always carries a non-empty `tracks` list; the caller only
    has to look at `state` to decide whether to schedule a refresh.
    """
    if not is_enabled():
        return None

    from api.models import EmotionTrackPool

    normalized_emotion = normalize_emotion(emotion)
    try:
        pool = EmotionTrackPool.objects.filter(emotion=normalized_emotion).first()
    except Exception:
        logger.exception("Failed to read the emotion track pool for %r", normalized_emotion)
        return None

    if pool is None:
        return None

    tracks = [track for track in (pool.tracks or []) if isinstance(track, dict) and track.get('id')]
    if not tracks:
        return None

    age_seconds = pool.age_seconds
    state = state_for_age(age_seconds)
    if state == POOL_STATE_EXPIRED:
        logger.info(
            "Ignoring expired emotion track pool for %r (age=%.0fs)",
            normalized_emotion,
            age_seconds,
        )
        return None

    return {
        'emotion': normalized_emotion,
        'state': state,
        'tracks': tracks,
        'age_seconds': age_seconds,
        'queries_used': list(pool.queries_used or []),
        'refreshed_at': pool.refreshed_at,
    }


def sample_tracks(pool_tracks, *, limit, seen_track_ids=None, seen_track_match_keys=None):
    """Pick up to `limit` unseen tracks from a pool, in random order.

    The sampling is what keeps a cached pool from handing every user (and the
    same user twice in a row) an identical playlist, which would also starve
    the taste profile of new signal. Pools are deliberately kept several times
    larger than a playlist so there is something to sample from.
    """
    if limit <= 0:
        return []

    seen_track_ids = set(seen_track_ids or ())
    seen_track_match_keys = set(seen_track_match_keys or ())

    candidates = []
    for track in pool_tracks or []:
        if not isinstance(track, dict):
            continue
        track_id = track.get('id')
        track_match_key = _track_match_key(track)
        if not track_id or track_id in seen_track_ids:
            continue
        if track_match_key and track_match_key in seen_track_match_keys:
            continue
        seen_track_ids.add(track_id)
        if track_match_key:
            seen_track_match_keys.add(track_match_key)
        candidates.append(track)

    if len(candidates) > limit:
        candidates = random.sample(candidates, limit)
    else:
        random.shuffle(candidates)

    sampled_tracks = []
    for track in candidates:
        pooled_track = dict(track)
        pooled_track['pool_cached'] = True
        sampled_tracks.append(pooled_track)
    return sampled_tracks


def store_pool(emotion, tracks, queries_used=None, *, force=False):
    """Replace the pool for `emotion`. Returns the stored track count.

    Without `force`, a smaller candidate set never replaces a bigger one that
    is still within its max age: requests warm the pool opportunistically with
    only a playlist's worth of tracks, and that must not shrink the deep pool
    the refresh command builds.
    """
    if not is_enabled():
        return 0

    from api.models import EmotionTrackPool

    normalized_emotion = normalize_emotion(emotion)
    stored_tracks = []
    seen_track_ids = set()
    for track in tracks or []:
        if not isinstance(track, dict):
            continue
        track_id = track.get('id')
        if not track_id or track_id in seen_track_ids:
            continue
        seen_track_ids.add(track_id)
        # `pool_cached` is stamped on read, not stored, so a pool refreshed
        # from a previous pool's tracks cannot accumulate the flag.
        stored_tracks.append({key: value for key, value in track.items() if key != 'pool_cached'})
        if len(stored_tracks) >= target_size():
            break

    if not stored_tracks:
        return 0

    try:
        if not force:
            existing_pool = EmotionTrackPool.objects.filter(emotion=normalized_emotion).first()
            if (
                existing_pool is not None
                and existing_pool.age_seconds <= max_age_seconds()
                and len(existing_pool.tracks or []) >= len(stored_tracks)
            ):
                return 0

        EmotionTrackPool.objects.update_or_create(
            emotion=normalized_emotion,
            defaults={
                'tracks': stored_tracks,
                'queries_used': list(queries_used or []),
                'refreshed_at': timezone.now(),
            },
        )
    except Exception:
        logger.exception("Failed to store the emotion track pool for %r", normalized_emotion)
        return 0

    logger.info(
        "Stored %d pooled tracks for emotion %r",
        len(stored_tracks),
        normalized_emotion,
    )
    return len(stored_tracks)
