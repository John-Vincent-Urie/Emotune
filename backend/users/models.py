from django.contrib.auth.models import AbstractUser
from django.db import models
import json


class User(AbstractUser):
    """Extended user model for EmoTune"""
    email = models.EmailField(unique=True)
    terms_accepted_at = models.DateTimeField(blank=True, null=True)
    personalization_opt_in = models.BooleanField(default=True)
    spotify_id = models.CharField(max_length=255, blank=True, null=True)
    spotify_access_token = models.TextField(blank=True, null=True)
    spotify_refresh_token = models.TextField(blank=True, null=True)
    spotify_granted_scopes = models.JSONField(default=list, blank=True)
    spotify_token_expires = models.DateTimeField(blank=True, null=True)
    profile_picture = models.ImageField(upload_to='profiles/', blank=True, null=True)
    bio = models.TextField(blank=True, default='')
    is_spotify_connected = models.BooleanField(default=False)
    preferred_artists = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']

    def __str__(self):
        return self.email

    class Meta:
        db_table = 'users'


class UserPreference(models.Model):
    """Tracks user music preferences per emotion for adaptive recommendations"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='preferences')
    emotion = models.CharField(max_length=50)
    spotify_track_id = models.CharField(max_length=255)
    track_name = models.CharField(max_length=500)
    artist_name = models.CharField(max_length=500)
    play_count = models.IntegerField(default=0)
    last_played = models.DateTimeField(auto_now=True)
    total_listen_time = models.IntegerField(default=0)  # seconds

    class Meta:
        db_table = 'user_preferences'
        unique_together = ('user', 'emotion', 'spotify_track_id')
        ordering = ['-play_count', '-last_played']

    def __str__(self):
        return f"{self.user.email} - {self.emotion} - {self.track_name}"


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
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'favorite_tracks'
        unique_together = ('user', 'spotify_track_id')
        ordering = ['-added_at']

    def __str__(self):
        return f"{self.user.email} - {self.track_name}"


class PromptHistory(models.Model):
    """History of user prompts and AI responses"""
    EMOTIONS = [
        ('happy', 'Happy'), ('sad', 'Sad'), ('angry', 'Angry'),
        ('motivational', 'Motivational'), ('fear', 'Fear'),
        ('depressing', 'Depressing'), ('surprising', 'Surprising'),
        ('stressed', 'Stressed'), ('calm', 'Calm'), ('lonely', 'Lonely'),
        ('romantic', 'Romantic'), ('nostalgic', 'Nostalgic'), ('mixed', 'Mixed'),
    ]

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
