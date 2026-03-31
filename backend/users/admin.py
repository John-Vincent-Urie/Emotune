from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, UserPreference, FavoriteTrack, PromptHistory, ListeningSession

@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ['email', 'username', 'is_spotify_connected', 'created_at']
    fieldsets = UserAdmin.fieldsets + (
        ('EmoTune', {'fields': ('spotify_id', 'is_spotify_connected', 'preferred_artists', 'bio')}),
    )

@admin.register(PromptHistory)
class PromptHistoryAdmin(admin.ModelAdmin):
    list_display = ['user', 'detected_emotion', 'emotion_confidence', 'created_at']
    list_filter = ['detected_emotion']

admin.site.register(FavoriteTrack)
admin.site.register(UserPreference)
admin.site.register(ListeningSession)
