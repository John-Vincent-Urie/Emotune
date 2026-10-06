from django.urls import path
from . import views
from rest_framework_simplejwt.views import TokenRefreshView

from .serializers import ActiveUserTokenRefreshSerializer

urlpatterns = [
    path('register/', views.register, name='register'),
    path('login/', views.login, name='login'),
    path('logout/', views.logout, name='logout'),
    path(
        'token/refresh/',
        TokenRefreshView.as_view(serializer_class=ActiveUserTokenRefreshSerializer),
        name='token_refresh',
    ),
    path('profile/', views.profile, name='profile'),
    path('change-password/', views.change_password, name='change_password'),
    path('password-reset/', views.password_reset_request, name='password_reset_request'),
    path('password-reset/verify/', views.password_reset_verify, name='password_reset_verify'),
    path('password-reset/confirm/', views.password_reset_confirm, name='password_reset_confirm'),
    path('update-artists/', views.update_artists, name='update_artists'),
    path('favorites/', views.favorites, name='favorites'),
    path('favorites/<str:track_id>/', views.remove_favorite, name='remove_favorite'),
    path('history/', views.history, name='history'),
    path('emotion-stats/', views.emotion_stats, name='emotion_stats'),
    path('listen-time/', views.update_listen_time, name='update_listen_time'),
]
