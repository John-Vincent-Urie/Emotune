"""Checks on the deployment-hardening settings.

The values that matter here only take effect when DEBUG is false, which is
never how the test suite runs, so these load settings.py in isolation with a
production-shaped environment and read the result. load_env_file only fills in
keys that are not already set, so the patched environment wins over any real
.env on the machine.
"""

import importlib.util
import os
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.test import SimpleTestCase

SETTINGS_PATH = Path(__file__).resolve().parent / 'settings.py'


BASE_DIR = SETTINGS_PATH.parent.parent
DOTENV_PATHS = {BASE_DIR.parent / '.env', BASE_DIR / '.env'}


def load_settings(**env):
    """Import settings.py as a throwaway module under the given environment.

    The .env files are hidden from the probe so it reads settings.py's own
    defaults rather than whatever the developer's machine happens to pin --
    unsetting the variables is not enough, since load_env_file would just read
    them back off disk.
    """
    real_exists = Path.exists

    def exists_ignoring_dotenv(self):
        if self in DOTENV_PATHS:
            return False
        return real_exists(self)

    spec = importlib.util.spec_from_file_location('emotune_settings_probe', SETTINGS_PATH)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(os.environ, env, clear=True):
        with patch.object(Path, 'exists', exists_ignoring_dotenv):
            spec.loader.exec_module(module)
    return module


PRODUCTION_ENV = {
    'DJANGO_DEBUG': 'false',
    'DJANGO_SECRET_KEY': 'a-secret-key-for-the-probe',
}


class ProductionSecuritySettingsTests(SimpleTestCase):
    def test_debug_false_turns_on_transport_hardening(self):
        probe = load_settings(**PRODUCTION_ENV)

        self.assertFalse(probe.DEBUG)
        self.assertTrue(probe.SECURE_SSL_REDIRECT)
        self.assertTrue(probe.SESSION_COOKIE_SECURE)
        self.assertTrue(probe.CSRF_COOKIE_SECURE)
        self.assertEqual(probe.SECURE_HSTS_SECONDS, 31536000)
        self.assertTrue(probe.SECURE_HSTS_INCLUDE_SUBDOMAINS)

    def test_debug_false_does_not_open_cors_to_everyone(self):
        probe = load_settings(**PRODUCTION_ENV)

        self.assertFalse(probe.CORS_ALLOW_ALL_ORIGINS)
        # Allow-all plus credentials is the combination that lets any site read
        # authenticated responses, so credentials stay off by default.
        self.assertFalse(probe.CORS_ALLOW_CREDENTIALS)

    def test_local_development_is_left_alone(self):
        probe = load_settings(DJANGO_DEBUG='true')

        self.assertTrue(probe.DEBUG)
        self.assertFalse(probe.SECURE_SSL_REDIRECT)
        self.assertFalse(probe.SESSION_COOKIE_SECURE)
        self.assertEqual(probe.SECURE_HSTS_SECONDS, 0)
        self.assertTrue(probe.CORS_ALLOW_ALL_ORIGINS)

    def test_proxy_ssl_header_is_not_trusted_unless_asked_for(self):
        """Trusting X-Forwarded-Proto with no proxy lets a client fake HTTPS."""
        probe = load_settings(**PRODUCTION_ENV)
        self.assertFalse(hasattr(probe, 'SECURE_PROXY_SSL_HEADER'))

        trusted = load_settings(**PRODUCTION_ENV, DJANGO_TRUST_PROXY_SSL_HEADER='true')
        self.assertEqual(
            trusted.SECURE_PROXY_SSL_HEADER,
            ('HTTP_X_FORWARDED_PROTO', 'https'),
        )

    def test_open_cors_with_credentials_refuses_to_start_in_production(self):
        """A development .env carried into production must not boot silently."""
        from django.core.exceptions import ImproperlyConfigured

        with self.assertRaises(ImproperlyConfigured):
            load_settings(
                **PRODUCTION_ENV,
                DJANGO_CORS_ALLOW_ALL_ORIGINS='true',
                DJANGO_CORS_ALLOW_CREDENTIALS='true',
            )

    def test_secret_key_is_required_once_debug_is_off(self):
        from django.core.exceptions import ImproperlyConfigured

        with self.assertRaises(ImproperlyConfigured):
            load_settings(DJANGO_DEBUG='false', DJANGO_SECRET_KEY='')


class AlwaysOnSecuritySettingsTests(SimpleTestCase):
    """Settings that should hold in every environment, including this one."""

    def test_cookies_are_hidden_from_javascript(self):
        self.assertTrue(settings.SESSION_COOKIE_HTTPONLY)
        self.assertTrue(settings.CSRF_COOKIE_HTTPONLY)
        self.assertEqual(settings.SESSION_COOKIE_SAMESITE, 'Lax')

    def test_framing_and_sniffing_are_refused(self):
        self.assertEqual(settings.X_FRAME_OPTIONS, 'DENY')
        self.assertTrue(settings.SECURE_CONTENT_TYPE_NOSNIFF)
        self.assertEqual(settings.SECURE_REFERRER_POLICY, 'same-origin')
