"""
EmoTune Main API Views
Handles emotion analysis, recommendations, Spotify auth
"""
import json
import logging
from django.conf import settings
from django.core import signing
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

from .spotify.recommendations import (
    STATIC_TRACK_SOURCES,
    familiar_favorite_quota,
    music_doc_tracks,
)
from .spotify_service import spotify_service
from .spotify_oauth_state import (
    issue_state as issue_spotify_oauth_state,
    read_state as read_spotify_oauth_state,
)
from .llm_music_picker import LLMMusicPicker
from .music_picker import music_picker
from .recommendation_session import (
    apply_outcome_mode,
    build_session_plan,
    normalize_outcome_mode,
    normalize_requested_outcome_mode,
    outcome_mode_for_emotion,
    normalize_taste_profile,
    outcome_mode_config,
    should_persist_recommendation_context,
    update_session_plan_progress,
)
from ml.emotion_classifier import EMOTIONS, get_classifier, get_ai_response
from ml.plutchik_mapper import build_plutchik_profile
from users.models import PromptHistory, UserPreference, FavoriteTrack, ListeningSession
from users.serializers import PromptHistorySerializer
from .models import SupportEvent, SupportResource
from .safety import (
    CONCERN_CHECK_IN_MESSAGE,
    RISK_CONCERN,
    RISK_CRISIS,
    assess_concern,
    SEVERITY_CRISIS,
    assess_crisis_severity,
    build_crisis_support_message,
)

User = get_user_model()
logger = logging.getLogger(__name__)

RECOMMENDATION_CONTINUATION_SALT = 'emotune.recommendation.continuation'
RECOMMENDATION_CONTINUATION_VERSION = 1
RECOVERY_TRIGGER_EMOTIONS = frozenset({'sad', 'stressed', 'depressing', 'angry'})
RECOVERY_SUPPORT_EMOTION_MAP = {
    'sad': 'calm',
    'stressed': 'calm',
    'depressing': 'calm',
    'angry': 'motivational',
}
RECOVERY_TRIGGER_CONFIDENCE = 0.90
RECOVERY_CHECK_INTERVAL_TRACKS = 5
OUTCOME_SUPPORT_MESSAGES = {
    'calm_me_down': "Let's bring the energy down gently.",
}


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


def _attach_concern_check_in(payload, trigger):
    """Mark a normal (music-bearing) payload with the gentle check-in tier."""
    payload['risk_level'] = RISK_CONCERN
    payload['support_check_in'] = {
        'message': CONCERN_CHECK_IN_MESSAGE,
        'trigger': trigger,
        'resources': _support_resources_payload(),
    }
    return payload


