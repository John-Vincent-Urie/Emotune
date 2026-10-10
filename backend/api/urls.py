from django.urls import path
from . import views

urlpatterns = [
    # Core
    path('analyze/', views.analyze_emotion, name='analyze_emotion'),
    path('recommend-by-emotion/', views.recommend_by_emotion, name='recommend_by_emotion'),
    path('feel-better/', views.check_feel_better, name='feel_better'),
    path('feel-better-response/', views.feel_better_response, name='feel_better_response'),
    path('support-resources/', views.support_resources, name='support_resources'),
    
    # Spotify
    path('spotify/app-remote-config/', views.spotify_app_remote_config, name='spotify_app_remote_config'),
    path('spotify/auth-url/', views.spotify_auth_url, name='spotify_auth_url'),
    path('spotify/callback/', views.spotify_callback, name='spotify_callback'),
    path('spotify/debug-status/', views.spotify_debug_status, name='spotify_debug_status'),
    path('spotify/prepare-playback/', views.spotify_prepare_playback, name='spotify_prepare_playback'),
    path('spotify/player-control/', views.spotify_player_control, name='spotify_player_control'),
    path('spotify/disconnect/', views.spotify_disconnect, name='spotify_disconnect'),
    
    # Admin
    path('admin/dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('admin/users/', views.admin_users, name='admin_users'),
    path('admin/users/<int:user_id>/', views.admin_delete_user, name='admin_delete_user'),
]
