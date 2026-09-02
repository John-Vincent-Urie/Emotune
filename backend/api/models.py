"""
Database models for the api app.

This holds only the shared emotion track pool: the pre-warmed candidate cache
that keeps per-request Spotify catalog searches off the critical path. Every
user-facing model (history, favorites, preferences) lives in the users app.
"""
from django.db import models
from django.utils import timezone


class EmotionTrackPool(models.Model):
    """Pre-fetched Spotify catalog candidates for one emotion.

    Rows are shared by every user because they hold only the emotion-baseline
    half of a recommendation -- what `_build_recommendation_queries` returns
    for an emotion with no user-specific inputs (no preferred artists, no LLM
    queries, no seed track/artist, no playlist category). Per-user
    personalization still runs live on every request and gets blended on top
    of these candidates, so a pool hit never flattens one user's
    recommendations into another's.

    This is a short-lived cache, not a local mirror of the Spotify catalog:
    rows past SPOTIFY_TRACK_POOL_MAX_AGE_SECONDS are ignored and refetched.
    """

    emotion = models.CharField(max_length=50, unique=True)
    tracks = models.JSONField(default=list)
    queries_used = models.JSONField(default=list, blank=True)
    refreshed_at = models.DateTimeField(default=timezone.now, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'emotion_track_pools'
        ordering = ['emotion']

    def __str__(self):
        return f"{self.emotion} ({len(self.tracks or [])} tracks)"

    @property
    def age_seconds(self):
        return max((timezone.now() - self.refreshed_at).total_seconds(), 0.0)
