"""
EmoTune Main API Views
Emotion analysis (BERT) -> the therapist-approved songs for that emotion, plus
crisis support, the feel-better flow, Spotify auth/in-app playback, and admin.
"""
import json
import logging
from django.conf import settings
from django.shortcuts import render
from django.utils import timezone
from django.db.models.functions import TruncMonth
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated, IsAdminUser
from rest_framework.response import Response
from rest_framework import status
from django.contrib.auth import get_user_model
from django.db.models import Count
from django.urls import reverse
from datetime import timedelta

from django.contrib.admin.views.decorators import staff_member_required
from rest_framework_simplejwt.tokens import AccessToken

from .spotify_service import spotify_service
from .spotify_oauth_state import (
    issue_state as issue_spotify_oauth_state,
    read_state as read_spotify_oauth_state,
)
from .session_plan import (
    build_session_plan,
    normalize_requested_outcome_mode,
    outcome_mode_config,
    outcome_mode_for_emotion,
    update_session_plan_progress,
)
from ml.emotion_classifier import EMOTIONS, get_classifier, get_ai_response
from ml.plutchik_mapper import build_plutchik_profile
from users.models import PromptHistory
from .models import SupportEvent, SupportResource, songs_for_emotion
from .safety import (
    CONCERN_CHECK_IN_MESSAGE,
    SOMEONE_ELSE_CHECK_IN_MESSAGE,
    SOMEONE_ELSE_CRISIS_MESSAGE,
    SUPPORT_SUBJECT_SOMEONE_ELSE,
    RISK_CONCERN,
    RISK_CRISIS,
    assess_concern,
    SEVERITY_CRISIS,
    assess_crisis_severity,
    build_crisis_support_message,
    support_subject,
)

User = get_user_model()
logger = logging.getLogger(__name__)

RECOVERY_TRIGGER_EMOTIONS = frozenset({'sad', 'stressed', 'depressing', 'angry'})
RECOVERY_SUPPORT_EMOTION_MAP = {
    'sad': 'calm',
    'stressed': 'calm',
    'depressing': 'calm',
    'angry': 'motivational',
}
RECOVERY_TRIGGER_CONFIDENCE = 0.90
RECOVERY_CHECK_INTERVAL_TRACKS = 5
# The refactor plan asks for a reasonable maximum on the analysed text.
MAX_ANALYZE_TEXT_LENGTH = 2000


def _fallback_analysis():
    other_weight = 0.65 / max(len(EMOTIONS) - 1, 1)
    all_scores = {emotion: other_weight for emotion in EMOTIONS}
    all_scores['mixed'] = 0.35
    return {
        'emotion': 'mixed',
        'confidence': all_scores['mixed'],
        'all_scores': all_scores,
        'top_emotions': [
            {'emotion': 'mixed', 'confidence': all_scores['mixed']},
            {'emotion': 'calm', 'confidence': all_scores.get('calm', 0.0)},
        ],
        'secondary_emotion': 'calm',
        'prediction_source': 'system',
        'prediction_strategy': 'system_fallback',
        'confidence_band': 'low',
        'confidence_margin': all_scores['mixed'] - all_scores.get('calm', 0.0),
        'fallback_used': True,
        'fallback_reason': 'classifier_error',
        'needs_review': True,
        'label_schema_version': 'v1',
    }


def _support_resources_payload():
    return [resource.to_payload() for resource in SupportResource.visible()]


def _record_support_event(level, trigger, source):
    """Count a safety-check hit. Never pass text or a user here (see SupportEvent)."""
    try:
        SupportEvent.objects.create(level=level, trigger=trigger, source=source)
    except Exception:
        # Counting is for reporting only; it must never block the support response.
        logger.exception("Could not record support event")


def _attach_concern_check_in(payload, trigger, subject):
    """Mark a normal (music-bearing) payload with the gentle check-in tier.

    `support_about` says who the worry is about ("self" or "someone_else"), so
    the app can word the card; the hotline list goes out either way.
    """
    payload['risk_level'] = RISK_CONCERN
    payload['support_about'] = subject
    payload['support_check_in'] = {
        'message': (
            SOMEONE_ELSE_CHECK_IN_MESSAGE
            if subject == SUPPORT_SUBJECT_SOMEONE_ELSE
            else CONCERN_CHECK_IN_MESSAGE
        ),
        'trigger': trigger,
        'about': subject,
        'resources': _support_resources_payload(),
    }
    return payload


def _build_crisis_response_payload(severity=SEVERITY_CRISIS, subject='self'):
    """Short-circuit payload for text matching `safety.assess_crisis_severity`.

    `crisis_severity` is "imminent" when the text names a plan, method or time
    ("tonight", pills, a bridge), so a client can put emergency contacts first.

    Shaped like `_build_emotion_response_payload`'s return value (same keys the
    Flutter client already reads off this endpoint) so a client that doesn't yet
    branch on `crisis` still gets a coherent "no tracks, here's a message" result
    instead of a differently-shaped response it has to guess about. `tracks: []`
    is deliberate -- this path must never hand back a playlist.
    """
    all_scores = {emotion: 0.0 for emotion in EMOTIONS}
    return {
        'crisis': True,
        'risk_level': RISK_CRISIS,
        'crisis_severity': severity,
        'support_about': subject,
        'support_resources': _support_resources_payload(),
        'emotion': 'mixed',
        'emotion_info': None,
        'confidence': 0.0,
        'all_scores': all_scores,
        'top_emotions': [],
        'secondary_emotion': None,
        'plutchik_scores': {},
        'plutchik_top_emotions': [],
        'plutchik_dominant_emotion': None,
        'plutchik_profile_version': 'v1',
        'outcome_mode': 'match_mood',
        'outcome_label': None,
        'outcome_description': None,
        'session_plan': None,
        'prediction_source': 'system',
        'prediction_strategy': 'crisis_short_circuit',
        'confidence_band': 'low',
        'confidence_margin': 0.0,
        'prediction_fallback_used': False,
        'prediction_fallback_reason': None,
        'needs_review': True,
        'ai_response': (
            SOMEONE_ELSE_CRISIS_MESSAGE
            if subject == SUPPORT_SUBJECT_SOMEONE_ELSE
            else build_crisis_support_message()
        ),
        'tracks': [],
        'total': 0,
        'tracks_source': 'crisis_short_circuit',
        'history_id': None,
        'recovery_plan': None,
    }


