import logging

from rest_framework import status, permissions
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.response import Response
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import get_user_model, authenticate
from django.db.models import Count
from django.utils import timezone
from .emails import send_password_reset_code
from .models import (
    EMOTION_CHOICES, FavoriteTrack, ListeningSession, PasswordResetCode,
    PromptHistory,
)
from .throttles import (
    LoginEmailThrottle, LoginIPThrottle, PasswordChangeThrottle,
    PasswordResetEmailThrottle, PasswordResetIPThrottle,
    PasswordResetVerifyEmailThrottle, PasswordResetVerifyIPThrottle,
    RegisterThrottle,
)
from .serializers import (
    UserSerializer, RegisterSerializer, ChangePasswordSerializer,
    FavoriteTrackSerializer, PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer, PasswordResetVerifySerializer,
    PromptHistorySerializer
)

logger = logging.getLogger(__name__)

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
    # Register stores addresses trimmed and lowercased, but phone keyboards
    # capitalize the first letter and admin-made accounts can be mixed case, so
    # match the stored address case-insensitively (as password reset does).
    email = str(request.data.get('email') or '').strip()
    password = request.data.get('password')
    matches = list(User.objects.filter(email__iexact=email).values_list('email', flat=True))
    stored_email = email.lower() if email.lower() in matches else (matches[0] if matches else email)
    user = authenticate(request, username=stored_email, password=password)
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
    serializer = ChangePasswordSerializer(data=request.data, context={'user': request.user})
    if serializer.is_valid():
        user = request.user
        if not user.check_password(serializer.validated_data['old_password']):
            return Response({'error': 'Wrong password'}, status=status.HTTP_400_BAD_REQUEST)
        user.set_password(serializer.validated_data['new_password'])
        user.save()
        return Response({'message': 'Password changed successfully'})
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# Forgotten-password reset, by one-time code emailed to the account address.

# Returned whether or not the address has an account: answering differently
# would turn this endpoint into a way to test which emails are registered.
_RESET_SENT_MESSAGE = (
    'If that email has an EmoTune account, a reset code is on its way.'
)
_RESET_CODE_INVALID = 'That code is invalid or has expired. Request a new one.'


