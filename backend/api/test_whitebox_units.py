"""White-box unit tests for EmoTune's pure helper logic.

Each test targets one branch or path of the code under test; the test case IDs
(WB-xxx-nn) match the white-box testing documentation. Nothing here touches
the network, Spotify or the BERT model -- those are replaced with fakes so each
path can be driven directly.

Tests named after a defect (DEF-nn) pin down a bug found during white-box
testing and since fixed, so it cannot come back unnoticed.
"""
import threading
from types import SimpleNamespace
from unittest.mock import patch

import torch
from django.core import signing
from django.test import RequestFactory, SimpleTestCase, override_settings
from rest_framework.request import Request
from rest_framework.parsers import JSONParser

from api import http_client
from api.spotify.search import SpotifyCatalogSearch
from api.spotify.utils import (
    _append_unique_tracks,
    _canonical_track_title,
    _clamp_spotify_limit,
    _clamp_spotify_search_limit,
    _classify_upstream_failure,
    _compact_failure,
    _extract_error_details,
    _format_nested_track_items,
    _format_tracks,
    _has_developer_allowlist_issue,
    _normalize_playable_item,
    _normalize_scopes,
    _parse_response_json,
    _parse_retry_after,
    _required_playback_scopes,
    _token_payload_summary,
    _track_match_key,
    _unique_text_values,
)
from api.spotify_oauth_state import STATE_SALT, issue_state, read_state
from ml.emotion_classifier import EMOTIONS, EmotionClassifier
from ml.emotion_labels import call_huggingface_loader
from ml.plutchik_mapper import (
    _normalize_emotune_scores,
    _safe_float,
    build_plutchik_profile,
)
from users.throttles import LoginEmailThrottle


# --------------------------------------------------------------------------
# api/spotify/utils.py
# --------------------------------------------------------------------------
class NormalizeScopesTests(SimpleTestCase):
    def test_wb_spu_01_string_is_split_and_deduplicated(self):
        self.assertEqual(
            _normalize_scopes('streaming  streaming user-read-email'),
            ['streaming', 'user-read-email'],
        )

    def test_wb_spu_02_list_drops_blank_and_none_entries(self):
        self.assertEqual(
            _normalize_scopes(['a', '', None, ' b ', 'a']),
            ['a', 'b'],
        )

    def test_wb_spu_03_unsupported_type_returns_empty(self):
        self.assertEqual(_normalize_scopes(42), [])
        self.assertEqual(_normalize_scopes(None), [])

    @override_settings(SPOTIFY_REQUIRED_PLAYBACK_SCOPES='')
    def test_wb_spu_04_required_scopes_fall_back_to_defaults(self):
        scopes = _required_playback_scopes()
        self.assertIn('streaming', scopes)
        self.assertEqual(len(scopes), 5)

    @override_settings(SPOTIFY_REQUIRED_PLAYBACK_SCOPES='streaming')
    def test_wb_spu_05_required_scopes_use_configured_value(self):
        self.assertEqual(_required_playback_scopes(), ['streaming'])


class TokenAndResponseParsingTests(SimpleTestCase):
    def test_wb_spu_06_token_summary_handles_non_dict(self):
        summary = _token_payload_summary('not a dict')
        self.assertFalse(summary['has_access_token'])
        self.assertIsNone(summary['token_type'])
        self.assertEqual(summary['expires_in'], 0)

    def test_wb_spu_07_token_summary_reads_fields(self):
        summary = _token_payload_summary({
            'access_token': 'x', 'refresh_token': '', 'expires_in': '3600',
            'token_type': 'Bearer', 'scope': 'a b',
        })
        self.assertTrue(summary['has_access_token'])
        self.assertFalse(summary['has_refresh_token'])
        self.assertEqual(summary['expires_in'], 3600)
        self.assertEqual(summary['scope'], ['a', 'b'])

    def test_wb_spu_08_response_json_returns_none_on_invalid_body(self):
        response = SimpleNamespace(json=lambda: (_ for _ in ()).throw(ValueError()))
        self.assertIsNone(_parse_response_json(response))

    def test_wb_spu_09_error_details_from_nested_error_object(self):
        details = _extract_error_details(
            {'error': {'status': 403, 'message': ' Premium required '}},
        )
        self.assertEqual(details, {'error_code': '403', 'error_message': 'Premium required'})

    def test_wb_spu_10_error_details_from_oauth_style_payload(self):
        details = _extract_error_details(
            {'error': 'invalid_grant', 'error_description': 'Bad code'},
        )
        self.assertEqual(details['error_code'], 'invalid_grant')
        self.assertEqual(details['error_message'], 'invalid_grant')

    def test_wb_spu_11_error_details_fall_back_to_response_text(self):
        details = _extract_error_details(None, 'x' * 1500)
        self.assertEqual(len(details['error_message']), 1000)

    def test_wb_spu_12_missing_error_code_stays_none(self):
        """DEF-01 (fixed): a missing code used to come back as the text 'None'."""
        details = _extract_error_details({}, 'gateway timeout')
        self.assertIsNone(details['error_code'])


