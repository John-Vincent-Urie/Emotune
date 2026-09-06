"""
Spotify API Service for EmoTune
Handles authentication, track search, and playlist generation

This module used to be a single ~4700-line SpotifyService class. It is now a
thin facade: SpotifyService builds one instance of each collaborator
(auth / search / personalization / recommendations / playback) and re-exposes
every original method name as a delegating method, so every existing caller
(views.py, tests.py, ...) keeps working unchanged. See backend/api/spotify/
for the actual implementations, and spotify/utils.py for the small stateless
helpers shared across all of them.

`requests` and `time` are imported here (even though this module no longer
makes HTTP calls directly) because the test suite patches them via dotted
paths like `api.spotify_service.requests.post` / `api.spotify_service.time.monotonic`;
since `requests`/`time` are shared singleton modules, patching an attribute
through this import still patches the exact same callable the collaborators
use.
"""
import requests
import time
import logging

from django.conf import settings

from .spotify.auth import SpotifyAuthError, SpotifyAuthClient
from .spotify.search import SpotifyCatalogSearch
from .spotify.personalization import SpotifyPersonalizationEngine
from .spotify.recommendations import SpotifyRecommendationEngine
from .spotify.playback import SpotifyPlaybackClient
from .spotify import utils
from .spotify.constants import (  # noqa: F401 -- re-exported for backwards compatibility
    SUPPORTED_SPOTIFY_ITEM_TYPES,
    EMOTION_QUERY_PROFILES,
    MUSIC_PICKER_DOC_EMOTIONS,
)

logger = logging.getLogger(__name__)


