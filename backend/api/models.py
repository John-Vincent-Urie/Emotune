"""
Database models for the api app.

This holds the shared emotion track pool (the pre-warmed candidate cache that
keeps per-request Spotify catalog searches off the critical path) and the
crisis-support directory and event counter used by api/safety.py. Every
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


class SupportResource(models.Model):
    """A hotline, counselor, or clinic shown to users who may be at risk.

    Managed in the Django admin, never hardcoded: a crisis number that is wrong
    or out of date is worse than none, so only rows an admin has marked
    `is_verified` (and that are active) ever reach the app. Re-check entries
    periodically and bump `verified_at` when you do.
    """

    KIND_EMERGENCY = 'emergency'
    KIND_HOTLINE = 'hotline'
    KIND_COUNSELOR = 'counselor'
    KIND_CLINIC = 'clinic'
    KIND_SCHOOL = 'school'
    KIND_CHOICES = [
        (KIND_EMERGENCY, 'Emergency services'),
        (KIND_HOTLINE, 'Crisis hotline'),
        (KIND_COUNSELOR, 'Therapist / counselor'),
        (KIND_CLINIC, 'Clinic / hospital'),
        (KIND_SCHOOL, 'School guidance office'),
    ]

    MODE_ONLINE = 'online'
    MODE_IN_PERSON = 'in_person'
    MODE_BOTH = 'both'
    MODE_CHOICES = [
        (MODE_ONLINE, 'Online / phone'),
        (MODE_IN_PERSON, 'In person'),
        (MODE_BOTH, 'Online and in person'),
    ]

    name = models.CharField(max_length=150)
    kind = models.CharField(max_length=20, choices=KIND_CHOICES, default=KIND_HOTLINE)
    description = models.TextField(blank=True, help_text='One or two sentences shown under the name.')
    phone = models.CharField(max_length=50, blank=True, help_text='Digits as they should be dialed, e.g. 1553 or 09175584673.')
    sms = models.CharField(max_length=50, blank=True)
    email = models.EmailField(blank=True)
    website = models.URLField(blank=True)
    hours = models.CharField(max_length=100, blank=True, help_text='e.g. "24/7" or "Mon-Fri 8am-5pm".')
    location = models.CharField(max_length=150, blank=True)
    service_mode = models.CharField(max_length=20, choices=MODE_CHOICES, default=MODE_ONLINE)
    is_free = models.BooleanField(default=False)
    languages = models.CharField(max_length=100, blank=True, help_text='e.g. "English, Filipino".')
    is_verified = models.BooleanField(
        default=False,
        help_text='Only verified entries are shown. Verify by actually contacting the service.',
    )
    verified_at = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=100, help_text='Lower shows first.')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'support_resources'
        ordering = ['sort_order', 'name']

    def __str__(self):
        return f"{self.name} ({self.get_kind_display()})"

    def to_payload(self):
        return {
            'id': self.id,
            'name': self.name,
            'kind': self.kind,
            'kind_label': self.get_kind_display(),
            'description': self.description,
            'phone': self.phone,
            # Ready-made link so any client can make the number tap-to-dial.
            'phone_uri': f"tel:{''.join(ch for ch in self.phone if ch.isdigit() or ch == '+')}" if self.phone else '',
            'sms': self.sms,
            'email': self.email,
            'website': self.website,
            'hours': self.hours,
            'location': self.location,
            'service_mode': self.service_mode,
            'is_free': self.is_free,
            'languages': self.languages,
        }

    @classmethod
    def visible(cls):
        return cls.objects.filter(is_verified=True, is_active=True)


class SupportEvent(models.Model):
    """One time the safety check fired. Deliberately holds no text and no user.

    Exists so the team can show the feature works and how often each tier
    fires, without the database ever holding what a person at risk wrote or
    who wrote it.
    """

    LEVEL_CHOICES = [('crisis', 'Crisis'), ('concern', 'Concern')]
    TRIGGER_CHOICES = [('phrase', 'Phrase match'), ('model', 'Classifier')]

    level = models.CharField(max_length=10, choices=LEVEL_CHOICES)
    trigger = models.CharField(max_length=10, choices=TRIGGER_CHOICES)
    source = models.CharField(max_length=50, help_text='Endpoint that detected it.')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'support_events'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.level} via {self.trigger} at {self.created_at:%Y-%m-%d %H:%M}"