def _safe_probability(value):
    try:
        probability = float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0
    if probability > 1.0:
        probability = probability / 100.0
    return max(0.0, min(probability, 1.0))


def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _invalid_history_id(history_id):
    """True for a history_id that is present but not a positive whole number."""
    if history_id in (None, ''):
        return False
    return _safe_int(history_id, 0) <= 0


def _to_bool(value, default=False):
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    text = str(value).strip().lower()
    if text in {'true', '1', 'yes', 'y', 'fine', 'im fine now', "i'm fine now"}:
        return True
    if text in {'false', '0', 'no', 'n', 'not yet'}:
        return False
    return default


def _music_picker_data_for_history(history):
    data = history.music_picker_data if history else {}
    return dict(data) if isinstance(data, dict) else {}


def _request_outcome_mode(request):
    """The mode the caller asked for, unresolved.

    Returned raw because the fallback is no longer a constant: with no explicit
    mode the detected emotion picks one, and that emotion is not known until
    after classification.
    """
    return request.data.get('outcome_mode')


def _request_session_length_minutes(request):
    raw_value = request.data.get('session_length_minutes')
    if raw_value in (None, ''):
        return None
    value = _safe_int(raw_value, 0)
    return max(value, 0)


def _request_check_in_frequency_tracks(request):
    raw_value = request.data.get('check_in_frequency_tracks')
    if raw_value in (None, ''):
        return None
    value = _safe_int(raw_value, 0)
    return max(value, 0) or None


def _session_plan_for_history(history):
    session_plan = _music_picker_data_for_history(history).get('session_plan')
    return dict(session_plan) if isinstance(session_plan, dict) else None


def _build_recovery_plan(*, result=None, history=None, existing_plan=None):
    existing = dict(existing_plan) if isinstance(existing_plan, dict) else {}

    if existing.get('eligible'):
        original_emotion = str(existing.get('original_emotion') or '').strip().lower()
        support_emotion = str(existing.get('support_emotion') or '').strip().lower()
        trigger_confidence = _safe_probability(existing.get('trigger_confidence'))
    else:
        if history is not None:
            original_emotion = str(history.detected_emotion or '').strip().lower()
            trigger_confidence = _safe_probability(history.emotion_confidence)
        else:
            result = result or {}
            original_emotion = str(result.get('emotion') or '').strip().lower()
            trigger_confidence = _safe_probability(result.get('confidence'))
        support_emotion = RECOVERY_SUPPORT_EMOTION_MAP.get(original_emotion, '')

    if (
        original_emotion not in RECOVERY_TRIGGER_EMOTIONS
        or support_emotion not in EMOTIONS
        or trigger_confidence < RECOVERY_TRIGGER_CONFIDENCE
    ):
        return None

    existing_next_checkpoint = existing.get('next_checkpoint_tracks')
    next_checkpoint_tracks = (
        None
        if existing_next_checkpoint is None and bool(existing.get('transition_applied'))
        else max(
            _safe_int(existing_next_checkpoint, RECOVERY_CHECK_INTERVAL_TRACKS),
            1,
        )
    )

    return {
        'eligible': True,
        'original_emotion': original_emotion,
        'support_emotion': support_emotion,
        'trigger_confidence': trigger_confidence,
        'check_interval_tracks': max(
            _safe_int(existing.get('check_interval_tracks'), RECOVERY_CHECK_INTERVAL_TRACKS),
            1,
        ),
        'next_checkpoint_tracks': next_checkpoint_tracks,
        'last_prompt_tracks': max(_safe_int(existing.get('last_prompt_tracks'), 0), 0),
        'tracks_played': max(_safe_int(existing.get('tracks_played'), 0), 0),
        'prompts_shown': max(_safe_int(existing.get('prompts_shown'), 0), 0),
        'not_yet_count': max(_safe_int(existing.get('not_yet_count'), 0), 0),
        'phase': str(existing.get('phase') or 'support').strip().lower() or 'support',
        'transition_applied': bool(existing.get('transition_applied', False)),
    }


def _recovery_plan_for_history(history):
    existing_plan = _music_picker_data_for_history(history).get('recovery_plan')
    return _build_recovery_plan(history=history, existing_plan=existing_plan)


def _build_recovery_recommendation_profile(recovery_plan, *, transition=False):
    if not isinstance(recovery_plan, dict) or not recovery_plan.get('eligible'):
        return None

    original_emotion = str(recovery_plan.get('original_emotion') or '').strip().lower()
    support_emotion = str(recovery_plan.get('support_emotion') or '').strip().lower()
    if original_emotion not in EMOTIONS or support_emotion not in EMOTIONS:
        return None

    primary_emotion = support_emotion if transition else original_emotion
    secondary_emotion = original_emotion if transition else support_emotion
    all_scores = {emotion_name: 0.0 for emotion_name in EMOTIONS}
    all_scores[primary_emotion] = 0.5
    all_scores[secondary_emotion] = 0.5

    return {
        'emotion': primary_emotion,
        'confidence': 0.5,
        'all_scores': all_scores,
        'top_emotions': [
            {'emotion': primary_emotion, 'confidence': 0.5},
            {'emotion': secondary_emotion, 'confidence': 0.5},
        ],
        'secondary_emotion': secondary_emotion,
        'prediction_source': 'recovery_support',
        'prediction_strategy': (
            'feel_better_transition_blend'
            if transition
            else 'high_intensity_recovery_support_blend'
        ),
        'confidence_band': 'high',
        'confidence_margin': 0.0,
        'fallback_used': False,
        'fallback_reason': None,
        'needs_review': False,
        'label_schema_version': 'v1',
    }