class SpotifyService:
    def __init__(self):
        client_id = settings.SPOTIFY_CLIENT_ID
        client_secret = settings.SPOTIFY_CLIENT_SECRET
        redirect_uri = settings.SPOTIFY_REDIRECT_URI
        request_timeout_seconds = max(
            float(getattr(settings, 'SPOTIFY_HTTP_TIMEOUT_SECONDS', 3)),
            0.5,
        )
        # These four live directly on the facade (not on the recommendations
        # collaborator) because the test suite does
        # `patch.object(spotify_service, 'recommendation_budget_seconds', ...)`,
        # which requires a genuine instance attribute -- patching a property
        # here would break on context-manager exit (properties have no
        # meaningful deleter for mock to fall back to). recommendations.py
        # reads them back via `self.service.<name>`.
        self.recommendation_budget_seconds = max(
            float(getattr(settings, 'SPOTIFY_RECOMMENDATION_BUDGET_SECONDS', 6)),
            1.0,
        )
        self.llm_exact_seed_enabled = bool(
            getattr(settings, 'LLM_MUSIC_PICKER_EXACT_SONG_SEED_ENABLED', True)
        )
        self.llm_exact_seed_query_limit = max(
            int(getattr(settings, 'LLM_MUSIC_PICKER_EXACT_SONG_SEED_QUERY_LIMIT', 3) or 3),
            1,
        )
        self.emotion_seed_track_limit = max(
            int(getattr(settings, 'MUSIC_PICKER_EMOTION_SEED_TRACK_LIMIT', 10) or 10),
            1,
        )

        self.auth = SpotifyAuthClient(
            service=self,
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            request_timeout_seconds=request_timeout_seconds,
        )
        self.search = SpotifyCatalogSearch(service=self)
        self.personalization = SpotifyPersonalizationEngine(service=self)
        self.recommendations = SpotifyRecommendationEngine(service=self)
        self.playback = SpotifyPlaybackClient(service=self)

    # -- settings that live on the auth collaborator, re-exposed here so
    #    cross-collaborator code (and any external caller) can keep reading
    #    them as plain attributes of the facade, exactly like before the
    #    split.
    @property
    def client_id(self):
        return self.auth.client_id

    @property
    def client_secret(self):
        return self.auth.client_secret

    @property
    def redirect_uri(self):
        return self.auth.redirect_uri

    @property
    def request_timeout_seconds(self):
        return self.auth.request_timeout_seconds

    @property
    def _client_token(self):
        return self.auth._client_token

    @_client_token.setter
    def _client_token(self, value):
        self.auth._client_token = value

    @property
    def _client_token_expires_at(self):
        return self.auth._client_token_expires_at

    @_client_token_expires_at.setter
    def _client_token_expires_at(self, value):
        self.auth._client_token_expires_at = value

    def get_auth_url(self, *args, **kwargs):
        return self.auth.get_auth_url(*args, **kwargs)

    def _normalize_scopes(self, *args, **kwargs):
        return utils._normalize_scopes(*args, **kwargs)

    def _required_playback_scopes(self, *args, **kwargs):
        return utils._required_playback_scopes(*args, **kwargs)

    def _requested_scopes(self, *args, **kwargs):
        return utils._requested_scopes(*args, **kwargs)

    def _personalization_scope_map(self, *args, **kwargs):
        return utils._personalization_scope_map(*args, **kwargs)

    def _token_payload_summary(self, *args, **kwargs):
        return utils._token_payload_summary(*args, **kwargs)

    def _parse_response_json(self, *args, **kwargs):
        return utils._parse_response_json(*args, **kwargs)

    def _extract_error_details(self, *args, **kwargs):
        return utils._extract_error_details(*args, **kwargs)

    def _classify_upstream_failure(self, *args, **kwargs):
        return utils._classify_upstream_failure(*args, **kwargs)

    def _build_failure_response(self, *args, **kwargs):
        return utils._build_failure_response(*args, **kwargs)

    def _build_request_exception_failure_response(self, *args, **kwargs):
        return utils._build_request_exception_failure_response(*args, **kwargs)

    def _developer_allowlist_message(self, *args, **kwargs):
        return utils._developer_allowlist_message(*args, **kwargs)

    def _has_developer_allowlist_issue(self, *args, **kwargs):
        return utils._has_developer_allowlist_issue(*args, **kwargs)

    def _compact_failure(self, *args, **kwargs):
        return utils._compact_failure(*args, **kwargs)

    def exchange_code(self, *args, **kwargs):
        return self.auth.exchange_code(*args, **kwargs)

    def refresh_token(self, *args, **kwargs):
        return self.auth.refresh_token(*args, **kwargs)

    def get_client_token_details(self, *args, **kwargs):
        return self.auth.get_client_token_details(*args, **kwargs)

    def get_client_token(self, *args, **kwargs):
        return self.auth.get_client_token(*args, **kwargs)

    def ensure_valid_token_with_details(self, *args, **kwargs):
        return self.auth.ensure_valid_token_with_details(*args, **kwargs)

    def ensure_valid_token(self, *args, **kwargs):
        return self.auth.ensure_valid_token(*args, **kwargs)

    def _spotify_request(self, *args, **kwargs):
        return self.auth._spotify_request(*args, **kwargs)

    def _spotify_get(self, *args, **kwargs):
        return self.auth._spotify_get(*args, **kwargs)

    def _spotify_put(self, *args, **kwargs):
        return self.auth._spotify_put(*args, **kwargs)

    def _spotify_post(self, *args, **kwargs):
        return self.auth._spotify_post(*args, **kwargs)

    def _choose_transfer_device(self, *args, **kwargs):
        return self.playback._choose_transfer_device(*args, **kwargs)

    def get_playback_debug_status(self, *args, **kwargs):
        return self.playback.get_playback_debug_status(*args, **kwargs)

    def prepare_playback(self, *args, **kwargs):
        return self.playback.prepare_playback(*args, **kwargs)

    def execute_playback_command(self, *args, **kwargs):
        return self.playback.execute_playback_command(*args, **kwargs)

    def _build_search_result(self, *args, **kwargs):
        return self.search._build_search_result(*args, **kwargs)

    def search_tracks_detailed(self, *args, **kwargs):
        return self.search.search_tracks_detailed(*args, **kwargs)

    def search_tracks(self, *args, **kwargs):
        return self.search.search_tracks(*args, **kwargs)

    def _get_catalog_token_candidates(self, *args, **kwargs):
        return self.search._get_catalog_token_candidates(*args, **kwargs)

    def _get_recommendation_tokens(self, *args, **kwargs):
        return self.search._get_recommendation_tokens(*args, **kwargs)

    def search_artists_detailed(self, *args, **kwargs):
        return self.search.search_artists_detailed(*args, **kwargs)

    def search_catalog(self, *args, **kwargs):
        return self.search.search_catalog(*args, **kwargs)

    def upstream_http_status(self, *args, **kwargs):
        return self.search.upstream_http_status(*args, **kwargs)

    def api_error_payload(self, *args, **kwargs):
        return self.search.api_error_payload(*args, **kwargs)

    def _build_recommendation_queries(self, *args, **kwargs):
        return self.recommendations._build_recommendation_queries(*args, **kwargs)

    def _build_curated_emotion_queries(self, *args, **kwargs):
        return self.recommendations._build_curated_emotion_queries(*args, **kwargs)

    def _select_seed_tracks(self, *args, **kwargs):
        return self.recommendations._select_seed_tracks(*args, **kwargs)

    def _build_seed_track_queries(self, *args, **kwargs):
        return self.recommendations._build_seed_track_queries(*args, **kwargs)

    def _build_exact_track_queries(self, *args, **kwargs):
        return self.recommendations._build_exact_track_queries(*args, **kwargs)

    def _safe_int(self, *args, **kwargs):
        return utils._safe_int(*args, **kwargs)

    def _clamp_spotify_limit(self, *args, **kwargs):
        return utils._clamp_spotify_limit(*args, **kwargs)

    def _clamp_spotify_search_limit(self, *args, **kwargs):
        return utils._clamp_spotify_search_limit(*args, **kwargs)

    def _track_match_key(self, *args, **kwargs):
        return utils._track_match_key(*args, **kwargs)

    def _canonical_track_title(self, *args, **kwargs):
        return utils._canonical_track_title(*args, **kwargs)

    def _extract_exact_query_constraints(self, *args, **kwargs):
        return self.recommendations._extract_exact_query_constraints(*args, **kwargs)

    def _seed_metadata_for_query(self, *args, **kwargs):
        return self.recommendations._seed_metadata_for_query(*args, **kwargs)

    def _unique_text_values(self, *args, **kwargs):
        return utils._unique_text_values(*args, **kwargs)

    def _annotate_tracks_for_query(self, *args, **kwargs):
        return self.recommendations._annotate_tracks_for_query(*args, **kwargs)

    def _filter_tracks_for_query(self, *args, **kwargs):
        return self.recommendations._filter_tracks_for_query(*args, **kwargs)

    def _normalize_playable_item(self, *args, **kwargs):
        return utils._normalize_playable_item(*args, **kwargs)

    def _build_saved_track_reference(self, *args, **kwargs):
        return self.recommendations._build_saved_track_reference(*args, **kwargs)

    def _append_unique_tracks(self, *args, **kwargs):
        return utils._append_unique_tracks(*args, **kwargs)

    def sanitize_recommendations(self, *args, **kwargs):
        return self.recommendations.sanitize_recommendations(*args, **kwargs)

    def _emotion_candidate_weight_map(self, *args, **kwargs):
        return self.recommendations._emotion_candidate_weight_map(*args, **kwargs)

    def rank_tracks_for_emotion(self, *args, **kwargs):
        return self.recommendations.rank_tracks_for_emotion(*args, **kwargs)

    def blend_recommendation_groups(self, *args, **kwargs):
        return self.recommendations.blend_recommendation_groups(*args, **kwargs)

    def select_primary_track(self, *args, **kwargs):
        return self.recommendations.select_primary_track(*args, **kwargs)

    def _build_user_fallback_tracks(self, *args, **kwargs):
        return self.recommendations._build_user_fallback_tracks(*args, **kwargs)

    def _build_curated_fallback_tracks(self, *args, **kwargs):
        return self.recommendations._build_curated_fallback_tracks(*args, **kwargs)

    def _build_fallback_tracks(self, *args, **kwargs):
        return self.recommendations._build_fallback_tracks(*args, **kwargs)

    def get_recommendations_with_details(self, *args, **kwargs):
        return self.recommendations.get_recommendations_with_details(*args, **kwargs)

    def get_recommendations(self, *args, **kwargs):
        return self.recommendations.get_recommendations(*args, **kwargs)

    def build_emotion_pool(self, *args, **kwargs):
        return self.recommendations.build_emotion_pool(*args, **kwargs)

    def refresh_emotion_pool(self, *args, **kwargs):
        return self.recommendations.refresh_emotion_pool(*args, **kwargs)

    def get_user_profile_result(self, *args, **kwargs):
        return self.recommendations.get_user_profile_result(*args, **kwargs)

    def get_user_profile(self, *args, **kwargs):
        return self.recommendations.get_user_profile(*args, **kwargs)

    def search_artists(self, *args, **kwargs):
        return self.search.search_artists(*args, **kwargs)

    def _format_artists(self, *args, **kwargs):
        return self.search._format_artists(*args, **kwargs)

    def _format_tracks(self, *args, **kwargs):
        return utils._format_tracks(*args, **kwargs)

    def _format_nested_track_items(self, *args, **kwargs):
        return utils._format_nested_track_items(*args, **kwargs)

    def _build_personalization_context(self, *args, **kwargs):
        return self.personalization._build_personalization_context(*args, **kwargs)

    def _score_personalized_track(self, *args, **kwargs):
        return self.personalization._score_personalized_track(*args, **kwargs)

    def _track_has_personalized_emotion_signal(self, *args, **kwargs):
        return self.personalization._track_has_personalized_emotion_signal(*args, **kwargs)

    def _history_allows_learning(self, *args, **kwargs):
        return utils._history_allows_learning(*args, **kwargs)

    def _normalize_taste_profile(self, *args, **kwargs):
        return utils._normalize_taste_profile(*args, **kwargs)

    def _taste_discovery_bonus(self, *args, **kwargs):
        return utils._taste_discovery_bonus(*args, **kwargs)

    def _taste_instrumental_bonus(self, *args, **kwargs):
        return utils._taste_instrumental_bonus(*args, **kwargs)

    def get_user_music_candidates(self, *args, **kwargs):
        return self.personalization.get_user_music_candidates(*args, **kwargs)


spotify_service = SpotifyService()
