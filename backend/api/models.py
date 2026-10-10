"""
Database models for the api app.

The therapist-validated song collection (Emotion, Song, EmotionSong) and the
crisis-support directory and event counter used by api/safety.py. Every
user-facing model (history, favorites) lives in the users app.
"""
from urllib.parse import quote

from django.db import models


class Emotion(models.Model):
    """One of the 13 labels the BERT classifier emits (ml/emotion_labels.py).

    `name` is the classifier's label exactly, so no LABEL_n mapping is needed;
    `display_name` is the heading the therapist's list uses ("Motivated" for
    motivational, "Scared" for fear, ...).
    """

    name = models.CharField(max_length=50, unique=True)
    display_name = models.CharField(max_length=50)
    description = models.TextField(blank=True)

    class Meta:
        db_table = 'emotions'
        ordering = ['id']

    def __str__(self):
        return self.name


class Song(models.Model):
    """A therapist-approved song. Spotify fields are empty when the song could
    not be matched on Spotify; it is still shown, just not playable in-app."""

    title = models.CharField(max_length=300)
    artist = models.CharField(max_length=300)
    spotify_track_id = models.CharField(max_length=64, blank=True, null=True)
    spotify_url = models.URLField(blank=True, null=True)
    album = models.CharField(max_length=300, blank=True)
    image = models.URLField(blank=True)
    duration_ms = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    emotions = models.ManyToManyField(Emotion, through='EmotionSong', related_name='songs')

    class Meta:
        db_table = 'songs'
        ordering = ['title', 'id']
        constraints = [
            models.UniqueConstraint(fields=['title', 'artist'], name='unique_song_title_artist'),
        ]

    def __str__(self):
        return f"{self.title} - {self.artist}"

    @property
    def uri(self):
        return f"spotify:track:{self.spotify_track_id}" if self.spotify_track_id else ''

    def as_track(self, position):
        """The track shape the app reads (agreed with the frontend, 2026-10-10)."""
        playable = bool(self.spotify_track_id)
        return {
            'id': self.spotify_track_id or f'song-{self.id}',
            'item_type': 'track',
            'name': self.title,
            'artist': self.artist,
            'album': self.album,
            'image': self.image,
            'uri': self.uri,
            # An unmatched song still gets a way in: a static Spotify search
            # link (no API call), so the student can look it up themselves.
            'spotify_url': (
                self.spotify_url
                or f"https://open.spotify.com/search/{quote(f'{self.title} {self.artist}'.strip())}"
            ),
            'duration_ms': self.duration_ms,
            'preview_url': None,
            'recommendation_source': 'therapist_list',
            'song_id': self.id,
            'position': position,
            'playable': playable,
        }


class EmotionSong(models.Model):
    """A therapist-approved emotion-song pairing. `position` is the song's place
    in that emotion's list in docs/music.md, which is the order the app shows."""

    emotion = models.ForeignKey(Emotion, on_delete=models.CASCADE, related_name='song_links')
    song = models.ForeignKey(Song, on_delete=models.CASCADE, related_name='emotion_links')
    position = models.PositiveIntegerField()

    class Meta:
        db_table = 'emotion_songs'
        ordering = ['emotion', 'position']
        constraints = [
            models.UniqueConstraint(fields=['emotion', 'song'], name='unique_emotion_song'),
        ]

    def __str__(self):
        return f"{self.emotion.name} #{self.position}: {self.song}"


def songs_for_emotion(emotion_name):
    """(Emotion or None, every active approved song for it in therapist order)."""
    emotion = Emotion.objects.filter(name=str(emotion_name or '').strip().lower()).first()
    if emotion is None:
        return None, []
    links = (
        EmotionSong.objects.filter(emotion=emotion, song__is_active=True)
        .select_related('song')
        .order_by('position', 'song_id')
    )
    return emotion, [link.song.as_track(link.position) for link in links]


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
