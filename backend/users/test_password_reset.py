"""The forgotten-password flow: request a code, verify it, set a new password."""

from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework.throttling import SimpleRateThrottle

from .models import PasswordResetCode


User = get_user_model()

REQUEST_URL = '/api/users/password-reset/'
VERIFY_URL = '/api/users/password-reset/verify/'
CONFIRM_URL = '/api/users/password-reset/confirm/'


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class PasswordResetTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        # The reset endpoints are throttled per IP and per email, and the cache
        # outlives a single test method.
        cache.clear()
        self.addCleanup(cache.clear)
        self.user = User.objects.create_user(
            username='Robin',
            email='robin@example.com',
            password='original-pass',
        )

    def _request_code(self, email='robin@example.com'):
        response = self.client.post(REQUEST_URL, {'email': email}, format='json')
        self.assertEqual(response.status_code, 200)
        return response

    def _issued_code(self):
        """Pull the plaintext code back out of the sent mail."""
        body = mail.outbox[-1].body
        digits = [word for word in body.split() if word.isdigit() and len(word) == 6]
        self.assertEqual(len(digits), 1, f'expected one code in: {body!r}')
        return digits[0]

    def test_request_emails_a_six_digit_code_and_stores_only_its_hash(self):
        self._request_code()

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['robin@example.com'])
        code = self._issued_code()

        record = PasswordResetCode.objects.get(user=self.user)
        self.assertNotIn(code, record.code_hash)
        self.assertTrue(record.matches(code))

    def test_request_for_an_unknown_address_is_indistinguishable(self):
        known = self._request_code()
        cache.clear()
        unknown = self.client.post(
            REQUEST_URL, {'email': 'nobody@example.com'}, format='json'
        )

        self.assertEqual(unknown.status_code, 200)
        self.assertEqual(unknown.json()['message'], known.json()['message'])
        # Only the real account got mail.
        self.assertEqual(len(mail.outbox), 1)

    def test_verify_accepts_the_code_without_spending_it(self):
        self._request_code()
        code = self._issued_code()

        verify = self.client.post(
            VERIFY_URL,
            {'email': 'robin@example.com', 'code': code},
            format='json',
        )
        self.assertEqual(verify.status_code, 200)
        self.assertTrue(verify.json()['valid'])

        # The same code still has to work for the confirm step.
        confirm = self.client.post(
            CONFIRM_URL,
            {
                'email': 'robin@example.com',
                'code': code,
                'new_password': 'brand-new-pass',
                'confirm_new_password': 'brand-new-pass',
            },
            format='json',
        )
        self.assertEqual(confirm.status_code, 200)

    def test_confirm_refuses_a_weak_password_and_keeps_the_code(self):
        self._request_code()
        code = self._issued_code()

        response = self.client.post(
            CONFIRM_URL,
            {'email': 'robin@example.com', 'code': code, 'new_password': 'password', 'confirm_new_password': 'password'},
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('This password is too common.', response.json()['new_password'])
        self.assertTrue(PasswordResetCode.objects.get(user=self.user).is_usable)
        self.assertTrue(User.objects.get(pk=self.user.pk).check_password('original-pass'))

    def test_similarity_error_does_not_reveal_whether_the_email_has_an_account(self):
        def confirm(email, password):
            return self.client.post(
                CONFIRM_URL,
                {'email': email, 'code': '000000', 'new_password': password, 'confirm_new_password': password},
                format='json',
            ).json()

        # robin@example.com has an account, nobod@example.com does not. Both
        # passwords echo their own address; the answer must not differ.
        existing = confirm('robin@example.com', 'robin-example')
        missing = confirm('nobod@example.com', 'nobod-example')
        self.assertEqual(existing, missing)
        self.assertIn('The password is too similar to the email.', existing['new_password'])

    def test_confirm_sets_the_password_and_burns_the_code(self):
        self._request_code()
        code = self._issued_code()

        response = self.client.post(
            CONFIRM_URL,
            {
                'email': 'robin@example.com',
                'code': code,
                'new_password': 'brand-new-pass',
                'confirm_new_password': 'brand-new-pass',
            },
            format='json',
        )
        self.assertEqual(response.status_code, 200)

        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('brand-new-pass'))
        self.assertFalse(self.user.check_password('original-pass'))

        record = PasswordResetCode.objects.get(user=self.user)
        self.assertIsNotNone(record.used_at)

        # Replaying it must not work a second time.
        replay = self.client.post(
            CONFIRM_URL,
            {
                'email': 'robin@example.com',
                'code': code,
                'new_password': 'third-pass',
                'confirm_new_password': 'third-pass',
            },
            format='json',
        )
        self.assertEqual(replay.status_code, 400)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('brand-new-pass'))

    def test_confirm_rejects_mismatched_new_passwords(self):
        self._request_code()
        code = self._issued_code()

        response = self.client.post(
            CONFIRM_URL,
            {
                'email': 'robin@example.com',
                'code': code,
                'new_password': 'brand-new-pass',
                'confirm_new_password': 'something-else',
            },
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('original-pass'))

    def test_wrong_code_counts_down_and_then_locks_the_code_out(self):
        self._request_code()
        real_code = self._issued_code()

        wrong = '000000' if real_code != '000000' else '111111'
        for expected_remaining in range(PasswordResetCode.MAX_ATTEMPTS - 1, 0, -1):
            response = self.client.post(
                VERIFY_URL,
                {'email': 'robin@example.com', 'code': wrong},
                format='json',
            )
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.json()['attempts_remaining'], expected_remaining)

        # The last wrong guess exhausts the budget...
        response = self.client.post(
            VERIFY_URL, {'email': 'robin@example.com', 'code': wrong}, format='json'
        )
        self.assertEqual(response.status_code, 400)

        # ...and the real code is dead along with it.
        response = self.client.post(
            VERIFY_URL, {'email': 'robin@example.com', 'code': real_code}, format='json'
        )
        self.assertEqual(response.status_code, 400)

    def test_expired_code_is_refused(self):
        self._request_code()
        code = self._issued_code()

        record = PasswordResetCode.objects.get(user=self.user)
        record.expires_at = timezone.now() - timedelta(seconds=1)
        record.save(update_fields=['expires_at'])

        response = self.client.post(
            VERIFY_URL, {'email': 'robin@example.com', 'code': code}, format='json'
        )
        self.assertEqual(response.status_code, 400)

    def test_requesting_again_invalidates_the_previous_code(self):
        self._request_code()
        first_code = self._issued_code()

        self._request_code()
        second_code = self._issued_code()
        self.assertNotEqual(first_code, second_code)

        self.assertEqual(PasswordResetCode.objects.filter(user=self.user).count(), 1)

        stale = self.client.post(
            VERIFY_URL, {'email': 'robin@example.com', 'code': first_code}, format='json'
        )
        self.assertEqual(stale.status_code, 400)

        fresh = self.client.post(
            VERIFY_URL, {'email': 'robin@example.com', 'code': second_code}, format='json'
        )
        self.assertEqual(fresh.status_code, 200)

    def test_repeated_requests_for_one_address_are_throttled(self):
        # Pinned: the default rate is looser when DJANGO_DEBUG is on. DRF reads
        # the rates at import, so the shared dict is what has to be patched.
        limit = 6
        rates = patch.dict(SimpleRateThrottle.THROTTLE_RATES, {'password_reset_email': f'{limit}/hour'})
        rates.start()
        self.addCleanup(rates.stop)
        for _ in range(limit):
            self.client.post(REQUEST_URL, {'email': 'robin@example.com'}, format='json')

        response = self.client.post(
            REQUEST_URL, {'email': 'robin@example.com'}, format='json'
        )
        self.assertEqual(response.status_code, 429)