class ClassifyUpstreamFailureTests(SimpleTestCase):
    def reason(self, status, message='', source=''):
        return _classify_upstream_failure(status, message, source=source)['reason']

    def test_wb_spu_13_every_classification_branch(self):
        cases = [
            (None, '', '', 'network_error'),
            (400, 'invalid_client', 'refresh_token', 'refresh_token_rejected'),
            (400, 'Invalid client', '', 'client_credentials_invalid'),
            (400, 'invalid_grant', '', 'invalid_grant'),
            (400, 'Invalid redirect URI', '', 'invalid_grant'),
            (401, '', '', 'token_invalid'),
            (403, 'User not registered for this application', '', 'developer_allowlist_required'),
            (403, 'Premium required', '', 'premium_required'),
            (403, 'Insufficient client scope', '', 'insufficient_scope'),
            (403, 'nope', '', 'forbidden'),
            (429, '', '', 'rate_limited'),
            (503, '', '', 'spotify_unavailable'),
            (404, '', '', 'spotify_request_failed'),
            (400, 'something else', '', 'spotify_request_failed'),
        ]
        for status, message, source, expected in cases:
            with self.subTest(status=status, message=message):
                self.assertEqual(self.reason(status, message, source), expected)

    def test_wb_spu_14_retryable_flags(self):
        self.assertTrue(_classify_upstream_failure(None)['retryable'])
        self.assertTrue(_classify_upstream_failure(429)['retryable'])
        self.assertTrue(_classify_upstream_failure(500)['retryable'])
        self.assertFalse(_classify_upstream_failure(404)['retryable'])


class SmallSpotifyHelperTests(SimpleTestCase):
    def test_wb_spu_15_retry_after_parsing(self):
        self.assertIsNone(_parse_retry_after(None))
        self.assertIsNone(_parse_retry_after('soon'))
        self.assertIsNone(_parse_retry_after('-5'))
        self.assertEqual(_parse_retry_after(' 30 '), 30)

    def test_wb_spu_16_allowlist_issue_detection(self):
        self.assertFalse(_has_developer_allowlist_issue(None))
        self.assertFalse(_has_developer_allowlist_issue({'account': 'x'}))
        self.assertTrue(_has_developer_allowlist_issue(
            {'devices': {'error_reason': 'developer_allowlist_required'}}
        ))
        self.assertTrue(_has_developer_allowlist_issue(
            {'currently_playing': {'developer_allowlist_required': True}}
        ))

    def test_wb_spu_17_compact_failure_merges_extra(self):
        compact = _compact_failure({'reason': 'x', 'source': 's'}, extra={'k': 1})
        self.assertEqual(compact['reason'], 'x')
        self.assertEqual(compact['source'], 's')
        self.assertEqual(compact['k'], 1)
        self.assertIsNone(_compact_failure('bad')['reason'])

    def test_wb_spu_18_limit_clamping_boundaries(self):
        self.assertEqual(_clamp_spotify_limit(0), 1)
        self.assertEqual(_clamp_spotify_limit(51), 50)
        self.assertEqual(_clamp_spotify_limit('abc'), 10)
        self.assertEqual(_clamp_spotify_search_limit(11), 10)
        self.assertEqual(_clamp_spotify_search_limit(None), 5)

    def test_wb_spu_19_unique_text_values(self):
        self.assertEqual(_unique_text_values([' a', 'a', '', None, 'b']), ['a', 'b'])
        self.assertEqual(_unique_text_values(None), [])


