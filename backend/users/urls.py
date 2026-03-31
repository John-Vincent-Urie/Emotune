from django.urls import path
from . import views
from rest_framework_simplejwt.views import TokenRefreshView

urlpatterns = [
    path('register/', views.register, name='register'),
    path('login/', views.login, name='login'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('profile/', views.profile, name='profile'),
    path('change-password/', views.change_password, name='change_password'),
    path('update-artists/', views.update_artists, name='update_artists'),
    path('favorites/', views.favorites, name='favorites'),
    path('favorites/<str:track_id>/', views.remove_favorite, name='remove_favorite'),
    path('history/', views.history, name='history'),
    path('emotion-stats/', views.emotion_stats, name='emotion_stats'),
    path('listen-time/', views.update_listen_time, name='update_listen_time'),
]
