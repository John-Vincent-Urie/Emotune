import secrets
from datetime import timedelta

from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


EMOTION_CHOICES = [
    ('happy', 'Happy'), ('sad', 'Sad'), ('angry', 'Angry'),
    ('motivational', 'Motivational'), ('fear', 'Fear'),
    ('depressing', 'Depressing'), ('surprising', 'Surprising'),
    ('stressed', 'Stressed'), ('calm', 'Calm'), ('lonely', 'Lonely'),
    ('romantic', 'Romantic'), ('nostalgic', 'Nostalgic'), ('mixed', 'Mixed'),
]


class User(AbstractUser):
    """Extended user model for EmoTune"""
    # Sign-in is by email, so `username` is only the display name the app
    # greets people with. Drop AbstractUser's handle rules: "Maria Santos" has
    # a space, and two people can both be called Maria.
    # Labelled for the password similarity check, whose message names the field.
    username = models.CharField('display name', max_length=150)
    email = models.EmailField(unique=True)
    terms_accepted_at = models.DateTimeField(blank=True, null=True)
    spotify_id = models.CharField(max_length=255, blank=True, null=True)
    spotify_access_token = models.TextField(blank=True, null=True)
    spotify_refresh_token = models.TextField(blank=True, null=True)
    spotify_granted_scopes = models.JSONField(default=list, blank=True)
    spotify_token_expires = models.DateTimeField(blank=True, null=True)
    profile_picture = models.ImageField(upload_to='profiles/', blank=True, null=True)
    bio = models.TextField(blank=True, default='')
    is_spotify_connected = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']

    def __str__(self):
        return self.email

    class Meta:
        db_table = 'users'



class FavoriteTrack(models.Model):
    """User's favorite tracks"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='favorites')
    spotify_track_id = models.CharField(max_length=255)
    track_name = models.CharField(max_length=500)
    artist_name = models.CharField(max_length=500)
    album_name = models.CharField(max_length=500, blank=True)
    album_image = models.URLField(blank=True)
    preview_url = models.URLField(blank=True, null=True)
    duration_ms = models.IntegerField(default=0)
    # The emotion the user was listening under when they hearted this track.
    # "More familiar" replays these first the next time that emotion comes up.
    emotion = models.CharField(
        max_length=50,
        choices=EMOTION_CHOICES,
        blank=True,
        default='',
        db_index=True,
    )
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'favorite_tracks'
        unique_together = ('user', 'spotify_track_id')
        ordering = ['-added_at']

    def __str__(self):
        return f"{self.user.email} - {self.track_name}"


class PromptHistory(models.Model):
    """History of user prompts and AI responses"""
    EMOTIONS = EMOTION_CHOICES

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='prompt_history')
    prompt_text = models.TextField()
    detected_emotion = models.CharField(max_length=50, choices=EMOTIONS)
    emotion_confidence = models.FloatField(default=0.0)
    emotion_scores = models.JSONField(default=dict)  # All emotion probabilities
    ai_response = models.TextField()
    playlist_data = models.JSONField(default=list)  # Recommended tracks
    music_picker_data = models.JSONField(default=dict, blank=True)
    session_duration = models.IntegerField(default=0)  # seconds listened
    felt_better_response = models.BooleanField(null=True)  # User response to "Feel better?"
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'prompt_history'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.email} - {self.detected_emotion} - {self.created_at}"


class ListeningSession(models.Model):
    """Track active listening sessions for adaptive recommendations"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sessions')
    prompt_history = models.ForeignKey(PromptHistory, on_delete=models.CASCADE)
    spotify_track_id = models.CharField(max_length=255)
    track_name = models.CharField(max_length=500)
    listen_duration = models.IntegerField(default=0)  # seconds
    completed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'listening_sessions'
        ordering = ['-created_at']


class PasswordResetCode(models.Model):
    """A short-lived one-time code emailed to someone who forgot their password.

    Only the hash is kept. A six-digit code is small enough to brute force from
    a database dump if it were stored in the clear, and the whole point of the
    code is that holding it proves control of the mailbox.
    """

    CODE_LENGTH = 6
    LIFETIME = timedelta(minutes=10)
    # Five wrong guesses kills the code, so 10 minutes of grinding cannot walk
    # the million-wide keyspace even if the throttles were somehow bypassed.
    MAX_ATTEMPTS = 5

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='password_reset_codes',
    )
    code_hash = models.CharField(max_length=128)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    attempts = models.PositiveIntegerField(default=0)
    used_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = 'password_reset_codes'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.email} - reset code - {self.created_at}"

    @classmethod
    def issue(cls, user):
        """Drop any outstanding code for this user and mint a fresh one.

        Returns the record and the plaintext code, which is the only moment the
        code exists in readable form -- hand it straight to the mailer.
        """
        cls.objects.filter(user=user, used_at__isnull=True).delete()
        code = f'{secrets.randbelow(10 ** cls.CODE_LENGTH):0{cls.CODE_LENGTH}d}'
        record = cls.objects.create(
            user=user,
            code_hash=make_password(code),
            expires_at=timezone.now() + cls.LIFETIME,
        )
        return record, code

    @property
    def is_expired(self):
        return timezone.now() >= self.expires_at

    @property
    def is_usable(self):
        return (
            self.used_at is None
            and not self.is_expired
            and self.attempts < self.MAX_ATTEMPTS
        )

    @property
    def attempts_remaining(self):
        return max(self.MAX_ATTEMPTS - self.attempts, 0)

    def matches(self, code):
        return check_password(str(code or '').strip(), self.code_hash)
