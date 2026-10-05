"""Tests for the LLM search plan wired into candidate retrieval.

The contract these pin down is that the plan is additive: when it cannot
produce queries -- disabled, unconfigured, erroring, malformed -- retrieval
must be left exactly as it was before the LLM existed.
"""
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from api.views import _build_llm_search_plan


CONFIGURED = {
    'LLM_MUSIC_PICKER_ENABLED': True,
    'LLM_MUSIC_PICKER_PROVIDER': 'gemini',
    'LLM_MUSIC_PICKER_API_KEY': 'test-key',
    'LLM_MUSIC_PICKER_MODEL': 'test-model',
}


def _plan(**overrides):
    return _build_llm_search_plan(
        prompt_text=overrides.pop('prompt_text', 'my dog died last week'),
        emotion=overrides.pop('emotion', 'sad'),
        top_emotions=overrides.pop('top_emotions', [{'emotion': 'sad', 'confidence': 0.8}]),
        all_scores=overrides.pop('all_scores', {'sad': 0.8}),
        confidence_band=overrides.pop('confidence_band', 'high'),
        confidence_margin=overrides.pop('confidence_margin', 0.3),
        preferred_artists=overrides.pop('preferred_artists', []),
        **overrides,
    )


class LLMSearchPlanTests(SimpleTestCase):
    @override_settings(LLM_MUSIC_PICKER_ENABLED=False)
    def test_disabled_contributes_nothing_and_makes_no_call(self):
        with patch('api.views.LLMMusicPicker.build_search_plan') as mock_plan:
            result = _plan()

        mock_plan.assert_not_called()
        self.assertFalse(result['used'])
        self.assertEqual(result['search_queries'], [])
        self.assertIsNone(result['playlist_category'])

    @override_settings(**CONFIGURED)
    def test_initial_stage_is_skipped_so_first_track_stays_fast(self):
        with patch('api.views.LLMMusicPicker.build_search_plan') as mock_plan:
            result = _plan(skip=True)

        mock_plan.assert_not_called()
        self.assertFalse(result['used'])

    @override_settings(**CONFIGURED)
    def test_empty_prompt_is_skipped(self):
        with patch('api.views.LLMMusicPicker.build_search_plan') as mock_plan:
            result = _plan(prompt_text='   ')

        mock_plan.assert_not_called()
        self.assertFalse(result['used'])

    @override_settings(**CONFIGURED)
    def test_successful_plan_returns_normalized_queries(self):
        with patch(
            'api.views.LLMMusicPicker.build_search_plan',
            return_value={
                'ok': True,
                'strategy': 'llm_search_plan',
                'search_queries': ['  grief   ballads ', 'quiet piano for loss', ''],
                'playlist_category': ' gentle grieving ',
                'reason': 'The prompt describes a bereavement.',
                'provider': 'gemini',
                'model': 'test-model',
                'confidence': 0.71,
                'error': None,
            },
        ):
            result = _plan()

        self.assertTrue(result['used'])
        self.assertEqual(
            result['search_queries'],
            ['grief ballads', 'quiet piano for loss'],
        )
        self.assertEqual(result['playlist_category'], 'gentle grieving')
        self.assertEqual(result['provider'], 'gemini')
        self.assertEqual(result['confidence'], 0.71)
        self.assertIsNone(result['error'])

    @override_settings(**CONFIGURED)
    def test_unsuccessful_plan_keeps_its_error_but_adds_no_queries(self):
        # build_search_plan returns ok=False with its own heuristic queries in
        # place; those are discarded rather than merged into retrieval.
        with patch(
            'api.views.LLMMusicPicker.build_search_plan',
            return_value={
                'ok': False,
                'search_queries': ['sad', 'sad songs', 'sad playlist'],
                'error': 'llm_search_plan_http_429',
            },
        ):
            result = _plan()

        self.assertFalse(result['used'])
        self.assertEqual(result['search_queries'], [])
        self.assertEqual(result['error'], 'llm_search_plan_http_429')

    @override_settings(**CONFIGURED)
    def test_exception_is_swallowed_so_retrieval_survives(self):
        with patch(
            'api.views.LLMMusicPicker.build_search_plan',
            side_effect=RuntimeError('boom'),
        ):
            result = _plan()

        self.assertFalse(result['used'])
        self.assertEqual(result['search_queries'], [])

    @override_settings(**CONFIGURED)
    def test_plan_returning_only_blank_queries_is_treated_as_unusable(self):
        with patch(
            'api.views.LLMMusicPicker.build_search_plan',
            return_value={'ok': True, 'search_queries': ['  ', ''], 'error': None},
        ):
            result = _plan()

        self.assertFalse(result['used'])
        self.assertEqual(result['search_queries'], [])
        self.assertEqual(result['error'], 'llm_search_plan_missing_queries')

    @override_settings(
        LLM_MUSIC_PICKER_ENABLED=True,
        LLM_MUSIC_PICKER_PROVIDER='gemini',
        LLM_MUSIC_PICKER_API_KEY='',
        LLM_MUSIC_PICKER_MODEL='test-model',
    )
    def test_enabled_without_a_key_is_not_configured(self):
        with patch('api.views.LLMMusicPicker.build_search_plan') as mock_plan:
            result = _plan()

        mock_plan.assert_not_called()
        self.assertFalse(result['used'])