def _build_crisis_response_payload(severity=SEVERITY_CRISIS):
    """Short-circuit payload for text matching `safety.assess_crisis_severity`.

    `crisis_severity` is "imminent" when the text names a plan, method or time
    ("tonight", pills, a bridge), so a client can put emergency contacts first.

    Shaped like `EmotionResponseBuilder.build()`'s return value (same keys the
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
        'support_resources': _support_resources_payload(),
        'emotion': 'mixed',
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
        'recommendation_target_emotion': 'mixed',
        'taste_profile': normalize_taste_profile(None),
        'session_plan': None,
        'prediction_source': 'system',
        'prediction_strategy': 'crisis_short_circuit',
        'confidence_band': 'low',
        'confidence_margin': 0.0,
        'prediction_fallback_used': False,
        'prediction_fallback_reason': None,
        'needs_review': True,
        'ai_response': build_crisis_support_message(),
        'tracks': [],
        'selected_track': None,
        'selected_track_source': None,
        'music_picker_strategy': None,
        'music_picker_reason': None,
        'music_picker_used_fallback': False,
        'music_picker_intent': None,
        'music_picker_artist_name': None,
        'music_picker_track_name': None,
        'music_picker_playlist_category': None,
        'music_picker_confirmation': None,
        'tracks_source': 'crisis_short_circuit',
        'tracks_fallback_used': False,
        'tracks_fallback_reason': None,
        'tracks_personalized': False,
        'tracks_personalization_sources': [],
        'tracks_personalization_missing_scopes': [],
        'progressive_stage': 'initial',
        'loading_more_tracks': False,
        'continuation_token': None,
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


def _history_allows_personalization_learning(history):
    music_picker_data = _music_picker_data_for_history(history)
    personalization = music_picker_data.get('personalization')
    if isinstance(personalization, dict) and personalization.get('train_session') is False:
        return False
    return True


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


def _request_taste_profile(request):
    raw_value = request.data.get('taste_profile')
    if not isinstance(raw_value, dict):
        raw_value = {}
    return normalize_taste_profile(raw_value)


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


def _progressive_initial_budget_seconds():
    return max(
        float(
            getattr(settings, 'SPOTIFY_PROGRESSIVE_INITIAL_BUDGET_SECONDS', 2.5) or 2.5
        ),
        0.5,
    )


def _progressive_initial_candidate_limit():
    return max(
        int(
            getattr(settings, 'SPOTIFY_PROGRESSIVE_INITIAL_CANDIDATE_LIMIT', 6) or 6
        ),
        1,
    )


def _progressive_initial_track_limit():
    return max(
        int(getattr(settings, 'SPOTIFY_PROGRESSIVE_INITIAL_TRACK_LIMIT', 1) or 1),
        1,
    )


def _progressive_continuation_budget_seconds():
    return max(
        float(
            getattr(
                settings,
                'SPOTIFY_PROGRESSIVE_CONTINUATION_BUDGET_SECONDS',
                8.0,
            )
            or 8.0
        ),
        1.0,
    )


def _progressive_continuation_candidate_limit():
    return max(
        int(
            getattr(
                settings,
                'SPOTIFY_PROGRESSIVE_CONTINUATION_CANDIDATE_LIMIT',
                20,
            )
            or 20
        ),
        2,
    )


def _recommendation_continuation_max_age_seconds():
    return max(
        int(
            getattr(
                settings,
                'RECOMMENDATION_CONTINUATION_MAX_AGE_SECONDS',
                900,
            )
            or 900
        ),
        60,
    )


EMPTY_LLM_SEARCH_PLAN = {
    'used': False,
    'search_queries': [],
    'playlist_category': None,
    'strategy': None,
    'reason': None,
    'provider': None,
    'model': None,
    'confidence': None,
    'error': None,
}


def _build_llm_search_plan(
    *,
    prompt_text,
    emotion,
    top_emotions=None,
    all_scores=None,
    confidence_band=None,
    confidence_margin=None,
    preferred_artists=None,
    skip=False,
):
    """Ask the LLM for Spotify search queries built from the prompt itself.

    The built-in query builder only ever sees the emotion label, so two very
    different prompts that both land on "sad" retrieve the same candidates.
    This reads the sentence the user actually wrote.

    It is strictly additive: the returned queries are appended to the built-in
    ones (`_build_recommendation_queries` already accepts `llm_queries`), and
    the linear ranker still decides the final order. Anything short of a usable
    plan -- disabled, unconfigured, timed out, malformed -- returns the empty
    plan, which leaves retrieval exactly as it is today. The picker's own
    heuristic fallback queries are deliberately discarded rather than merged:
    they are a thinner restatement of what the query builder already produces.
    """
    if skip or not str(prompt_text or '').strip():
        return dict(EMPTY_LLM_SEARCH_PLAN)

    picker = LLMMusicPicker()
    if not picker.is_configured():
        return dict(EMPTY_LLM_SEARCH_PLAN)

    try:
        plan = picker.build_search_plan(
            prompt_text=prompt_text,
            emotion=emotion,
            top_emotions=top_emotions,
            all_scores=all_scores,
            confidence_band=confidence_band,
            confidence_margin=confidence_margin,
            preferred_artists=preferred_artists,
        )
    except Exception:
        # Candidate retrieval must survive anything the LLM layer does; the
        # built-in queries alone are a complete result.
        logger.exception("LLM search plan failed for emotion %r", emotion)
        return dict(EMPTY_LLM_SEARCH_PLAN)

    if not isinstance(plan, dict) or not plan.get('ok'):
        failed = dict(EMPTY_LLM_SEARCH_PLAN)
        failed['error'] = (
            plan.get('error') if isinstance(plan, dict) else 'llm_search_plan_unavailable'
        )
        return failed

    queries = [
        ' '.join(str(query or '').split())
        for query in (plan.get('search_queries') or [])
    ]
    queries = [query for query in queries if query]
    if not queries:
        failed = dict(EMPTY_LLM_SEARCH_PLAN)
        failed['error'] = 'llm_search_plan_missing_queries'
        return failed

    return {
        'used': True,
        'search_queries': queries,
        'playlist_category': (
            str(plan.get('playlist_category') or '').strip() or None
        ),
        'strategy': plan.get('strategy') or 'llm_search_plan',
        'reason': plan.get('reason'),
        'provider': plan.get('provider'),
        'model': plan.get('model'),
        'confidence': plan.get('confidence'),
        'error': None,
    }


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


def _serialize_recommendation_result(result):
    result = _ensure_hybrid_result(result)

    return {
        'emotion': result.get('emotion', 'mixed'),
        'confidence': float(result.get('confidence', 0.0) or 0.0),
        'all_scores': result.get('all_scores') or _fallback_analysis()['all_scores'],
        'top_emotions': result.get('top_emotions') or [],
        'secondary_emotion': result.get('secondary_emotion'),
        'plutchik_scores': result.get('plutchik_scores') or {},
        'plutchik_top_emotions': result.get('plutchik_top_emotions') or [],
        'plutchik_dominant_emotion': result.get('plutchik_dominant_emotion'),
        'plutchik_profile_version': result.get('plutchik_profile_version', 'v1'),
        'prediction_source': result.get('prediction_source', 'system'),
        'prediction_strategy': result.get('prediction_strategy', 'system_fallback'),
        'confidence_band': result.get('confidence_band', 'low'),
        'confidence_margin': float(result.get('confidence_margin', 0.0) or 0.0),
        'fallback_used': bool(result.get('fallback_used', False)),
        'fallback_reason': result.get('fallback_reason'),
        'needs_review': bool(result.get('needs_review', True)),
        'label_schema_version': result.get('label_schema_version', 'v1'),
        'outcome_mode': normalize_outcome_mode(result.get('outcome_mode')),
        'outcome_label': result.get('outcome_label'),
        'outcome_description': result.get('outcome_description'),
    }


def _build_recommendation_continuation_token(
    request,
    *,
    text,
    result,
    persist_history,
    history_id,
    outcome_mode,
    session_plan,
    taste_profile,
):
    return signing.dumps(
        {
            'version': RECOMMENDATION_CONTINUATION_VERSION,
            'user_id': request.user.id if request.user.is_authenticated else None,
            'text': text,
            'result': _serialize_recommendation_result(result),
            'persist_history': bool(persist_history),
            'history_id': history_id,
            'outcome_mode': normalize_outcome_mode(outcome_mode),
            'session_plan': session_plan if isinstance(session_plan, dict) else None,
            'taste_profile': normalize_taste_profile(taste_profile),
        },
        salt=RECOMMENDATION_CONTINUATION_SALT,
        compress=True,
    )


def _load_recommendation_continuation_token(request, token):
    payload = signing.loads(
        token,
        salt=RECOMMENDATION_CONTINUATION_SALT,
        max_age=_recommendation_continuation_max_age_seconds(),
    )
    expected_user_id = payload.get('user_id')
    request_user_id = request.user.id if request.user.is_authenticated else None
    if expected_user_id != request_user_id:
        raise PermissionError('This playlist continuation token belongs to another user.')
    return payload


class EmotionResponseBuilder:
    """Builds the emotion-analysis response payload (recommendations, playlist,
    prompt history, continuation token) for a single classify/recommend request."""

    def __init__(
        self,
        request,
        *,
        text,
        result,
        persist_history=True,
        recommendation_stage='full',
        history_id=None,
        recommendation_profile=None,
        recovery_plan=None,
        outcome_mode=None,
        session_length_minutes=None,
        check_in_frequency_tracks=None,
        taste_profile=None,
        session_plan=None,
    ):
        self.request = request
        self.text = text
        self.result = result
        self.persist_history = persist_history
        self.recommendation_stage = recommendation_stage
        self.history_id = history_id
        self.recommendation_profile = recommendation_profile
        self.recovery_plan = recovery_plan
        self.outcome_mode = outcome_mode
        self.session_length_minutes = session_length_minutes
        self.check_in_frequency_tracks = check_in_frequency_tracks
        self.taste_profile = taste_profile
        self.session_plan = session_plan

    def build(self):
        if not isinstance(self.result, dict):
            logger.warning("Emotion classifier returned invalid payload: %r", self.result)
            self.result = _fallback_analysis()
        self.result = _ensure_hybrid_result(self.result)

        normalized_recommendation_stage = (
            str(self.recommendation_stage or 'full').strip().lower() or 'full'
        )
        requested_outcome_mode = normalize_requested_outcome_mode(self.outcome_mode)
        normalized_taste_profile = normalize_taste_profile(self.taste_profile)
        # A session plan is still something the user asks for. Routing picking
        # Calm Me Down for a sad prompt must not start scheduling check-ins for
        # everyone who was simply feeling low.
        has_custom_session_request = (
            self.session_length_minutes is not None
            or (requested_outcome_mode or 'match_mood') != 'match_mood'
        )
        is_initial_stage = normalized_recommendation_stage == 'initial'
        is_continuation_stage = normalized_recommendation_stage == 'continuation'
        emotion = self.result.get('emotion', 'mixed')
        # docs/arch: the classifier picks the mode. An explicit request still
        # wins, which is what keeps a stage-2 continuation on the mode stage 1
        # already committed to.
        normalized_outcome_mode = (
            requested_outcome_mode or outcome_mode_for_emotion(emotion)
        )
        confidence = self.result.get('confidence', 1.0)
        all_scores = self.result.get('all_scores', _fallback_analysis()['all_scores'])
        top_emotions = self.result.get('top_emotions', [])
        prediction_source = self.result.get('prediction_source', 'system')
        prediction_strategy = self.result.get('prediction_strategy', 'system_fallback')
        confidence_band = self.result.get('confidence_band', 'low')
        confidence_margin = self.result.get('confidence_margin', 0.0)
        fallback_used = bool(self.result.get('fallback_used', False))
        fallback_reason = self.result.get('fallback_reason')
        needs_review = bool(self.result.get('needs_review', True))
        secondary_emotion = self.result.get('secondary_emotion')
        plutchik_scores = self.result.get('plutchik_scores') or {}
        plutchik_top_emotions = self.result.get('plutchik_top_emotions') or []
        plutchik_dominant_emotion = self.result.get('plutchik_dominant_emotion')
        plutchik_profile_version = self.result.get('plutchik_profile_version', 'v1')
        # Where on the iso-principle arc this request sits. A session plan handed
        # in by a continuation or a feel-better transition carries the phase the
        # listen-time clock has already advanced to; a fresh request has none, and
        # "settle" is the honest answer for one -- the listener just told us how
        # they feel, so this is the match step, not the arrival.
        blend_phase = (
            str(self.session_plan.get('phase') or '').strip().lower()
            if isinstance(self.session_plan, dict)
            else ''
        ) or 'settle'
        outcome_profile = _ensure_hybrid_result(
            apply_outcome_mode(self.result, normalized_outcome_mode, phase=blend_phase)
        )
        outcome_label = outcome_profile.get('outcome_label')
        outcome_description = outcome_profile.get('outcome_description')
        recommendation_target_emotion = outcome_profile.get('emotion', emotion)
        if not isinstance(self.session_plan, dict):
            self.session_plan = (
                build_session_plan(
                    outcome_mode=normalized_outcome_mode,
                    session_length_minutes=self.session_length_minutes,
                    check_in_frequency_tracks=self.check_in_frequency_tracks,
                )
                if has_custom_session_request
                else None
            )
        self.recovery_plan = _build_recovery_plan(
            result=self.result,
            existing_plan=self.recovery_plan,
        )
        if self.recommendation_profile is None:
            if self.recovery_plan and not self.recovery_plan.get('transition_applied'):
                self.recommendation_profile = _build_recovery_recommendation_profile(
                    self.recovery_plan,
                    transition=False,
                )
            else:
                self.recommendation_profile = outcome_profile

        if not isinstance(self.recommendation_profile, dict):
            self.recommendation_profile = self.result
        else:
            self.recommendation_profile = _ensure_hybrid_result(self.recommendation_profile)

        recommendation_emotion = self.recommendation_profile.get('emotion', emotion)
        recommendation_all_scores = (
            self.recommendation_profile.get('all_scores')
            or all_scores
        )
        recommendation_top_emotions = (
            self.recommendation_profile.get('top_emotions')
            or top_emotions
        )
        recommendation_target_emotion = self.recommendation_profile.get(
            'emotion',
            recommendation_target_emotion,
        )

        # Get AI response message
        ai_response = get_ai_response(emotion)
        outcome_prefix = OUTCOME_SUPPORT_MESSAGES.get(normalized_outcome_mode)
        if outcome_prefix:
            ai_response = f"{outcome_prefix} {ai_response}"

        # Get adaptive recommendations (check user preferences first)
        tracks = []
        user = self.request.user if self.request.user.is_authenticated else None
    
        if user:
            # Check if user has strong preferences for this emotion
            top_prefs = UserPreference.objects.filter(
                user=user,
                emotion=recommendation_target_emotion,
                play_count__gte=3,  # Played 3+ times = strong preference
            ).exclude(
                artist_name__iexact='Open in Spotify',
            ).order_by('-play_count')[:5]

            if top_prefs.exists():
                # Include preferred tracks
                for pref in top_prefs:
                    tracks.append({
                        'id': pref.spotify_track_id,
                        'name': pref.track_name,
                        'artist': pref.artist_name,
                        'album': '',
                        'image': '',
                        'preview_url': None,
                        'duration_ms': 0,
                        'spotify_url': f'https://open.spotify.com/track/{pref.spotify_track_id}',
                        'uri': f'spotify:track:{pref.spotify_track_id}',
                        'is_preferred': True,
                        'recommendation_source': 'user_preference',
                        'selection_reasons': ['emotion_preference', 'user_preference'],
                        'personalization_score': float(pref.play_count or 0) + 2.0,
                    })

        # Get Spotify recommendations
        preferred_artists = getattr(user, 'preferred_artists', []) if user else []
        spotify_result = {
            'tracks': [],
            'source': 'fallback',
            'used_fallback': True,
            'fallback_reason': 'recommendation_lookup_failed',
        }
        spotify_lookup_limit = (
            _progressive_initial_candidate_limit()
            if is_initial_stage
            else _progressive_continuation_candidate_limit()
            if is_continuation_stage
            else 20
        )
        spotify_lookup_include_personalization = (
            not is_initial_stage and not is_continuation_stage
        )
        spotify_lookup_time_budget_seconds = (
            _progressive_initial_budget_seconds()
            if is_initial_stage
            else _progressive_continuation_budget_seconds()
            if is_continuation_stage
            else None
        )
        spotify_query_mode = 'continuation' if is_continuation_stage else 'default'

        # The initial stage exists to get one track playing as fast as
        # possible, so it keeps the built-in queries and skips the round trip.
        # Every later stage can spend it: the user is already listening.
        llm_search_plan = _build_llm_search_plan(
            prompt_text=self.text,
            emotion=recommendation_emotion,
            top_emotions=recommendation_top_emotions,
            all_scores=recommendation_all_scores,
            confidence_band=confidence_band,
            confidence_margin=confidence_margin,
            preferred_artists=preferred_artists,
            skip=is_initial_stage,
        )
        # Omitted entirely rather than passed empty, so a request with no usable
        # plan reaches Spotify as the exact call it made before the LLM existed.
        llm_lookup_kwargs = {}
        if llm_search_plan['used']:
            llm_lookup_kwargs['llm_queries'] = llm_search_plan['search_queries']
            if llm_search_plan['playlist_category']:
                llm_lookup_kwargs['playlist_category'] = (
                    llm_search_plan['playlist_category']
                )

        try:
            spotify_result = spotify_service.get_recommendations_with_details(
                recommendation_emotion,
                user=user,
                preferred_artists=preferred_artists,
                top_emotions=recommendation_top_emotions,
                all_scores=recommendation_all_scores,
                **llm_lookup_kwargs,
                limit=spotify_lookup_limit,
                include_personalization=spotify_lookup_include_personalization,
                time_budget_seconds=spotify_lookup_time_budget_seconds,
                query_mode=spotify_query_mode,
                taste_profile=normalized_taste_profile,
            )
        except Exception:
            logger.exception(
                "Spotify recommendation lookup failed for emotion %r and outcome %r",
                recommendation_emotion,
                normalized_outcome_mode,
            )
        spotify_tracks = spotify_result.get('tracks') or []
    
        # Merge: preferred tracks first, then Spotify tracks
        seen_ids = {t['id'] for t in tracks}
        for t in spotify_tracks:
            if t['id'] not in seen_ids:
                tracks.append(t)
                seen_ids.add(t['id'])

        ranking_limit = spotify_lookup_limit
        tracks = spotify_service.sanitize_recommendations(tracks, limit=ranking_limit)
        tracks = spotify_service.rank_tracks_for_emotion(
            tracks,
            emotion=recommendation_emotion,
            top_emotions=recommendation_top_emotions,
            preferred_artists=preferred_artists,
            confidence_band=confidence_band,
            limit=ranking_limit,
            taste_profile=normalized_taste_profile,
        )
        heuristic_selected_track = spotify_service.select_primary_track(tracks)
        if is_initial_stage:
            recommended_tracks = tracks[: _progressive_initial_track_limit()]
            selected_track = heuristic_selected_track
            if not isinstance(selected_track, dict) and recommended_tracks:
                selected_track = recommended_tracks[0]
            if isinstance(selected_track, dict):
                recommended_tracks = [selected_track]
            selected_track_source = (
                selected_track.get('recommendation_source')
                if isinstance(selected_track, dict)
                else None
            )
            music_picker_strategy = 'quick_primary_track'
            music_picker_reason = (
                'Returned the fastest high-confidence Spotify match first while the full '
                'playlist keeps loading in the background.'
            )
            music_picker_used_fallback = bool(spotify_result.get('used_fallback'))
            music_picker_intent = 'track'
            music_picker_artist_name = (
                str(selected_track.get('artist') or '').strip() or None
                if isinstance(selected_track, dict)
                else None
            )
            music_picker_track_name = (
                str(selected_track.get('name') or '').strip() or None
                if isinstance(selected_track, dict)
                else None
            )
            music_picker_playlist_category = recommendation_emotion
            music_picker_confirmation = (
                (
                    f"Starting with {music_picker_track_name} by {music_picker_artist_name} "
                    "while the rest of the playlist loads."
                )
                if music_picker_track_name and music_picker_artist_name
                else None
            )
            playlist_result = {
                'tracks': recommended_tracks,
                'selected_track': selected_track,
                'playlist_track_ids': [
                    str(track.get('id'))
                    for track in recommended_tracks
                    if isinstance(track, dict) and str(track.get('id') or '').strip()
                ],
                'strategy': music_picker_strategy,
                'reason': music_picker_reason,
                'used_fallback': music_picker_used_fallback,
                'provider': 'spotify_progressive',
                'model': 'quick_primary_track',
                'error': spotify_result.get('fallback_reason'),
                'confidence': None,
                'intent': music_picker_intent,
                'artist_name': music_picker_artist_name,
                'track_name': music_picker_track_name,
                'playlist_category': music_picker_playlist_category,
                'confirmation': music_picker_confirmation,
            }
        else:
            playlist_result = music_picker.pick_playlist(
                prompt_text=self.text,
                emotion=recommendation_emotion,
                top_emotions=recommendation_top_emotions,
                all_scores=recommendation_all_scores,
                confidence_band=confidence_band,
                confidence_margin=confidence_margin,
                candidates=tracks,
                preferred_artists=preferred_artists,
                user=user,
                taste_profile=normalized_taste_profile,
            )
            recommended_tracks = playlist_result.get('tracks') or tracks[:20]
            selected_track = playlist_result.get('selected_track') or heuristic_selected_track
            selected_track_source = (
                selected_track.get('recommendation_source')
                if isinstance(selected_track, dict)
                else None
            )
            music_picker_strategy = playlist_result.get('strategy') or 'heuristic_playlist'
            music_picker_reason = playlist_result.get('reason')
            music_picker_used_fallback = bool(playlist_result.get('used_fallback', True))
            music_picker_intent = playlist_result.get('intent')
            music_picker_artist_name = playlist_result.get('artist_name')
            music_picker_track_name = playlist_result.get('track_name')
            music_picker_playlist_category = playlist_result.get('playlist_category')
            music_picker_confirmation = playlist_result.get('confirmation')

        # Taste control gets the final say: "more familiar" opens with the
        # favorites saved for this emotion, "more discovery" refuses the static
        # curated tracks, and "balanced" opens with the docs/music.md list.
        recommended_tracks, selected_track = _apply_taste_control(
            recommended_tracks,
            selected_track,
            familiarity=normalized_taste_profile.get('familiarity'),
            prefer_instrumental=normalized_taste_profile.get('prefer_instrumental'),
            emotions=(emotion, recommendation_emotion),
            user=user,
            limit=max(len(recommended_tracks), 1),
            candidates=tracks,
        )
        selected_track_source = (
            selected_track.get('recommendation_source')
            if isinstance(selected_track, dict)
            else selected_track_source
        )

        # Save prompt history
        continuation_token = None
        if user and self.persist_history:
            active_session_plan = (
                update_session_plan_progress(
                    self.session_plan,
                    duration_seconds=0,
                    tracks_played=0,
                )
                if isinstance(self.session_plan, dict)
                else None
            )
            music_picker_data = {
                'strategy': music_picker_strategy,
                'reason': music_picker_reason,
                'used_fallback': music_picker_used_fallback,
                'outcome_mode': normalized_outcome_mode,
                'outcome_label': outcome_label,
                'outcome_description': outcome_description,
                'search_plan': {
                    'strategy': (
                        llm_search_plan['strategy']
                        if llm_search_plan['used']
                        else 'spotify_emotion_candidate_retrieval'
                    ),
                    'reason': llm_search_plan['reason'] or (
                        'Candidates were retrieved from Spotify personalization, '
                        'emotion queries, and curated fallbacks before final ranking.'
                    ),
                    'used_fallback': bool(spotify_result.get('used_fallback')),
                    # The LLM's queries, when it produced any. An empty list
                    # means retrieval ran on the built-in queries alone.
                    'queries': llm_search_plan['search_queries'],
                    'provider': (
                        llm_search_plan['provider']
                        if llm_search_plan['used']
                        else playlist_result.get('provider')
                    ),
                    'model': (
                        llm_search_plan['model']
                        if llm_search_plan['used']
                        else playlist_result.get('model')
                    ),
                    'error': (
                        llm_search_plan['error']
                        or spotify_result.get('fallback_reason')
                    ),
                    'confidence': llm_search_plan['confidence'],
                    'intent': 'candidate_retrieval',
                    'artist_name': None,
                    'track_name': None,
                    'playlist_category': (
                        llm_search_plan['playlist_category']
                        or playlist_result.get('playlist_category')
                        or emotion
                    ),
                    'confirmation': None,
                },
                'selected_track_id': (
                    selected_track.get('id') if isinstance(selected_track, dict) else None
                ),
                'playlist_track_ids': [
                    str(track.get('id') or '').strip()
                    for track in recommended_tracks
                    if str(track.get('id') or '').strip()
                ] or playlist_result.get('playlist_track_ids') or [],
                'selected_track_source': selected_track_source,
                'candidate_tracks': tracks[:12],
                'confidence_band': confidence_band,
                'plutchik_scores': plutchik_scores,
                'plutchik_top_emotions': plutchik_top_emotions,
                'plutchik_dominant_emotion': plutchik_dominant_emotion,
                'plutchik_profile_version': plutchik_profile_version,
                'llm_provider': playlist_result.get('provider'),
                'llm_model': playlist_result.get('model'),
                'llm_error': playlist_result.get('error'),
                'llm_confidence': playlist_result.get('confidence'),
                'recommendation_target_emotion': recommendation_target_emotion,
                'intent': music_picker_intent,
                'artist_name': music_picker_artist_name,
                'track_name': music_picker_track_name,
                'playlist_category': music_picker_playlist_category,
                'confirmation': music_picker_confirmation,
                'progressive_stage': 'initial' if is_initial_stage else 'full',
                'recovery_plan': self.recovery_plan,
                'session_plan': active_session_plan,
                'personalization': normalized_taste_profile,
            }
            try:
                existing_history = None
                if self.history_id:
                    existing_history = PromptHistory.objects.filter(
                        id=self.history_id,
                        user=user,
                    ).first()

                if existing_history:
                    existing_history.prompt_text = self.text
                    existing_history.detected_emotion = emotion
                    existing_history.emotion_confidence = confidence
                    existing_history.emotion_scores = all_scores
                    existing_history.ai_response = ai_response
                    existing_history.playlist_data = recommended_tracks
                    existing_history.music_picker_data = music_picker_data
                    existing_history.save(update_fields=[
                        'prompt_text',
                        'detected_emotion',
                        'emotion_confidence',
                        'emotion_scores',
                        'ai_response',
                        'playlist_data',
                        'music_picker_data',
                    ])
                    self.history_id = existing_history.id
                else:
                    history = PromptHistory.objects.create(
                        user=user,
                        prompt_text=self.text,
                        detected_emotion=emotion,
                        emotion_confidence=confidence,
                        emotion_scores=all_scores,
                        ai_response=ai_response,
                        playlist_data=recommended_tracks,
                        music_picker_data=music_picker_data,
                    )
                    self.history_id = history.id
            except Exception:
                logger.exception("Failed to save prompt history for user %s", user.id)
                self.history_id = None
        elif not user:
            self.history_id = None

        if is_initial_stage:
            continuation_token = _build_recommendation_continuation_token(
                self.request,
                text=self.text,
                result=self.result,
                persist_history=self.persist_history,
                history_id=self.history_id,
                outcome_mode=normalized_outcome_mode,
                session_plan=self.session_plan,
                taste_profile=normalized_taste_profile,
            )

        return {
            'emotion': emotion,
            'confidence': round(confidence * 100, 1),
            'all_scores': {k: round(v * 100, 1) for k, v in all_scores.items()},
            'top_emotions': [
                {
                    'emotion': item.get('emotion'),
                    'confidence': round(float(item.get('confidence', 0.0)) * 100, 1),
                }
                for item in top_emotions
            ],
            'secondary_emotion': secondary_emotion,
            'plutchik_scores': {
                emotion_name: round(float(score) * 100, 1)
                for emotion_name, score in plutchik_scores.items()
            },
            'plutchik_top_emotions': [
                {
                    'emotion': item.get('emotion'),
                    'confidence': round(float(item.get('confidence', 0.0)) * 100, 1),
                }
                for item in plutchik_top_emotions
            ],
            'plutchik_dominant_emotion': plutchik_dominant_emotion,
            'plutchik_profile_version': plutchik_profile_version,
            'outcome_mode': normalized_outcome_mode,
            'outcome_label': outcome_label,
            'outcome_description': outcome_description,
            'outcome_phase': outcome_profile.get('outcome_phase'),
            'recommendation_target_emotion': recommendation_target_emotion,
            'taste_profile': normalized_taste_profile,
            'session_plan': self.session_plan,
            'prediction_source': prediction_source,
            'prediction_strategy': prediction_strategy,
            'confidence_band': confidence_band,
            'confidence_margin': round(float(confidence_margin) * 100, 1),
            'prediction_fallback_used': fallback_used,
            'prediction_fallback_reason': fallback_reason,
            'needs_review': needs_review,
            'ai_response': ai_response,
            'tracks': recommended_tracks,
            'selected_track': selected_track,
            'selected_track_source': selected_track_source,
            'music_picker_strategy': music_picker_strategy,
            'music_picker_reason': music_picker_reason,
            'music_picker_used_fallback': music_picker_used_fallback,
            'music_picker_intent': music_picker_intent,
            'music_picker_artist_name': music_picker_artist_name,
            'music_picker_track_name': music_picker_track_name,
            'music_picker_playlist_category': music_picker_playlist_category,
            'music_picker_confirmation': music_picker_confirmation,
            'tracks_source': spotify_result.get('source') or 'fallback',
            'tracks_fallback_used': bool(spotify_result.get('used_fallback')),
            'tracks_fallback_reason': spotify_result.get('fallback_reason'),
            'tracks_personalized': bool(spotify_result.get('personalized')),
            'tracks_personalization_sources': (
                spotify_result.get('personalization_sources') or []
            ),
            'tracks_personalization_missing_scopes': (
                spotify_result.get('personalization_missing_scopes') or []
            ),
            'progressive_stage': 'initial' if is_initial_stage else 'full',
            'loading_more_tracks': bool(continuation_token),
            'continuation_token': continuation_token,
            'history_id': self.history_id,
            'recovery_plan': self.recovery_plan,
        }


def _emotion_favorite_leads(emotions, user, limit=20):
    """Favorites the user hearted under these emotions, oldest first.

    "More familiar" opens the playlist with these, so the first song hearted
    for an emotion is the first one heard when that emotion comes back. More
    than one emotion is accepted because an outcome mode can shift the lane the
    playlist is built for, while the heart was pressed under the detected one.
    """
    if not user or not getattr(user, 'is_authenticated', False):
        return []

    if isinstance(emotions, str):
        emotions = [emotions]
    normalized_emotions = []
    for value in emotions or []:
        normalized = str(value or '').strip().lower()
        if normalized and normalized not in normalized_emotions:
            normalized_emotions.append(normalized)
    if not normalized_emotions:
        return []

    leads = []
    favorites = sorted(
        FavoriteTrack.objects.filter(
            user=user,
            emotion__in=normalized_emotions,
        ).order_by('added_at')[:limit],
        key=lambda favorite: (
            normalized_emotions.index(favorite.emotion),
            favorite.added_at,
        ),
    )
    for favorite in favorites:
        leads.append({
            'id': favorite.spotify_track_id,
            'item_type': 'track',
            'name': favorite.track_name,
            'artist': favorite.artist_name,
            'album': favorite.album_name,
            'image': favorite.album_image,
            'preview_url': favorite.preview_url,
            'duration_ms': favorite.duration_ms,
            'uri': f'spotify:track:{favorite.spotify_track_id}',
            'spotify_url': (
                f'https://open.spotify.com/track/{favorite.spotify_track_id}'
            ),
            'recommendation_source': 'favorite_track',
            'is_favorite': True,
            'favorite_emotion': favorite.emotion,
        })
    return leads


def _track_identity(track):
    return str(track.get('uri') or track.get('id') or '').strip()


def _apply_taste_control(
    tracks,
    selected_track,
    *,
    familiarity,
    emotions,
    user,
    limit,
    candidates=None,
    prefer_instrumental=False,
):
    """Give the taste control its final say over the playlist.

    Ranking happens upstream; this only enforces what the three settings
    promise the user, and returns ``(tracks, selected_track)``. "Balanced"
    opens with the docs/music.md list for the emotion, pulling it out of
    ``candidates`` -- the whole ranked pool -- because the first progressive
    stage hands this only the single track it already chose to play.
    """
    working = [track for track in (tracks or []) if isinstance(track, dict)]

    if familiarity == 'familiar':
        # The favorites lead, but only up to their quota: the rest of the
        # playlist stays available for songs the user has not heard yet.
        leads = _emotion_favorite_leads(
            emotions,
            user,
            limit=familiar_favorite_quota(limit),
        )
        if leads:
            lead_ids = {
                str(track.get('id') or '').strip()
                for track in leads
                if str(track.get('id') or '').strip()
            }
            fresh = [
                track for track in working
                if str(track.get('id') or '').strip() not in lead_ids
            ]
            working = leads + fresh
            selected_track = leads[0]
    elif familiarity == 'discovery':
        # Discovery must not serve the static curated list, but an empty
        # playlist helps nobody, so the filter only applies when something
        # real survives it.
        fresh = [
            track for track in working
            if str(track.get('recommendation_source') or '').strip().lower()
            not in STATIC_TRACK_SOURCES
        ]
        if fresh:
            working = fresh
            if (
                not isinstance(selected_track, dict)
                or str(selected_track.get('recommendation_source') or '').strip().lower()
                in STATIC_TRACK_SOURCES
            ):
                selected_track = fresh[0]
    elif not prefer_instrumental:
        # Balanced serves the static list: the songs docs/music.md pairs with
        # this emotion lead the playlist in document order, however the ranker
        # happened to score them. An instrumental request skips this -- the
        # document list is vocal pop, and the ranking already put the
        # instrumental candidates on top.
        pool = working + [
            track for track in (candidates or []) if isinstance(track, dict)
        ]
        for candidate_emotion in emotions:
            # Half the playlist at most, the same share the blender gives the
            # document, so the ranked picks still get a say.
            leads = music_doc_tracks(
                pool, candidate_emotion, limit=max(limit // 2, 1),
            )
            if not leads:
                continue
            lead_keys = {key for key in map(_track_identity, leads) if key}
            working = leads + [
                track for track in working
                if _track_identity(track) not in lead_keys
            ]
            selected_track = leads[0]
            break

    return (working[:limit] if limit else working), selected_track


def _build_emotion_response_payload(
    request,
    *,
    text,
    result,
    persist_history=True,
    recommendation_stage='full',
    history_id=None,
    recommendation_profile=None,
    recovery_plan=None,
    outcome_mode=None,
    session_length_minutes=None,
    check_in_frequency_tracks=None,
    taste_profile=None,
    session_plan=None,
):
    return EmotionResponseBuilder(
        request,
        text=text,
        result=result,
        persist_history=persist_history,
        recommendation_stage=recommendation_stage,
        history_id=history_id,
        recommendation_profile=recommendation_profile,
        recovery_plan=recovery_plan,
        outcome_mode=outcome_mode,
        session_length_minutes=session_length_minutes,
        check_in_frequency_tracks=check_in_frequency_tracks,
        taste_profile=taste_profile,
        session_plan=session_plan,
    ).build()


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

    severity = assess_crisis_severity(text)
    if severity:
        logger.warning(
            "Crisis-risk language (%s) detected in analyze_emotion (user=%s)",
            severity,
            request.user.id if request.user.is_authenticated else None,
        )
        _record_support_event(RISK_CRISIS, 'phrase', 'analyze_emotion')
        return Response(_build_crisis_response_payload(severity))

    outcome_mode = _request_outcome_mode(request)
    session_length_minutes = _request_session_length_minutes(request)
    check_in_frequency_tracks = _request_check_in_frequency_tracks(request)
    taste_profile = _request_taste_profile(request)

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
        recommendation_stage='initial',
        outcome_mode=outcome_mode,
        session_length_minutes=session_length_minutes,
        check_in_frequency_tracks=check_in_frequency_tracks,
        taste_profile=taste_profile,
    )
    concern_trigger = assess_concern(text, result)
    if concern_trigger:
        _record_support_event(RISK_CONCERN, concern_trigger, 'analyze_emotion')
        _attach_concern_check_in(payload, concern_trigger)
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
        return Response(_build_crisis_response_payload(severity))

    text = raw_text or f'Play songs for a {emotion} mood.'
    outcome_mode = _request_outcome_mode(request)
    session_length_minutes = _request_session_length_minutes(request)
    check_in_frequency_tracks = _request_check_in_frequency_tracks(request)
    taste_profile = _request_taste_profile(request)
    persist_history = (
        bool(request.user.is_authenticated)
        and should_persist_recommendation_context(
            outcome_mode=outcome_mode,
            session_length_minutes=(
                0 if session_length_minutes is None else session_length_minutes
            ),
            taste_profile=taste_profile,
        )
    )
    result = _build_explicit_emotion_result(emotion)
    payload = _build_emotion_response_payload(
        request,
        text=text,
        result=result,
        persist_history=persist_history,
        recommendation_stage='initial',
        outcome_mode=outcome_mode,
        session_length_minutes=session_length_minutes,
        check_in_frequency_tracks=check_in_frequency_tracks,
        taste_profile=taste_profile,
    )
    # Phrase check on caller-supplied text only. The result here is the tab the
    # user picked, not a prediction, so choosing "depressing" must not count as
    # a model-confident concern.
    concern_trigger = assess_concern(raw_text)
    if concern_trigger:
        _record_support_event(RISK_CONCERN, concern_trigger, 'recommend_by_emotion')
        _attach_concern_check_in(payload, concern_trigger)
    return Response(payload)


@api_view(['POST'])
def recommendation_playlist(request):
    """Continue a progressive recommendation request and return the full playlist."""
    continuation_token = str(request.data.get('continuation_token', '')).strip()
    if not continuation_token:
        return Response(
            {'error': 'continuation_token is required'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        payload = _load_recommendation_continuation_token(request, continuation_token)
    except signing.SignatureExpired:
        return Response(
            {'error': 'This recommendation request expired. Please try again.'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    except signing.BadSignature:
        return Response(
            {'error': 'Invalid continuation token.'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    except PermissionError as error:
        return Response({'error': str(error)}, status=status.HTTP_403_FORBIDDEN)

    return Response(
        _build_emotion_response_payload(
            request,
            text=str(payload.get('text', '')).strip(),
            result=payload.get('result') or _fallback_analysis(),
            persist_history=bool(payload.get('persist_history', False)),
            recommendation_stage='continuation',
            history_id=payload.get('history_id'),
            outcome_mode=payload.get('outcome_mode'),
            session_plan=payload.get('session_plan'),
            taste_profile=payload.get('taste_profile'),
        )
    )


@api_view(['POST'])
def check_feel_better(request):
    """Check whether a high-intensity session should show a recovery prompt."""
    history_id = request.data.get('history_id')
    listen_duration = request.data.get('duration', 0)
    tracks_played = max(_safe_int(request.data.get('tracks_played'), 0), 0)

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
        recommendation_stage='full',
        history_id=history.id,
        recovery_plan=recovery_plan,
        outcome_mode=music_picker_data.get('outcome_mode'),
        session_plan=session_plan,
        taste_profile=music_picker_data.get('personalization'),
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
def search_artists(request):
    """Search artists for preference selection"""
    query = request.query_params.get('q', '')
    if not query:
        return Response([])

    search_result = spotify_service.search_catalog(
        query,
        'artist',
        user=request.user if request.user.is_authenticated else None,
        limit=5,
    )
    if search_result['ok']:
        return Response(search_result['items'])

    return Response(
        spotify_service.api_error_payload(
            search_result,
            default_message='Spotify artist search failed.',
        ),
        status=spotify_service.upstream_http_status(search_result),
    )


@api_view(['GET'])
def search_tracks(request):
    """Search tracks"""
    query = request.query_params.get('q', '')
    if not query:
        return Response([])

    search_result = spotify_service.search_catalog(
        query,
        'track',
        user=request.user if request.user.is_authenticated else None,
        limit=20,
    )
    if search_result['ok']:
        return Response(search_result['items'])

    return Response(
        spotify_service.api_error_payload(
            search_result,
            default_message='Spotify track search failed.',
        ),
        status=spotify_service.upstream_http_status(search_result),
    )


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

