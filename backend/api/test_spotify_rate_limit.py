"""A Spotify 429 pauses every Spotify call in the process until Retry-After ends.

Without this, one QA run against /api/analyze/ kept calling Spotify through
~1,450 429s on the dev credentials. See api/spotify/rate_limit.py.
"""
from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from api.spotify import rate_limit
from api.spotify_service import spotify_service


def _response(status_code, *, retry_after=None, body=None):
    body = body if body is not None else {'tracks': {'items': []}}
    response = Mock()
    response.status_code = status_code
    response.json.return_value = body
    response.text = '{"error": {"status": 429}}' if status_code == 429 else '{}'
    response.headers = {'Retry-After': str(retry_after)} if retry_after is not None else {}
    return response


class SpotifyRateLimitCooldownTests(SimpleTestCase):
    def setUp(self):
        rate_limit.reset()
        self.addCleanup(rate_limit.reset)
        self.clock = 1000.0
        patcher = patch.object(rate_limit.time, 'monotonic', side_effect=lambda: self.clock)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _call(self):
        return spotify_service._spotify_request('GET', 'token', '/search', params={'q': 'x'})

    def test_a_429_stops_further_spotify_calls_until_retry_after_passes(self):
        with patch('api.http_client.request', return_value=_response(429, retry_after=120)) as http:
            first = self._call()
            second = self._call()
            third = self._call()

        self.assertEqual(http.call_count, 1)
        self.assertEqual(first['reason'], 'rate_limited')
        self.assertEqual(first['retry_after'], 120)
        for skipped in (second, third):
            self.assertEqual(skipped['reason'], 'rate_limited')
            self.assertTrue(skipped['skipped_during_cooldown'])
            self.assertEqual(skipped['retry_after'], 120)

        self.clock += 121
        with patch('api.http_client.request', return_value=_response(200)) as http:
            resumed = self._call()
        self.assertTrue(resumed['ok'])
        http.assert_called_once()

    def test_remaining_wait_is_reported_as_retry_after(self):
        with patch('api.http_client.request', return_value=_response(429, retry_after=60)):
            self._call()
        self.clock += 45

        with patch('api.http_client.request') as http:
            skipped = self._call()

        http.assert_not_called()
        self.assertEqual(skipped['retry_after'], 15)

    def test_missing_retry_after_uses_the_default_window(self):
        with patch('api.http_client.request', return_value=_response(429)):
            self._call()

        self.clock += rate_limit.DEFAULT_COOLDOWN_SECONDS - 1
        with patch('api.http_client.request') as http:
            self._call()
        http.assert_not_called()

        self.clock += 2
        with patch('api.http_client.request', return_value=_response(200)) as http:
            self._call()
        http.assert_called_once()

    def test_cooldown_is_logged_once_not_per_request(self):
        with self.assertLogs('api.spotify.rate_limit', level='INFO') as logs:
            with patch('api.http_client.request', return_value=_response(429, retry_after=30)):
                for _ in range(5):
                    self._call()
            # Concurrent searches that were already in flight can each bring
            # back their own 429; they extend the block without a new warning.
            rate_limit.start_cooldown(40)
            self.clock += 41
            with patch('api.http_client.request', return_value=_response(200)):
                self._call()
                self._call()

        warnings = [r for r in logs.records if r.levelname == 'WARNING']
        resumes = [r for r in logs.records if 'over' in r.getMessage()]
        self.assertEqual(len(warnings), 1)
        self.assertEqual(len(resumes), 1)

    def test_search_falls_back_without_calling_spotify_during_cooldown(self):
        rate_limit.start_cooldown(300)

        with patch('api.http_client.request') as http:
            result = spotify_service.search_tracks_detailed('calm piano', 'token', limit=5)

        http.assert_not_called()
        self.assertFalse(result['ok'])
        self.assertEqual(result['reason'], 'rate_limited')
        self.assertEqual(spotify_service.upstream_http_status(result), 503)

    def test_an_absurd_retry_after_is_capped(self):
        rate_limit.start_cooldown(10 ** 9)
        self.assertLessEqual(rate_limit.remaining_seconds(), rate_limit.MAX_COOLDOWN_SECONDS)