def _spotify_redirect_uri(request):
    configured_redirect_uri = str(
        getattr(settings, 'SPOTIFY_REDIRECT_URI', '') or ''
    ).strip()
    if configured_redirect_uri:
        return configured_redirect_uri
    return request.build_absolute_uri(reverse('spotify_callback'))




def _ensure_hybrid_result(result):
    if not isinstance(result, dict):
        result = _fallback_analysis()

    existing_scores = result.get('plutchik_scores')
    if isinstance(existing_scores, dict) and existing_scores:
        return result

    hybrid_profile = build_plutchik_profile(result.get('all_scores'))
    return {
        **result,
        **hybrid_profile,
    }


def _build_emotion_response_payload(
    request,
    *,
    text,
    result,
    persist_history=True,
    history_id=None,
    recovery_plan=None,
    outcome_mode=None,
    session_length_minutes=None,
    check_in_frequency_tracks=None,
    session_plan=None,
):
    """The analysis response: the emotion plus ALL of its therapist-approved songs.

    No ranking, scoring or personalization picks songs any more (EmoTune
    Architecture Refactor Plan, 2026-10-10): the list is every active song mapped
    to the emotion, in the order the therapist's docs/music.md gives them. The
    emotion is the classifier's, or the support emotion once the feel-better flow
    has switched (which hands its own `result` in).
    """
    if not isinstance(result, dict):
        logger.warning("Emotion classifier returned invalid payload: %r", result)
        result = _fallback_analysis()
    result = _ensure_hybrid_result(result)

    emotion = result.get('emotion', 'mixed')
    confidence = result.get('confidence', 1.0)
    all_scores = result.get('all_scores', _fallback_analysis()['all_scores'])
    top_emotions = result.get('top_emotions', [])
    plutchik_scores = result.get('plutchik_scores') or {}
    plutchik_top_emotions = result.get('plutchik_top_emotions') or []

    # The mode now only shapes the listening session (check-in wording and
    # cadence); it no longer moves which emotion's songs are served.
    requested_outcome_mode = normalize_requested_outcome_mode(outcome_mode)
    normalized_outcome_mode = requested_outcome_mode or outcome_mode_for_emotion(emotion)
    mode_config = outcome_mode_config(normalized_outcome_mode)
    has_custom_session_request = (
        session_length_minutes is not None
        or (requested_outcome_mode or 'match_mood') != 'match_mood'
    )
    if not isinstance(session_plan, dict):
        session_plan = (
            build_session_plan(
                outcome_mode=normalized_outcome_mode,
                session_length_minutes=session_length_minutes,
                check_in_frequency_tracks=check_in_frequency_tracks,
            )
            if has_custom_session_request
            else None
        )
    recovery_plan = _build_recovery_plan(result=result, existing_plan=recovery_plan)

    emotion_record, tracks = songs_for_emotion(emotion)
    ai_response = get_ai_response(emotion)

    user = request.user if request.user.is_authenticated else None
    if user and persist_history:
        music_picker_data = {
            'outcome_mode': normalized_outcome_mode,
            'recovery_plan': recovery_plan,
            'session_plan': (
                update_session_plan_progress(session_plan, duration_seconds=0, tracks_played=0)
                if isinstance(session_plan, dict)
                else None
            ),
            'song_source': 'therapist_list',
        }
        try:
            history = (
                PromptHistory.objects.filter(id=history_id, user=user).first()
                if history_id
                else None
            )
            if history:
                history.prompt_text = text
                history.detected_emotion = emotion
                history.emotion_confidence = confidence
                history.emotion_scores = all_scores
                history.ai_response = ai_response
                history.playlist_data = tracks
                history.music_picker_data = music_picker_data
                history.save(update_fields=[
                    'prompt_text', 'detected_emotion', 'emotion_confidence',
                    'emotion_scores', 'ai_response', 'playlist_data', 'music_picker_data',
                ])
            else:
                history = PromptHistory.objects.create(
                    user=user,
                    prompt_text=text,
                    detected_emotion=emotion,
                    emotion_confidence=confidence,
                    emotion_scores=all_scores,
                    ai_response=ai_response,
                    playlist_data=tracks,
                    music_picker_data=music_picker_data,
                )
            history_id = history.id
        except Exception:
            logger.exception("Failed to save prompt history for user %s", user.id)
            history_id = None
    elif not user:
        history_id = None

    payload = {
        'emotion': emotion,
        'emotion_info': (
            {
                'id': emotion_record.id,
                'name': emotion_record.name,
                'display_name': emotion_record.display_name,
            }
            if emotion_record
            else None
        ),
        'confidence': round(confidence * 100, 1),
        'all_scores': {k: round(v * 100, 1) for k, v in all_scores.items()},
        'top_emotions': [
            {
                'emotion': item.get('emotion'),
                'confidence': round(float(item.get('confidence', 0.0)) * 100, 1),
            }
            for item in top_emotions
        ],
        'secondary_emotion': result.get('secondary_emotion'),
        'plutchik_scores': {
            name: round(float(score) * 100, 1) for name, score in plutchik_scores.items()
        },
        'plutchik_top_emotions': [
            {
                'emotion': item.get('emotion'),
                'confidence': round(float(item.get('confidence', 0.0)) * 100, 1),
            }
            for item in plutchik_top_emotions
        ],
        'plutchik_dominant_emotion': result.get('plutchik_dominant_emotion'),
        'plutchik_profile_version': result.get('plutchik_profile_version', 'v1'),
        'outcome_mode': normalized_outcome_mode,
        'outcome_label': mode_config['label'],
        'outcome_description': mode_config['description'],
        'session_plan': session_plan,
        'prediction_source': result.get('prediction_source', 'system'),
        'prediction_strategy': result.get('prediction_strategy', 'system_fallback'),
        'confidence_band': result.get('confidence_band', 'low'),
        'confidence_margin': round(float(result.get('confidence_margin', 0.0)) * 100, 1),
        'prediction_fallback_used': bool(result.get('fallback_used', False)),
        'prediction_fallback_reason': result.get('fallback_reason'),
        'needs_review': bool(result.get('needs_review', True)),
        'ai_response': ai_response,
        'tracks': tracks,
        'total': len(tracks),
        'tracks_source': 'therapist_list',
        'history_id': history_id,
        'recovery_plan': recovery_plan,
    }
    if emotion_record is None:
        payload['message'] = 'No supported emotion was identified.'
    elif not tracks:
        payload['message'] = 'No songs are mapped to this emotion yet.'
    return payload