def _resolve_reset_code(email, code):
    """Look up the live code for an address and check it.

    Returns ``(user, record, error_response)`` with exactly one of the first
    pair or the error populated. A wrong guess is counted here, so both the
    verify and confirm endpoints burn attempts at the same rate.
    """
    user = User.objects.filter(email__iexact=email).first()
    record = None
    if user is not None:
        record = (
            PasswordResetCode.objects
            .filter(user=user, used_at__isnull=True)
            .order_by('-created_at')
            .first()
        )

    # No account, no code, expired, already spent, or out of attempts all
    # collapse to one answer -- each distinction would leak something.
    if user is None or record is None or not record.is_usable:
        return None, None, Response(
            {'error': _RESET_CODE_INVALID},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not record.matches(code):
        record.attempts += 1
        record.save(update_fields=['attempts'])
        if record.attempts_remaining == 0:
            return None, None, Response(
                {'error': 'Too many wrong codes. Request a new one.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        # The count goes in the message as well as the field: the app surfaces
        # `error` verbatim, and "4 tries left" is the part that changes what
        # the user does next.
        tries = record.attempts_remaining
        noun = 'try' if tries == 1 else 'tries'
        return None, None, Response(
            {
                'error': f'That code is not right. {tries} {noun} left.',
                'attempts_remaining': tries,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    return user, record, None


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
@throttle_classes([PasswordResetIPThrottle, PasswordResetEmailThrottle])
def password_reset_request(request):
    """Email a one-time code to the address, if an account owns it."""
    serializer = PasswordResetRequestSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    email = serializer.validated_data['email']
    user = User.objects.filter(email__iexact=email).first()

    if user is not None:
        record, code = PasswordResetCode.issue(user)
        try:
            send_password_reset_code(user, code)
        except Exception:
            # The code is useless to a user who never received it, and leaving
            # it live would only eat into their attempt budget later.
            record.delete()
            logger.exception('Password reset mail failed for %s', email)
            # This does reveal that the address exists, but only while mail is
            # broken -- and a silent success would strand the user instead.
            return Response(
                {'error': 'Could not send the code right now. Try again shortly.'},
                status=status.HTTP_502_BAD_GATEWAY,
            )

    return Response({
        'message': _RESET_SENT_MESSAGE,
        'expires_in_minutes': int(PasswordResetCode.LIFETIME.total_seconds() // 60),
        'code_length': PasswordResetCode.CODE_LENGTH,
    })


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
@throttle_classes([PasswordResetVerifyIPThrottle, PasswordResetVerifyEmailThrottle])
def password_reset_verify(request):
    """Check a code without spending it, so the app can gate its next step."""
    serializer = PasswordResetVerifySerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    _user, record, error = _resolve_reset_code(
        serializer.validated_data['email'],
        serializer.validated_data['code'],
    )
    if error is not None:
        return error
    return Response({'valid': True, 'expires_at': record.expires_at})


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
@throttle_classes([PasswordResetVerifyIPThrottle, PasswordResetVerifyEmailThrottle])
def password_reset_confirm(request):
    """Spend the code and set the new password."""
    serializer = PasswordResetConfirmSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    user, record, error = _resolve_reset_code(
        serializer.validated_data['email'],
        serializer.validated_data['code'],
    )
    if error is not None:
        return error

    user.set_password(serializer.validated_data['new_password'])
    user.save(update_fields=['password'])

    record.used_at = timezone.now()
    record.save(update_fields=['used_at'])
    PasswordResetCode.objects.filter(user=user, used_at__isnull=True).delete()

    # Whoever knew the old password may still hold a live session. A reset is
    # how someone recovers a compromised account, so end those sessions too.
    for token in OutstandingToken.objects.filter(user=user):
        BlacklistedToken.objects.get_or_create(token=token)

    return Response({'message': 'Password updated. You can log in with it now.'})


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


# A listen past this share of a track is the user staying with the pick.
# Below it, they left -- which is the negative the ranker has to learn from.
LISTENED_THROUGH_RATIO = 0.6
# Used when the client cannot tell us how long the track is.
LISTENED_THROUGH_FALLBACK_SECONDS = 30


def _listen_was_meaningful(listen_seconds, track_length_seconds):
    """Did the user actually stay with this track?

    Judged against the track's own length, because a flat threshold calls 30
    seconds of a six-minute song a completed listen and 25 seconds of a
    28-second interlude a skip.
    """
    if track_length_seconds > 0:
        return listen_seconds >= track_length_seconds * LISTENED_THROUGH_RATIO
    return listen_seconds >= LISTENED_THROUGH_FALLBACK_SECONDS


@api_view(['POST'])
def update_listen_time(request):
    """Record how a playback ended.

    Advances the listening session's progress (the session card and the
    feel-better check-ins read it) and keeps the listening history. Nothing here
    trains or personalizes anything any more: the songs are the therapist's
    fixed list, so the old preference counters and "train on this session"
    switch went with the ranking (2026-10-10).
    """
    track_id = request.data.get('track_id')
    emotion = request.data.get('emotion')
    duration = request.data.get('duration', 0)
    track_name = request.data.get('track_name', '')
    artist_name = request.data.get('artist_name', '')
    item_type = str(request.data.get('item_type', 'track') or 'track').strip().lower()
    history_id = request.data.get('history_id')
    ended_reason = str(request.data.get('ended_reason', '') or '').strip().lower()

    try:
        track_length_seconds = max(int(request.data.get('duration_ms') or 0), 0) / 1000.0
    except (TypeError, ValueError):
        track_length_seconds = 0.0
    try:
        duration = max(int(duration or 0), 0)
    except (TypeError, ValueError):
        duration = 0
    if history_id not in (None, ''):
        try:
            history_id = int(history_id)
        except (TypeError, ValueError):
            history_id = 0
        if history_id <= 0:
            return Response(
                {'error': 'history_id must be a positive whole number.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

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

    if (
        not track_id
        or not emotion
        or item_type != 'track'
        or str(artist_name).strip().lower() == 'open in spotify'
    ):
        return Response({'status': 'skipped'})

    listen_seconds = max(int(duration or 0), 0)
    played_through = (
        ended_reason == 'completed'
        or _listen_was_meaningful(listen_seconds, track_length_seconds)
    )

    if prompt_history is not None:
        # Listening history: every playback of a real track, however short.
        ListeningSession.objects.update_or_create(
            user=request.user,
            prompt_history=prompt_history,
            spotify_track_id=track_id,
            defaults={
                'track_name': track_name,
                'listen_duration': listen_seconds,
                'completed': played_through,
            },
        )

    return Response({'status': 'recorded', 'completed': played_through})