class TrackTitleAndKeyTests(SimpleTestCase):
    def test_wb_spu_20_canonical_title_strips_version_suffixes(self):
        cases = {
            'Black - Remastered 2011': 'black',
            'Yellow (Live at Glastonbury)': 'yellow',
            'Song [Explicit]': 'song',
            'Ikaw - (2024 Remastered Version)': 'ikaw',
            'Intro Part 2': 'intro',
            '  Many   Spaces ': 'many spaces',
            '': '',
            None: '',
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(_canonical_track_title(raw), expected)

    def test_wb_spu_21_match_key_uses_first_artist(self):
        key = _track_match_key({'name': 'Hello (Live)', 'artist': 'Adele,  Someone'})
        self.assertEqual(key, 'adele|hello')

    def test_wb_spu_22_match_key_rejects_missing_parts(self):
        self.assertIsNone(_track_match_key('not a dict'))
        self.assertIsNone(_track_match_key({'name': 'Hello', 'artist': ''}))
        self.assertIsNone(_track_match_key({'name': '', 'artist': 'Adele'}))


class NormalizePlayableItemTests(SimpleTestCase):
    def test_wb_spu_23_rejects_non_dict_and_placeholder_artist(self):
        self.assertIsNone(_normalize_playable_item('x'))
        self.assertIsNone(_normalize_playable_item({'id': '1', 'artist': 'Open in Spotify'}))

    def test_wb_spu_24_builds_uri_and_url_from_id(self):
        item = _normalize_playable_item({'id': 'abc', 'name': 'Song', 'artist': 'A'})
        self.assertEqual(item['uri'], 'spotify:track:abc')
        self.assertEqual(item['spotify_url'], 'https://open.spotify.com/track/abc')
        self.assertEqual(item['recommendation_source'], 'spotify')

    def test_wb_spu_25_reads_type_and_id_from_uri(self):
        item = _normalize_playable_item({'uri': 'spotify:playlist:p1'})
        self.assertEqual(item['item_type'], 'playlist')
        self.assertEqual(item['id'], 'p1')

    def test_wb_spu_26_unplayable_item_is_dropped(self):
        self.assertIsNone(_normalize_playable_item({'name': 'No ids at all'}))

    def test_wb_spu_27_preview_only_item_is_kept_with_defaults(self):
        item = _normalize_playable_item({'preview_url': 'http://p', 'duration_ms': 'x'})
        self.assertEqual(item['name'], 'Spotify recommendation')
        self.assertEqual(item['artist'], 'Spotify')
        self.assertEqual(item['duration_ms'], 0)

    def test_wb_spu_28_album_url_keeps_album_type(self):
        """DEF-02 (fixed): an album URL used to become a spotify:track: URI."""
        item = _normalize_playable_item({'spotify_url': 'https://open.spotify.com/album/xyz'})
        self.assertEqual(item['uri'], 'spotify:album:xyz')
        self.assertEqual(item['item_type'], 'album')

    def test_wb_spu_28b_explicit_item_type_still_wins(self):
        item = _normalize_playable_item({
            'item_type': 'track',
            'spotify_url': 'https://open.spotify.com/album/xyz',
        })
        self.assertEqual(item['uri'], 'spotify:track:xyz')

    def test_wb_spu_29_append_unique_tracks_dedupes_and_stops_at_limit(self):
        target, seen = [], set()
        candidates = ['bad', {'id': 'a'}, {'id': 'a'}, {'name': 'none'}, {'id': 'b'}, {'id': 'c'}]
        _append_unique_tracks(target, seen, candidates, limit=2)
        self.assertEqual([t['id'] for t in target], ['a', 'b'])


class FormatTracksTests(SimpleTestCase):
    RAW = {
        'id': 't1', 'name': 'Song', 'artists': [{'name': 'A'}, {'name': 'B'}],
        'album': {'name': 'Alb', 'images': [{'url': 'img'}]},
        'external_urls': {'spotify': 'url'}, 'uri': 'spotify:track:t1', 'popularity': '70',
    }

    def test_wb_spu_30_format_tracks(self):
        formatted = _format_tracks([None, self.RAW, {'id': 't2', 'name': 'N'}])
        self.assertEqual(len(formatted), 2)
        self.assertEqual(formatted[0]['artist'], 'A, B')
        self.assertEqual(formatted[0]['image'], 'img')
        self.assertEqual(formatted[0]['popularity'], 70)
        self.assertEqual(formatted[1]['image'], '')

    def test_wb_spu_31_nested_items_carry_timestamps(self):
        items = [
            {'track': self.RAW, 'played_at': 'p', 'added_at': 'a'},
            {'track': None},
            'bad',
        ]
        formatted = _format_nested_track_items(
            items, recommendation_source='recent',
            played_at_key='played_at', added_at_key='added_at',
        )
        self.assertEqual(len(formatted), 1)
        self.assertEqual(formatted[0]['spotify_played_at'], 'p')
        self.assertEqual(formatted[0]['spotify_added_at'], 'a')
        self.assertEqual(formatted[0]['catalog_source'], 'recent')


# --------------------------------------------------------------------------
# api/spotify/search.py
# --------------------------------------------------------------------------
class CatalogSearchTests(SimpleTestCase):
    def setUp(self):
        self.service = SimpleNamespace()
        self.search = SpotifyCatalogSearch(self.service)
        self.service._build_search_result = self.search._build_search_result
        self.service.search_tracks_detailed = self.search.search_tracks_detailed

    def test_wb_srch_01_no_token_returns_failure_without_calling_spotify(self):
        result = self.search.search_tracks_detailed('q', token='')
        self.assertFalse(result['ok'])
        self.assertEqual(result['reason'], 'network_error')
        self.assertEqual(result['items'], [])

    def test_wb_srch_02_auth_failure_raises_when_requested(self):
        from api.spotify.auth import SpotifyAuthError
        self.service._spotify_get = lambda *a, **k: {
            'ok': False, 'status_code': 401, 'error': 'expired',
        }
        with self.assertRaises(SpotifyAuthError):
            self.search.search_tracks('q', 'tok', raise_on_auth=True)
        self.assertEqual(self.search.search_tracks('q', 'tok'), [])

    def test_wb_srch_03_upstream_http_status_mapping(self):
        self.assertEqual(self.search.upstream_http_status({'reason': 'rate_limited'}), 503)
        self.assertEqual(self.search.upstream_http_status({'reason': 'client_credentials_invalid'}), 500)
        self.assertEqual(self.search.upstream_http_status(None), 502)

    def test_wb_srch_04_error_payload_prefers_json_body(self):
        payload = self.search.api_error_payload(
            {'response_json': {'e': 1}, 'response_text': 't'}, default_message='m',
        )
        self.assertEqual(payload['spotify']['response_body'], {'e': 1})
        payload = self.search.api_error_payload('bad', default_message='m')
        self.assertIsNone(payload['spotify']['response_body'])


# --------------------------------------------------------------------------
# api/http_client.py
# --------------------------------------------------------------------------
class HttpClientTests(SimpleTestCase):
    def test_wb_http_01_session_is_reused_within_a_thread(self):
        self.assertIs(http_client.get_session(), http_client.get_session())

    def test_wb_http_02_each_thread_gets_its_own_session(self):
        sessions = []
        worker = threading.Thread(target=lambda: sessions.append(http_client.get_session()))
        worker.start()
        worker.join()
        self.assertIsNot(sessions[0], http_client.get_session())

    def test_wb_http_03_helpers_delegate_to_the_session(self):
        session = http_client.get_session()
        with patch.object(session, 'request', return_value='r') as req, \
                patch.object(session, 'post', return_value='p') as post, \
                patch.object(session, 'get', return_value='g') as get:
            self.assertEqual(http_client.request('PUT', 'u', json={}), 'r')
            self.assertEqual(http_client.post('u'), 'p')
            self.assertEqual(http_client.get('u'), 'g')
        req.assert_called_once_with('PUT', 'u', json={})
        post.assert_called_once()
        get.assert_called_once()


# --------------------------------------------------------------------------
# api/spotify_oauth_state.py
# --------------------------------------------------------------------------
class OAuthStateTests(SimpleTestCase):
    def test_wb_oauth_01_round_trip(self):
        self.assertEqual(read_state(issue_state(SimpleNamespace(id=7))), 7)

    def test_wb_oauth_02_blank_and_tampered_states_are_rejected(self):
        self.assertIsNone(read_state(None))
        self.assertIsNone(read_state('   '))
        self.assertIsNone(read_state(issue_state(SimpleNamespace(id=7)) + 'x'))

    @override_settings(SPOTIFY_OAUTH_STATE_MAX_AGE_SECONDS=1)
    def test_wb_oauth_03_expired_state_is_rejected(self):
        state = issue_state(SimpleNamespace(id=7))
        with patch('django.core.signing.time.time', return_value=10**10):
            self.assertIsNone(read_state(state))

    def test_wb_oauth_04_wrong_payload_shapes_are_rejected(self):
        self.assertIsNone(read_state(signing.dumps(['list'], salt=STATE_SALT)))
        self.assertIsNone(read_state(signing.dumps({'uid': '7'}, salt=STATE_SALT)))

    def test_wb_oauth_05_state_from_another_salt_is_rejected(self):
        self.assertIsNone(read_state(signing.dumps({'uid': 7}, salt='other')))


# --------------------------------------------------------------------------
# users/throttles.py
# --------------------------------------------------------------------------
class EmailThrottleKeyTests(SimpleTestCase):
    def make_request(self, body):
        raw = RequestFactory().post('/login/', body, content_type='application/json')
        return Request(raw, parsers=[JSONParser()])

    def test_wb_thr_01_email_is_normalised_into_cache_key(self):
        key = LoginEmailThrottle().get_cache_key(
            self.make_request({'email': '  User@Example.COM '}), None,
        )
        self.assertEqual(key, 'throttle_login_email_user@example.com')

    def test_wb_thr_02_no_email_means_no_key(self):
        throttle = LoginEmailThrottle()
        self.assertIsNone(throttle.get_cache_key(self.make_request({}), None))
        self.assertIsNone(throttle.get_cache_key(SimpleNamespace(), None))


# --------------------------------------------------------------------------
# ml/plutchik_mapper.py and ml/emotion_labels.py
# --------------------------------------------------------------------------
class PlutchikMapperTests(SimpleTestCase):
    def test_wb_plu_01_safe_float(self):
        self.assertEqual(_safe_float('0.5'), 0.5)
        self.assertEqual(_safe_float('abc'), 0.0)
        self.assertEqual(_safe_float(None), 0.0)

    def test_wb_plu_02_percent_scores_are_rescaled(self):
        normalized = _normalize_emotune_scores({'happy': 80, 'sad': -5})
        self.assertAlmostEqual(normalized['happy'], 0.8)
        self.assertEqual(normalized['sad'], 0.0)

    def test_wb_plu_03_empty_input_gives_zero_profile(self):
        profile = build_plutchik_profile(None)
        self.assertTrue(all(v == 0.0 for v in profile['plutchik_scores'].values()))
        self.assertEqual(len(profile['plutchik_top_emotions']), 3)

    def test_wb_plu_04_happy_maps_to_joy(self):
        profile = build_plutchik_profile({'happy': 1.0})
        self.assertEqual(profile['plutchik_dominant_emotion'], 'joy')


class HuggingFaceLoaderTests(SimpleTestCase):
    def test_wb_lbl_01_loader_is_called_with_arguments(self):
        result = call_huggingface_loader(lambda *a, **k: (a, k), 'model', local=True)
        self.assertEqual(result, (('model',), {'local': True}))


# --------------------------------------------------------------------------
# ml/emotion_classifier.py -- BERT path with a fake model
# --------------------------------------------------------------------------
class FakeTokenizer:
    def __call__(self, text, **kwargs):
        return {'input_ids': torch.tensor([[1, 2, 3]])}


class FakeModel:
    """Returns fixed logits so the softmax probabilities are known in advance."""

    def __init__(self, logits):
        self.logits = torch.tensor([logits], dtype=torch.float32)

    def __call__(self, **inputs):
        return SimpleNamespace(logits=self.logits)


def peaked_logits(index, peak):
    logits = [0.0] * len(EMOTIONS)
    logits[index] = peak
    return logits


@patch.object(EmotionClassifier, '_load_goemotions_model', return_value=None)
@patch.object(EmotionClassifier, '_load_model', return_value=None)
class BertPredictPathTests(SimpleTestCase):
    def make(self, logits):
        classifier = EmotionClassifier()
        classifier.goemotions_enabled = False
        classifier.tokenizer = FakeTokenizer()
        classifier.model = FakeModel(logits)
        classifier.model_loaded = True
        return classifier

    def test_wb_clf_01_high_confidence_path(self, *_):
        result = self.make(peaked_logits(EMOTIONS.index('sad'), 10.0)).predict('I am down')
        self.assertEqual(result['emotion'], 'sad')
        self.assertEqual(result['prediction_strategy'], 'bert_high_confidence')
        self.assertFalse(result['needs_review'])

    def test_wb_clf_02_medium_confidence_path(self, *_):
        # softmax gives ~0.55 to the peak: above medium (0.45), below high (0.68).
        result = self.make(peaked_logits(EMOTIONS.index('calm'), 2.8)).predict('fine')
        self.assertEqual(result['prediction_strategy'], 'bert_medium_confidence')
        self.assertTrue(result['needs_review'])

    def test_wb_clf_03_low_confidence_falls_back_to_keywords(self, *_):
        result = self.make([0.0] * len(EMOTIONS)).predict('I feel so lonely tonight')
        self.assertEqual(result['prediction_strategy'], 'keyword_fallback')
        self.assertEqual(result['fallback_reason'], 'low_model_confidence')
        self.assertIn('model_prediction', result)

    def test_wb_clf_04_model_error_falls_back_to_keywords(self, *_):
        classifier = self.make([0.0] * len(EMOTIONS))
        classifier.model = lambda **_: (_ for _ in ()).throw(RuntimeError('boom'))
        with self.assertLogs('ml.emotion_classifier', level='ERROR'):
            result = classifier.predict('I am so angry')
        self.assertEqual(result['fallback_reason'], 'bert_prediction_error')

    def test_wb_clf_05_empty_text_is_uncertain(self, *_):
        result = self.make([0.0] * len(EMOTIONS)).predict('   ')
        self.assertEqual(result['emotion'], 'mixed')
        self.assertEqual(result['fallback_reason'], 'empty_text')

    def test_wb_clf_06_confidence_band_boundaries(self, *_):
        classifier = self.make([0.0] * len(EMOTIONS))
        self.assertEqual(classifier._confidence_band(0.68, 0.12), 'high')
        self.assertEqual(classifier._confidence_band(0.68, 0.11), 'medium')
        self.assertEqual(classifier._confidence_band(0.45, 0.0), 'medium')
        self.assertEqual(classifier._confidence_band(0.44, 0.5), 'low')

    def test_wb_clf_07_margin_with_short_rankings(self, *_):
        classifier = self.make([0.0] * len(EMOTIONS))
        self.assertEqual(classifier._confidence_margin([]), 0.0)
        self.assertEqual(classifier._confidence_margin([{'confidence': 0.4}]), 0.4)


@patch.object(EmotionClassifier, '_load_goemotions_model', return_value=None)
@patch.object(EmotionClassifier, '_load_model', return_value=None)
class LabelMapResolutionTests(SimpleTestCase):
    def resolve(self, id2label=None, num_labels=None):
        model = SimpleNamespace(config=SimpleNamespace(id2label=id2label, num_labels=num_labels))
        return EmotionClassifier()._resolve_model_label_map(model)

    def test_wb_clf_08_named_labels_in_any_order(self, *_):
        labels = list(reversed(EMOTIONS))
        self.assertEqual(self.resolve({i: l for i, l in enumerate(labels)}), labels)

    def test_wb_clf_09_depressed_alias_and_string_keys(self, *_):
        labels = ['Depressed' if l == 'depressing' else l for l in EMOTIONS]
        resolved = self.resolve({str(i): l for i, l in enumerate(labels)})
        self.assertEqual(resolved, EMOTIONS)

    def test_wb_clf_10_generic_labels_assume_emotune_order(self, *_):
        self.assertEqual(self.resolve({i: f'LABEL_{i}' for i in range(len(EMOTIONS))}), EMOTIONS)

    def test_wb_clf_11_mismatched_labels_are_rejected(self, *_):
        self.assertIsNone(self.resolve({0: 'happy', 1: 'sad'}))
        wrong = {i: f'x{i}' for i in range(len(EMOTIONS))}
        self.assertIsNone(self.resolve(wrong))

    def test_wb_clf_12_missing_names_use_num_labels(self, *_):
        self.assertEqual(self.resolve(None, num_labels=len(EMOTIONS)), EMOTIONS)
        self.assertIsNone(self.resolve(None, num_labels=3))
        self.assertIsNone(EmotionClassifier()._resolve_model_label_map(SimpleNamespace()))

    def test_wb_clf_13_goemotions_label_map(self, *_):
        classifier = EmotionClassifier()
        model = SimpleNamespace(config=SimpleNamespace(id2label={0: 'Joy', 1: 'Sadness'}))
        self.assertEqual(classifier._resolve_goemotions_label_map(model), ['joy', 'sadness'])
        model.config.id2label = {0: 'LABEL_0'}
        self.assertIsNone(classifier._resolve_goemotions_label_map(model))
        model.config.id2label = {}
        self.assertIsNone(classifier._resolve_goemotions_label_map(model))

    def test_wb_clf_14_goemotions_scores_aggregate_into_emotune_labels(self, *_):
        scores = EmotionClassifier()._aggregate_goemotions_scores(
            {'joy': 0.3, 'amusement': 0.2, 'unknown': 0.9, 'grief': -1.0},
        )
        self.assertAlmostEqual(scores['happy'], 0.5)
        self.assertEqual(scores['sad'], 0.0)

    def test_wb_clf_15_prefer_goemotions_rules(self, *_):
        classifier = EmotionClassifier()
        self.assertFalse(classifier._should_prefer_goemotions_result(None))
        self.assertFalse(classifier._should_prefer_goemotions_result(
            {'emotion': 'mixed', 'confidence': 0.9}))
        self.assertTrue(classifier._should_prefer_goemotions_result(
            {'emotion': 'sad', 'confidence': 0.31, 'confidence_margin': 0}))
        self.assertTrue(classifier._should_prefer_goemotions_result(
            {'emotion': 'sad', 'confidence': 0.1, 'confidence_margin': 0.06}))
        self.assertFalse(classifier._should_prefer_goemotions_result(
            {'emotion': 'sad', 'confidence': 0.1, 'confidence_margin': 0.01}))

    def test_wb_clf_16_model_path_detection(self, *_):
        classifier = EmotionClassifier()
        self.assertTrue(classifier._looks_like_local_model_path('./models/x'))
        self.assertTrue(classifier._looks_like_local_model_path('/abs/path'))
        self.assertFalse(classifier._looks_like_local_model_path('org/model-id'))
        self.assertFalse(classifier._looks_like_local_model_path(''))
        self.assertEqual(classifier._resolve_model_source(''), (None, False))
        self.assertEqual(classifier._resolve_model_source('./missing-model'), (None, False))
        self.assertEqual(classifier._resolve_model_source('org/model-id'), ('org/model-id', False))
