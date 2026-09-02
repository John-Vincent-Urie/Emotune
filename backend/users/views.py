from rest_framework import status, permissions
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.response import Response
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import get_user_model, authenticate
from django.db.models import Count
from .models import (
    EMOTION_CHOICES, FavoriteTrack, ListeningSession, PromptHistory, UserPreference,
)
from .throttles import (
    LoginEmailThrottle, LoginIPThrottle, PasswordChangeThrottle, RegisterThrottle,
)
from .serializers import (
    UserSerializer, RegisterSerializer, ChangePasswordSerializer,
    FavoriteTrackSerializer, PromptHistorySerializer, UserPreferenceSerializer
)

User = get_user_model()

VALID_EMOTIONS = frozenset(value for value, _label in EMOTION_CHOICES)


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
@throttle_classes([RegisterThrottle])
def register(request):
    serializer = RegisterSerializer(data=request.data)
    if serializer.is_valid():
        user = serializer.save()
        refresh = RefreshToken.for_user(user)
        return Response({
            'user': UserSerializer(user).data,
            'access': str(refresh.access_token),
            'refresh': str(refresh),
        }, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
@throttle_classes([LoginIPThrottle, LoginEmailThrottle])
def login(request):
    email = request.data.get('email')
    password = request.data.get('password')
    user = authenticate(request, username=email, password=password)
    if user:
        refresh = RefreshToken.for_user(user)
        return Response({
            'user': UserSerializer(user).data,
            'access': str(refresh.access_token),
            'refresh': str(refresh),
        })
    return Response({'error': 'Invalid credentials'}, status=status.HTTP_401_UNAUTHORIZED)


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def logout(request):
    """Revoke the refresh token the caller presents.

    Dropping the tokens on the device is not revocation: the refresh token
    stays valid for its full lifetime, so a copy lifted from a lost phone can
    still mint access tokens for weeks. Blacklisting it is what ends the
    session for real.

    Deliberately unauthenticated: the refresh token is itself the credential,
    and requiring a live access token would leave anyone whose access token had
    already expired unable to log out.
    """
    refresh_token = str(request.data.get('refresh') or '').strip()
    if not refresh_token:
        return Response(
            {'error': 'A refresh token is required to log out.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        RefreshToken(refresh_token).blacklist()
    except TokenError:
        # Expired, already blacklisted, or not one of ours. The token cannot be
        # used either way, so this is still a successful logout; saying which
        # would only tell an attacker whether a token is live.
        pass

    return Response(status=status.HTTP_205_RESET_CONTENT)


@api_view(['GET', 'PUT', 'PATCH'])
def profile(request):
    if request.method == 'GET':
        return Response(UserSerializer(request.user).data)
    serializer = UserSerializer(request.user, data=request.data, partial=True)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@throttle_classes([PasswordChangeThrottle])
def change_password(request):
    serializer = ChangePasswordSerializer(data=request.data)
    if serializer.is_valid():
        user = request.user
        if not user.check_password(serializer.validated_data['old_password']):
            return Response({'error': 'Wrong password'}, status=status.HTTP_400_BAD_REQUEST)
        user.set_password(serializer.validated_data['new_password'])
        user.save()
        return Response({'message': 'Password changed successfully'})
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['PUT'])
def update_artists(request):
    """Update preferred artists"""
    artists = request.data.get('preferred_artists', [])
    request.user.preferred_artists = artists
    request.user.save()
    return Response({'preferred_artists': artists})


# Favorites
def _normalized_favorite_emotion(value):
    """Keep only emotions the recommender knows; anything else is untagged."""
    emotion = str(value or '').strip().lower()
    return emotion if emotion in VALID_EMOTIONS else ''


@api_view(['GET', 'POST'])
def favorites(request):
    if request.method == 'GET':
        favs = FavoriteTrack.objects.filter(user=request.user)
        emotion = _normalized_favorite_emotion(request.query_params.get('emotion'))
        if emotion:
            favs = favs.filter(emotion=emotion).order_by('added_at')
        return Response(FavoriteTrackSerializer(favs, many=True).data)
    track_id = str(request.data.get('spotify_track_id') or '').strip()
    emotion = _normalized_favorite_emotion(request.data.get('emotion'))
    if track_id:
        existing = FavoriteTrack.objects.filter(
            user=request.user,
            spotify_track_id=track_id,
        ).first()
        if existing is not None:
            # An older favorite predates emotion tagging, or was hearted before
            # the emotion was known. Keep the original tag once it exists so the
            # "first favorite for this emotion" order stays stable.
            if emotion and not existing.emotion:
                existing.emotion = emotion
                existing.save(update_fields=['emotion'])
            return Response(FavoriteTrackSerializer(existing).data, status=status.HTTP_200_OK)
    serializer = FavoriteTrackSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save(user=request.user, emotion=emotion)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['DELETE'])
def remove_favorite(request, track_id):
    FavoriteTrack.objects.filter(user=request.user, spotify_track_id=track_id).delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


# History
@api_view(['GET'])
def history(request):
    history_qs = PromptHistory.objects.filter(user=request.user)
    return Response(PromptHistorySerializer(history_qs, many=True).data)


@api_view(['GET'])
def emotion_stats(request):
    """Get emotion distribution for pie chart"""
    stats = PromptHistory.objects.filter(user=request.user)\
        .values('detected_emotion')\
        .annotate(count=Count('id'))\
        .order_by('-count')
    return Response(list(stats))


@api_view(['POST'])
def update_listen_time(request):
    """Update listening time for adaptive recommendations"""
    track_id = request.data.get('track_id')
    emotion = request.data.get('emotion')
    duration = request.data.get('duration', 0)
    track_name = request.data.get('track_name', '')
    artist_name = request.data.get('artist_name', '')
    item_type = str(request.data.get('item_type', 'track') or 'track').strip().lower()
    history_id = request.data.get('history_id')
    train_session = request.data.get('train_session', True)

    prompt_history = None
    if history_id:
        prompt_history = PromptHistory.objects.filter(
            id=history_id,
            user=request.user,
        ).first()

    if prompt_history is not None:
        prompt_history.session_duration = max(int(duration or 0), 0)
        music_picker_data = (
            dict(prompt_history.music_picker_data)
            if isinstance(prompt_history.music_picker_data, dict)
            else {}
        )
        session_plan = music_picker_data.get('session_plan')
        if isinstance(session_plan, dict):
            session_plan = dict(session_plan)
            session_plan['progress_seconds'] = max(int(duration or 0), 0)
            music_picker_data['session_plan'] = session_plan
        prompt_history.music_picker_data = music_picker_data
        prompt_history.save(update_fields=['session_duration', 'music_picker_data'])

        personalization = music_picker_data.get('personalization')
        if isinstance(personalization, dict) and personalization.get('train_session') is False:
            train_session = False

    if (
        not track_id
        or not emotion
        or item_type != 'track'
        or str(artist_name).strip().lower() == 'open in spotify'
    ):
        return Response({'status': 'skipped'})

    if str(train_session).strip().lower() in {'false', '0', 'no'}:
        return Response({'status': 'tracking_disabled'})

    if prompt_history is not None:
        ListeningSession.objects.update_or_create(
            user=request.user,
            prompt_history=prompt_history,
            spotify_track_id=track_id,
            defaults={
                'track_name': track_name,
                'listen_duration': max(int(duration or 0), 0),
                'completed': max(int(duration or 0), 0) >= 30,
            },
        )

    pref, _created = UserPreference.objects.get_or_create(
        user=request.user,
        emotion=emotion,
        spotify_track_id=track_id,
        defaults={'track_name': track_name, 'artist_name': artist_name}
    )
    pref.play_count += 1
    pref.total_listen_time += duration
    pref.save()
    return Response({'status': 'updated'})