def _build_explicit_emotion_result(emotion):
    normalized_emotion = str(emotion or '').strip().lower()
    if normalized_emotion not in EMOTIONS:
        normalized_emotion = 'mixed'

    all_scores = {emotion_name: 0.0 for emotion_name in EMOTIONS}
    all_scores[normalized_emotion] = 1.0
    return {
        'emotion': normalized_emotion,
        'confidence': 1.0,
        'all_scores': all_scores,
        'top_emotions': [
            {'emotion': normalized_emotion, 'confidence': 1.0},
        ],
        'secondary_emotion': None,
        'prediction_source': 'direct_emotion_selection',
        'prediction_strategy': 'explicit_emotion_tab',
        'confidence_band': 'high',
        'confidence_margin': 1.0,
        'fallback_used': False,
        'fallback_reason': None,
        'needs_review': False,
        'label_schema_version': 'v1',
    }


@api_view(['POST'])
def analyze_emotion(request):
    """
    Main endpoint: Analyze user's emotion from text prompt
    and return AI response + playlist recommendations
    """
    text = str(request.data.get('text', '')).strip()
    if not text:
        return Response({'error': 'Text is required'}, status=status.HTTP_400_BAD_REQUEST)
    if len(text) > MAX_ANALYZE_TEXT_LENGTH:
        return Response(
            {'error': f'Please keep it under {MAX_ANALYZE_TEXT_LENGTH} characters.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    severity = assess_crisis_severity(text)
    if severity:
        logger.warning(
            "Crisis-risk language (%s) detected in analyze_emotion (user=%s)",
            severity,
            request.user.id if request.user.is_authenticated else None,
        )
        _record_support_event(RISK_CRISIS, 'phrase', 'analyze_emotion')
        return Response(_build_crisis_response_payload(severity, support_subject(text)))

    outcome_mode = _request_outcome_mode(request)
    session_length_minutes = _request_session_length_minutes(request)
    check_in_frequency_tracks = _request_check_in_frequency_tracks(request)

    # Run BERT emotion classification
    try:
        classifier = get_classifier()
        result = classifier.predict(text)
    except Exception:
        logger.exception("Emotion analysis failed for text input")
        result = _fallback_analysis()

    payload = _build_emotion_response_payload(
        request,
        text=text,
        result=result,
        persist_history=True,
        outcome_mode=outcome_mode,
        session_length_minutes=session_length_minutes,
        check_in_frequency_tracks=check_in_frequency_tracks,
    )
    concern_trigger = assess_concern(text, result)
    if concern_trigger:
        _record_support_event(RISK_CONCERN, concern_trigger, 'analyze_emotion')
        _attach_concern_check_in(payload, concern_trigger, support_subject(text))
    return Response(payload)


@api_view(['POST'])
def recommend_by_emotion(request):
    """Return recommendations for an explicitly selected emotion tab."""
    emotion = str(request.data.get('emotion', '')).strip().lower()
    if emotion not in EMOTIONS:
        return Response(
            {
                'error': (
                    'Emotion must be one of: '
                    + ', '.join(EMOTIONS)
                )
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    raw_text = str(request.data.get('text', '')).strip()
    severity = assess_crisis_severity(raw_text) if raw_text else None
    if severity:
        logger.warning(
            "Crisis-risk language (%s) detected in recommend_by_emotion (user=%s)",
            severity,
            request.user.id if request.user.is_authenticated else None,
        )
        _record_support_event(RISK_CRISIS, 'phrase', 'recommend_by_emotion')
        return Response(_build_crisis_response_payload(severity, support_subject(raw_text)))

    text = raw_text or f'Play songs for a {emotion} mood.'
    outcome_mode = _request_outcome_mode(request)
    session_length_minutes = _request_session_length_minutes(request)
    check_in_frequency_tracks = _request_check_in_frequency_tracks(request)
    # Browsing a tab is not a session worth a history row unless the user asked
    # for one (a session length or an explicit mode).
    persist_history = bool(request.user.is_authenticated) and (
        (session_length_minutes or 0) > 0
        or (normalize_requested_outcome_mode(outcome_mode) or 'match_mood') != 'match_mood'
    )
    result = _build_explicit_emotion_result(emotion)
    payload = _build_emotion_response_payload(
        request,
        text=text,
        result=result,
        persist_history=persist_history,
        outcome_mode=outcome_mode,
        session_length_minutes=session_length_minutes,
        check_in_frequency_tracks=check_in_frequency_tracks,
    )
    # Phrase check on caller-supplied text only. The result here is the tab the
    # user picked, not a prediction, so choosing "depressing" must not count as
    # a model-confident concern.
    concern_trigger = assess_concern(raw_text)
    if concern_trigger:
        _record_support_event(RISK_CONCERN, concern_trigger, 'recommend_by_emotion')
        _attach_concern_check_in(payload, concern_trigger, support_subject(raw_text))
    return Response(payload)


@api_view(['POST'])
def check_feel_better(request):
    """Check whether a high-intensity session should show a recovery prompt."""
    history_id = request.data.get('history_id')
    listen_duration = max(_safe_int(request.data.get('duration'), 0), 0)
    tracks_played = max(_safe_int(request.data.get('tracks_played'), 0), 0)
    if _invalid_history_id(history_id):
        return Response(
            {'error': 'history_id must be a positive whole number.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    response_payload = {
        'should_prompt': False,
        'message': None,
        'history_id': history_id,
        'tracks_played': tracks_played,
        'next_checkpoint_tracks': None,
        'check_interval_tracks': RECOVERY_CHECK_INTERVAL_TRACKS,
        'recovery_plan': None,
        'session_plan': None,
    }

    if history_id and request.user.is_authenticated:
        try:
            history = PromptHistory.objects.get(id=history_id, user=request.user)
        except PromptHistory.DoesNotExist:
            history = None

        if history is not None:
            history.session_duration = max(_safe_int(listen_duration), 0)
            session_plan = update_session_plan_progress(
                _session_plan_for_history(history),
                duration_seconds=history.session_duration,
                tracks_played=tracks_played,
            )
            recovery_plan = _recovery_plan_for_history(history)
            music_picker_data = _music_picker_data_for_history(history)
            if session_plan:
                music_picker_data['session_plan'] = session_plan
                response_payload['session_plan'] = session_plan
                response_payload['next_checkpoint_tracks'] = session_plan.get('next_check_in_tracks')
                response_payload['check_interval_tracks'] = max(
                    _safe_int(session_plan.get('check_in_after_tracks'), RECOVERY_CHECK_INTERVAL_TRACKS),
                    1,
                )
            if recovery_plan:
                recovery_plan['tracks_played'] = max(
                    tracks_played,
                    _safe_int(recovery_plan.get('tracks_played'), 0),
                )
                music_picker_data['recovery_plan'] = recovery_plan

                checkpoint = max(
                    _safe_int(
                        recovery_plan.get('next_checkpoint_tracks'),
                        RECOVERY_CHECK_INTERVAL_TRACKS,
                    ),
                    1,
                )
                response_payload.update({
                    'history_id': history.id,
                    'tracks_played': recovery_plan['tracks_played'],
                    'next_checkpoint_tracks': checkpoint,
                    'check_interval_tracks': max(
                        _safe_int(
                            recovery_plan.get('check_interval_tracks'),
                            RECOVERY_CHECK_INTERVAL_TRACKS,
                        ),
                        1,
                    ),
                    'recovery_plan': recovery_plan,
                })
                if session_plan:
                    # The session's cadence is what the student chose; report its
                    # interval, and whichever checkpoint comes first so the app
                    # calls back in time for both prompts.
                    response_payload['check_interval_tracks'] = max(
                        _safe_int(session_plan.get('check_in_after_tracks'), RECOVERY_CHECK_INTERVAL_TRACKS),
                        1,
                    )
                    session_next = _safe_int(session_plan.get('next_check_in_tracks'), 0)
                    if session_next > 0:
                        response_payload['next_checkpoint_tracks'] = min(checkpoint, session_next)

                if (
                    recovery_plan.get('phase') == 'support'
                    and not recovery_plan.get('transition_applied')
                    and recovery_plan['tracks_played'] >= checkpoint
                ):
                    response_payload.update({
                        'should_prompt': True,
                        'message': (
                            f"You've listened to {recovery_plan['tracks_played']} songs. "
                            "Are you feeling better right now?"
                        ),
                    })

            if (
                not response_payload['should_prompt']
                and session_plan
                and not session_plan.get('completed')
                and tracks_played >= max(
                    _safe_int(session_plan.get('next_check_in_tracks'), 0),
                    1,
                )
            ):
                response_payload.update({
                    'should_prompt': True,
                    'message': (
                        str(session_plan.get('check_in_prompt') or '').strip()
                        or 'How is this session feeling so far?'
                    ),
                    'next_checkpoint_tracks': session_plan.get('next_check_in_tracks'),
                })

            history.music_picker_data = music_picker_data
            history.save(update_fields=['session_duration', 'music_picker_data'])

    return Response({
        **response_payload,
    })


@api_view(['POST'])
def feel_better_response(request):
    """Handle the recovery prompt response and optionally transition the playlist."""
    history_id = request.data.get('history_id')
    response_val = _to_bool(request.data.get('felt_better', True), default=True)
    listen_duration = max(_safe_int(request.data.get('duration'), 0), 0)
    tracks_played = max(_safe_int(request.data.get('tracks_played'), 0), 0)
    if _invalid_history_id(history_id):
        return Response(
            {'error': 'history_id must be a positive whole number.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not (history_id and request.user.is_authenticated):
        return Response({'status': 'ok', 'action': 'noop'})

    try:
        history = PromptHistory.objects.get(id=history_id, user=request.user)
    except PromptHistory.DoesNotExist:
        return Response(
            {'status': 'error', 'message': 'Listening session not found.'},
            status=status.HTTP_404_NOT_FOUND,
        )

    recovery_plan = _recovery_plan_for_history(history)
    music_picker_data = _music_picker_data_for_history(history)
    session_plan = update_session_plan_progress(
        _session_plan_for_history(history),
        duration_seconds=listen_duration,
        tracks_played=tracks_played,
    )

    if not recovery_plan and not session_plan:
        history.felt_better_response = response_val
        history.session_duration = listen_duration
        history.save(update_fields=['felt_better_response', 'session_duration'])
        return Response({'status': 'ok', 'action': 'noop'})

    if session_plan:
        session_plan['last_response'] = 'felt_better' if response_val else 'not_yet'
        interval = max(
            _safe_int(
                session_plan.get('check_in_after_tracks'),
                RECOVERY_CHECK_INTERVAL_TRACKS,
            ),
            1,
        )
        if response_val:
            session_plan['completed'] = True
            session_plan['next_check_in_tracks'] = None
        else:
            session_plan['completed'] = False
            session_plan['next_check_in_tracks'] = tracks_played + interval
        music_picker_data['session_plan'] = session_plan

        if not recovery_plan:
            history.felt_better_response = response_val
            history.session_duration = listen_duration
            history.music_picker_data = music_picker_data
            history.save(update_fields=[
                'felt_better_response',
                'session_duration',
                'music_picker_data',
            ])
            return Response({
                'status': 'ok',
                'action': 'session_complete' if response_val else 'continue_playlist',
                'message': (
                    str(session_plan.get('completion_message') or '').strip()
                    if response_val
                    else (
                        f"Okay, I will check in again after {interval} more songs."
                    )
                ),
                'history_id': history.id,
                'next_checkpoint_tracks': session_plan.get('next_check_in_tracks'),
                'check_interval_tracks': interval,
                'session_plan': session_plan,
            })

    recovery_plan['tracks_played'] = max(
        tracks_played,
        _safe_int(recovery_plan.get('tracks_played'), 0),
    )
    recovery_plan['last_prompt_tracks'] = recovery_plan['tracks_played']
    recovery_plan['prompts_shown'] = _safe_int(recovery_plan.get('prompts_shown'), 0) + 1

    if not response_val:
        interval = max(
            _safe_int(
                recovery_plan.get('check_interval_tracks'),
                RECOVERY_CHECK_INTERVAL_TRACKS,
            ),
            1,
        )
        recovery_plan['not_yet_count'] = (
            _safe_int(recovery_plan.get('not_yet_count'), 0) + 1
        )
        recovery_plan['next_checkpoint_tracks'] = (
            recovery_plan['tracks_played'] + interval
        )
        recovery_plan['phase'] = 'support'
        recovery_plan['transition_applied'] = False

        music_picker_data['recovery_plan'] = recovery_plan
        history.felt_better_response = False
        history.session_duration = listen_duration
        history.music_picker_data = music_picker_data
        history.save(update_fields=[
            'felt_better_response',
            'session_duration',
            'music_picker_data',
        ])
        return Response({
            'status': 'ok',
            'action': 'continue_playlist',
            'message': 'Okay, I will check in again after 5 more songs.',
            'history_id': history.id,
            'next_checkpoint_tracks': recovery_plan['next_checkpoint_tracks'],
            'check_interval_tracks': interval,
            'recovery_plan': recovery_plan,
            'session_plan': session_plan,
        })

    recovery_plan['phase'] = 'transition'
    recovery_plan['transition_applied'] = True
    recovery_plan['next_checkpoint_tracks'] = None

    transition_result = _build_recovery_recommendation_profile(
        recovery_plan,
        transition=True,
    )
    payload = _build_emotion_response_payload(
        request,
        text=history.prompt_text,
        result=transition_result,
        persist_history=False,
        history_id=history.id,
        recovery_plan=recovery_plan,
        outcome_mode=music_picker_data.get('outcome_mode'),
        session_plan=session_plan,
    )

    music_picker_data.update({
        'recovery_plan': recovery_plan,
        'session_plan': session_plan,
        'recovery_transition': {
            'applied_at': timezone.now().isoformat(),
            'emotion': payload.get('emotion'),
            'tracks': payload.get('tracks') or [],
        },
    })
    history.felt_better_response = True
    history.session_duration = listen_duration
    history.ai_response = payload.get('ai_response') or history.ai_response
    history.playlist_data = payload.get('tracks') or history.playlist_data
    history.music_picker_data = music_picker_data
    history.save(update_fields=[
        'felt_better_response',
        'session_duration',
        'ai_response',
        'playlist_data',
        'music_picker_data',
    ])

    return Response({
        'status': 'ok',
        'action': 'transition_playlist',
        **payload,
    })


# Spotify Auth
@api_view(['GET'])
@permission_classes([AllowAny])
def spotify_app_remote_config(request):
    """Expose public Spotify App Remote config to the mobile client."""
    return Response({
        'client_id': settings.SPOTIFY_CLIENT_ID,
        'redirect_uri': settings.SPOTIFY_APP_REMOTE_REDIRECT_URI,
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def spotify_auth_url(request):
    """Get Spotify OAuth URL for the signed-in user.

    The account to link is taken from the access token, never from a request
    parameter: a caller who could name the target user could hand somebody
    else's account a Spotify login link.
    """
    redirect_uri = _spotify_redirect_uri(request)
    logger.info(
        "Generating Spotify auth URL for user=%s redirect_uri=%s",
        request.user.id,
        redirect_uri,
    )
    url = spotify_service.get_auth_url(
        state=issue_spotify_oauth_state(request.user),
        redirect_uri=redirect_uri,
    )
    return Response({'auth_url': url})


def _wants_html(request):
    """True when the caller is a browser rather than an API client."""
    return 'text/html' in request.headers.get('Accept', '')


def _spotify_connect_result_page(request, *, success, message, status_code):
    """Render the browser-facing end of the OAuth flow.

    Spotify sends the browser here after login, so without this the user is
    left staring at the API's JSON page and has to find EmoTune again by hand.
    The page deep links straight back into the app.
    """
    return_uri = settings.SPOTIFY_APP_RETURN_URI
    response = render(
        request,
        'spotify_connect_result.html',
        {
            'success': success,
            'message': message,
            'return_uri': return_uri,
            'return_uri_json': json.dumps(return_uri),
        },
        status=status_code,
    )
    return response


@api_view(['GET'])
@permission_classes([AllowAny])
def spotify_callback(request):
    """Handle Spotify OAuth callback"""
    code = request.query_params.get('code')
    state = request.query_params.get('state')  # signed, issued by /spotify/auth-url/
    redirect_uri = _spotify_redirect_uri(request)
    
    if not code:
        if _wants_html(request):
            return _spotify_connect_result_page(
                request,
                success=False,
                message='Spotify did not return a login code. Start the connection again from EmoTune.',
                status_code=400,
            )
        return Response({'error': 'No code provided'}, status=400)

    # The signed state is what says which account this login belongs to. An
    # unreadable one means the callback was not started by EmoTune, so nothing
    # gets linked.
    state_user_id = read_spotify_oauth_state(state)
    if state_user_id is None:
        logger.warning(
            "Spotify callback rejected because the state was missing or invalid "
            "redirect_uri=%s",
            redirect_uri,
        )
        if _wants_html(request):
            return _spotify_connect_result_page(
                request,
                success=False,
                message=(
                    'This Spotify login link is no longer valid. Start the connection '
                    'again from EmoTune.'
                ),
                status_code=400,
            )
        return Response(
            {
                'error': 'Invalid or expired Spotify login state.',
                'message': (
                    'This Spotify login link is no longer valid. Start the connection '
                    'again from EmoTune.'
                ),
            },
            status=400,
        )

    token_data = spotify_service.exchange_code(code, redirect_uri=redirect_uri)
    
    if 'access_token' not in token_data:
        logger.warning(
            "Spotify callback token exchange failed for state=%s redirect_uri=%s reason=%s error=%s",
            state,
            redirect_uri,
            token_data.get('reason'),
            token_data.get('error'),
        )
        if _wants_html(request):
            return _spotify_connect_result_page(
                request,
                success=False,
                message=(
                    token_data.get('recommended_action')
                    or 'Spotify could not finish the login handshake.'
                ),
                status_code=400,
            )
        return Response(
            {
                'error': 'Spotify token exchange failed.',
                'message': (
                    token_data.get('recommended_action')
                    or 'Spotify could not finish the login handshake.'
                ),
                'spotify_token_error': spotify_service.api_error_payload(
                    token_data,
                    default_message='Spotify token exchange failed.',
                )['spotify'],
            },
            status=400,
        )
    
    access_token = token_data['access_token']
    refresh_token = token_data.get('refresh_token')
    expires_in = token_data.get('expires_in', 3600)
    granted_scopes = (
        spotify_service._normalize_scopes(token_data.get('scope'))
        or spotify_service._requested_scopes()
    )
    
    # Get Spotify user info
    profile_result = spotify_service.get_user_profile_result(access_token)
    spotify_profile = profile_result.get('data') if profile_result.get('ok') else None
    if not profile_result.get('ok'):
        logger.warning(
            "Spotify profile lookup during callback failed state=%s status=%s reason=%s error=%s",
            state,
            profile_result.get('status_code'),
            profile_result.get('reason'),
            profile_result.get('error'),
        )

    if profile_result.get('reason') == 'developer_allowlist_required':
        logger.warning(
            "Spotify callback blocked by developer allowlist for state=%s redirect_uri=%s",
            state,
            redirect_uri,
        )
        if _wants_html(request):
            return _spotify_connect_result_page(
                request,
                success=False,
                message=(
                    'Spotify rejected this login because the account is not registered '
                    'for EmoTune in the Spotify Developer Dashboard. Add it under Users '
                    'and Access, then try again.'
                ),
                status_code=403,
            )
        return Response(
            {
                'error': 'Spotify blocked this account for the EmoTune application.',
                'message': (
                    'Spotify rejected this login because the selected Spotify account is not '
                    'registered for the EmoTune app in the Spotify Developer Dashboard.'
                ),
                'spotify_profile_error': spotify_service.api_error_payload(
                    profile_result,
                    default_message='Spotify profile validation failed.',
                )['spotify'],
            },
            status=403,
        )
    
    try:
        user = User.objects.get(id=state_user_id)
    except User.DoesNotExist:
        # The state was signed by us, so this is an account deleted mid-login.
        logger.warning(
            "Spotify callback could not link because user=%s no longer exists",
            state_user_id,
        )
        if _wants_html(request):
            return _spotify_connect_result_page(
                request,
                success=False,
                message='That EmoTune account no longer exists. Sign in again and retry.',
                status_code=400,
            )
        return Response(
            {
                'error': 'Account not found for this Spotify login.',
                'message': 'That EmoTune account no longer exists. Sign in again and retry.',
            },
            status=400,
        )

    previous_spotify_id = str(user.spotify_id or '').strip() or None
    user.spotify_access_token = access_token
    user.spotify_refresh_token = refresh_token
    if granted_scopes:
        user.spotify_granted_scopes = granted_scopes
    user.spotify_token_expires = timezone.now() + timedelta(seconds=expires_in)
    user.is_spotify_connected = True
    if spotify_profile:
        user.spotify_id = spotify_profile.get('id')
    if (
        previous_spotify_id
        and spotify_profile
        and previous_spotify_id != spotify_profile.get('id')
    ):
        logger.warning(
            "Spotify account changed for user=%s old_spotify_id=%s new_spotify_id=%s",
            user.id,
            previous_spotify_id,
            spotify_profile.get('id'),
        )
    user.save()
    logger.info(
        "Spotify OAuth completed for user=%s spotify_id=%s spotify_email=%s expires_in=%s scopes=%s",
        user.id,
        user.spotify_id,
        spotify_profile.get('email') if spotify_profile else None,
        expires_in,
        granted_scopes,
    )
    
    response_payload = {
        'access_token': access_token,
        'spotify_profile': spotify_profile,
        'message': 'Spotify connected successfully!'
    }
    if not profile_result.get('ok'):
        response_payload['warning'] = (
            'Spotify authorized EmoTune, but Spotify profile validation failed right after '
            'login. Check the connected Spotify account and Spotify Developer Dashboard '
            'settings.'
        )
        response_payload['spotify_profile_error'] = spotify_service.api_error_payload(
            profile_result,
            default_message='Spotify profile validation failed.',
        )['spotify']
    if _wants_html(request):
        return _spotify_connect_result_page(
            request,
            success=True,
            message=(
                response_payload.get('warning')
                or 'Your Spotify account is linked. You can head back to EmoTune.'
            ),
            status_code=200,
        )
    return Response(response_payload)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def spotify_debug_status(request):
    """Return Spotify auth and playback diagnostics for the authenticated user."""
    diagnostics = spotify_service.get_playback_debug_status(request.user)
    logger.info(
        "Spotify debug status for user=%s connected=%s premium=%s devices=%s active=%s",
        request.user.id,
        diagnostics['spotify_connected'],
        diagnostics['account']['has_premium'],
        diagnostics['devices']['device_count'],
        diagnostics['devices']['has_active_device'],
    )
    return Response(diagnostics)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def spotify_prepare_playback(request):
    """Prepare Spotify playback by validating scopes and activating a device."""
    device_id = request.data.get('device_id')
    preparation = spotify_service.prepare_playback(request.user, device_id=device_id)
    logger.info(
        "Spotify prepare playback for user=%s ok=%s transfer_attempted=%s transfer_succeeded=%s blocking=%s",
        request.user.id,
        preparation['ok'],
        preparation['transfer_attempted'],
        preparation['transfer_succeeded'],
        preparation['blocking_issue'],
    )
    return Response(preparation)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def spotify_player_control(request):
    """Control Spotify playback through the Spotify Web API."""
    action = request.data.get('action')
    uri = request.data.get('uri')
    device_id = request.data.get('device_id')
    position_ms = request.data.get('position_ms')
    shuffle_enabled = request.data.get('shuffle_enabled')
    repeat_mode = request.data.get('repeat_mode')
    control_result = spotify_service.execute_playback_command(
        request.user,
        action=action,
        uri=uri,
        device_id=device_id,
        position_ms=position_ms,
        shuffle_enabled=shuffle_enabled,
        repeat_mode=repeat_mode,
    )
    logger.info(
        "Spotify player control user=%s action=%s ok=%s blocking=%s device=%s",
        request.user.id,
        action,
        control_result['ok'],
        control_result['blocking_issue'],
        control_result['selected_device_name'],
    )
    return Response(control_result)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def spotify_disconnect(request):
    """Disconnect the authenticated user's linked Spotify account."""
    user = request.user
    previous_spotify_id = str(user.spotify_id or '').strip() or None

    user.spotify_access_token = None
    user.spotify_refresh_token = None
    user.spotify_granted_scopes = []
    user.spotify_token_expires = None
    user.spotify_id = None
    user.is_spotify_connected = False
    user.save(update_fields=[
        'spotify_access_token',
        'spotify_refresh_token',
        'spotify_granted_scopes',
        'spotify_token_expires',
        'spotify_id',
        'is_spotify_connected',
        'updated_at',
    ])

    logger.info(
        "Spotify disconnected for user=%s previous_spotify_id=%s",
        user.id,
        previous_spotify_id,
    )
    return Response({
        'ok': True,
        'message': 'Spotify disconnected successfully.',
        'previous_spotify_id': previous_spotify_id,
    })


@api_view(['GET'])
@permission_classes([AllowAny])
def support_resources(request):
    """Verified hotlines and counselors for the app's support screen.

    Public on purpose: someone in crisis whose login has expired must still be
    able to reach this list.
    """
    return Response({
        'message': build_crisis_support_message(),
        'resources': _support_resources_payload(),
    })


# Admin Views
@api_view(['GET'])
@permission_classes([IsAdminUser])
def admin_dashboard(request):
    """Admin dashboard stats"""
    total_users = User.objects.filter(is_staff=False).count()
    
    # Monthly stats for last 6 months
    monthly_playlists = (
        PromptHistory.objects
        .annotate(month=TruncMonth('created_at'))
        .values('month')
        .annotate(count=Count('id'))
        .order_by('month')
    )
    
    # Mood distribution
    mood_distribution = (
        PromptHistory.objects
        .values('detected_emotion')
        .annotate(count=Count('id'))
        .order_by('-count')
    )
    
    # Counts only -- SupportEvent stores no text or user (see api/models.py).
    support_events = (
        SupportEvent.objects
        .filter(created_at__gte=timezone.now() - timedelta(days=30))
        .values('level', 'trigger')
        .annotate(count=Count('id'))
        .order_by('level', 'trigger')
    )

    return Response({
        'total_users': total_users,
        'monthly_playlists': list(monthly_playlists),
        'mood_distribution': list(mood_distribution),
        'support_events_last_30_days': list(support_events),
    })


@api_view(['GET'])
@permission_classes([IsAdminUser])
def admin_users(request):
    """Admin: list all users"""
    query = request.query_params.get('q', '')
    users = User.objects.filter(is_staff=False)
    if query:
        users = users.filter(username__icontains=query) | users.filter(email__icontains=query)
    
    data = [{
        'id': u.id,
        'username': u.username,
        'email': u.email,
        'is_spotify_connected': u.is_spotify_connected,
        'created_at': u.created_at,
        'prompt_count': u.prompt_history.count(),
    } for u in users]
    
    return Response(data)


@api_view(['DELETE'])
@permission_classes([IsAdminUser])
def admin_delete_user(request, user_id):
    """Admin: delete a user"""
    try:
        user = User.objects.get(id=user_id, is_staff=False)
        user.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
    except User.DoesNotExist:
        return Response({'error': 'User not found'}, status=404)


@staff_member_required
def admin_panel(request):
    """Serve the Admin Dashboard HTML interface to signed-in staff.

    The dashboard used to be public and ask for credentials in JavaScript, so
    anyone could load the page and — because the old script fell back to demo
    data whenever the API refused it — see something that looked like a working
    admin console. Django's session check now gates the page itself, and the
    short-lived token minted here lets the already-authenticated staff user
    call the admin API without a second login.
    """
    return render(
        request,
        "admin_dashboard.html",
        {'admin_access_token': str(AccessToken.for_user(request.user))},
    )

