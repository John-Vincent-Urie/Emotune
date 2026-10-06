from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework.throttling import SimpleRateThrottle


User = get_user_model()


class RegistrationTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_register_stores_terms_acceptance_and_personalization_preference(self):
        response = self.client.post(
            '/api/users/register/',
            {
                'username': 'Avery',
                'email': 'avery@example.com',
                'password': 'password123',
                'confirm_password': 'password123',
                'accept_terms': True,
                'personalization_opt_in': False,
            },
            format='json',
        )

        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body['user']['username'], 'Avery')
        self.assertFalse(body['user']['personalization_opt_in'])
        self.assertIsNotNone(body['user']['terms_accepted_at'])

        user = User.objects.get(email='avery@example.com')
        self.assertFalse(user.personalization_opt_in)
        self.assertIsNotNone(user.terms_accepted_at)

    def _register(self, display_name, email):
        return self.client.post(
            '/api/users/register/',
            {
                'username': display_name,
                'email': email,
                'password': 'password123',
                'confirm_password': 'password123',
                'accept_terms': True,
            },
            format='json',
        )

    def test_display_name_may_contain_spaces(self):
        response = self._register('  QA Tester  ', 'qa@example.com')

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()['user']['username'], 'QA Tester')
        self.assertEqual(User.objects.get(email='qa@example.com').username, 'QA Tester')

    def test_two_people_can_share_a_display_name(self):
        self.assertEqual(self._register('Maria', 'maria1@example.com').status_code, 201)
        self.assertEqual(self._register('Maria', 'maria2@example.com').status_code, 201)

    def test_same_email_in_other_case_is_a_clean_400_not_a_500(self):
        self.assertEqual(self._register('Avery', 'avery@example.com').status_code, 201)

        response = self._register('Avery Two', 'Avery@Example.com')

        self.assertEqual(response.status_code, 400)
        self.assertIn('email', response.json())
        self.assertEqual(User.objects.filter(email__iexact='avery@example.com').count(), 1)

    def test_login_ignores_email_case_and_surrounding_spaces(self):
        self._register('QA', 'qa.e1@example.com')
        # Phone keyboards capitalize the first letter; other clients may not trim.
        for typed in ['qa.e1@example.com', 'QA.e1@example.com', 'Qa.e1@Example.com', ' qa.e1@example.com ']:
            with self.subTest(email=typed):
                response = self.client.post(
                    '/api/users/login/', {'email': typed, 'password': 'password123'}, format='json',
                )
                self.assertEqual(response.status_code, 200)

    def test_login_finds_a_mixed_case_account_made_outside_register(self):
        # createsuperuser and the admin store the address as typed.
        User.objects.create_user(username='Admin', email='Admin@Example.com', password='password123')

        response = self.client.post(
            '/api/users/login/', {'email': 'admin@example.com', 'password': 'password123'}, format='json',
        )

        self.assertEqual(response.status_code, 200)

    def test_login_with_wrong_password_still_fails_in_any_case(self):
        self._register('QA', 'qa.e1@example.com')

        response = self.client.post(
            '/api/users/login/', {'email': 'QA.E1@EXAMPLE.COM', 'password': 'wrong-password'}, format='json',
        )

        self.assertEqual(response.status_code, 401)

    def test_register_requires_terms_acceptance(self):
        response = self.client.post(
            '/api/users/register/',
            {
                'username': 'Jordan',
                'email': 'jordan@example.com',
                'password': 'password123',
                'confirm_password': 'password123',
                'accept_terms': False,
                'personalization_opt_in': True,
            },
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('accept_terms', response.json())
        self.assertFalse(User.objects.filter(email='jordan@example.com').exists())


class LogoutTests(TestCase):
    """Signing out has to revoke the refresh token, not just forget it."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='logout-user',
            email='logout@example.com',
            password='correct-horse-battery',
        )

    def issue_tokens(self):
        response = self.client.post(
            '/api/users/login/',
            {'email': 'logout@example.com', 'password': 'correct-horse-battery'},
            format='json',
        )
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_logout_makes_the_refresh_token_unusable(self):
        refresh = self.issue_tokens()['refresh']
        # Sanity check: the token works before logging out.
        self.assertEqual(
            self.client.post(
                '/api/users/token/refresh/', {'refresh': refresh}, format='json'
            ).status_code,
            200,
        )

        logout = self.client.post('/api/users/logout/', {'refresh': refresh}, format='json')

        self.assertEqual(logout.status_code, 205)
        self.assertEqual(
            self.client.post(
                '/api/users/token/refresh/', {'refresh': refresh}, format='json'
            ).status_code,
            401,
        )

    def test_logout_requires_a_refresh_token(self):
        response = self.client.post('/api/users/logout/', {}, format='json')

        self.assertEqual(response.status_code, 400)

    def test_logout_accepts_an_already_dead_token(self):
        """Repeat sign-outs should not error; the session is gone either way."""
        refresh = self.issue_tokens()['refresh']
        self.client.post('/api/users/logout/', {'refresh': refresh}, format='json')

        again = self.client.post('/api/users/logout/', {'refresh': refresh}, format='json')

        self.assertEqual(again.status_code, 205)

    def test_logout_works_without_a_live_access_token(self):
        """An expired access token must not trap a user in a live session."""
        refresh = self.issue_tokens()['refresh']

        response = APIClient().post(
            '/api/users/logout/', {'refresh': refresh}, format='json'
        )

        self.assertEqual(response.status_code, 205)


class CredentialThrottleTests(TestCase):
    """The credential endpoints must stop answering once a client hammers them."""

    def setUp(self):
        self.client = APIClient()
        # DRF reads DEFAULT_THROTTLE_RATES into SimpleRateThrottle.THROTTLE_RATES
        # at import time, so override_settings cannot lower the limits here;
        # patching the shared dict is what actually takes effect.
        rates = patch.dict(
            SimpleRateThrottle.THROTTLE_RATES,
            {
                'login_ip': '5/min',
                'login_email': '2/min',
                'register': '2/min',
                'password_change': '2/min',
            },
        )
        rates.start()
        self.addCleanup(rates.stop)
        # Throttle history lives in the default cache, so it would otherwise
        # carry over between tests and make them order dependent.
        cache.clear()
        self.addCleanup(cache.clear)
        self.user = User.objects.create_user(
            username='throttled',
            email='throttled@example.com',
            password='correct-horse-battery',
        )

    def _login(self, email='throttled@example.com', password='wrong-password'):
        return self.client.post(
            '/api/users/login/',
            {'email': email, 'password': password},
            format='json',
        )

    def test_repeated_failed_logins_for_one_account_are_throttled(self):
        for _ in range(2):
            self.assertEqual(self._login().status_code, 401)
        self.assertEqual(self._login().status_code, 429)

    def test_login_throttle_is_scoped_to_the_submitted_email(self):
        for _ in range(2):
            self._login()
        self.assertEqual(self._login().status_code, 429)
        # A different account is still reachable from the same client until the
        # per-IP limit (5/min here) is reached.
        other = self._login(email='someone-else@example.com')
        self.assertEqual(other.status_code, 401)

    def test_faked_forwarded_for_does_not_dodge_the_ip_throttle(self):
        # With DRF's default NUM_PROXIES (None) every request below would count
        # as a new client. settings pins it to 0: the socket address decides.
        for index in range(5):
            response = self.client.post(
                '/api/users/register/',
                {
                    'username': f'spoof{index}',
                    'email': f'spoof{index}@example.com',
                    'password': 'correct-horse-battery',
                    'confirm_password': 'correct-horse-battery',
                    'accept_terms': True,
                },
                format='json',
                HTTP_X_FORWARDED_FOR=f'203.0.113.{index}',
            )
            if index < 2:
                self.assertEqual(response.status_code, 201)
        self.assertEqual(response.status_code, 429)

    def test_registration_is_throttled(self):
        def signup(name):
            return self.client.post(
                '/api/users/register/',
                {
                    'username': name,
                    'email': f'{name}@example.com',
                    'password': 'correct-horse-battery',
                    'confirm_password': 'correct-horse-battery',
                    'accept_terms': True,
                },
                format='json',
            )

        for index in range(2):
            self.assertEqual(signup(f'signup{index}').status_code, 201)
        self.assertEqual(signup('signup-blocked').status_code, 429)

    def test_password_change_guessing_is_throttled(self):
        self.client.force_authenticate(user=self.user)
        payload = {'old_password': 'nope', 'new_password': 'another-strong-pass'}
        for _ in range(2):
            self.assertEqual(
                self.client.post('/api/users/change-password/', payload, format='json').status_code,
                400,
            )
        self.assertEqual(
            self.client.post('/api/users/change-password/', payload, format='json').status_code,
            429,
        )
