"""Rate limits for the credential endpoints.

Registration, login and password change are the endpoints an attacker can
attack with nothing but a network connection, so they get their own throttle
scopes (rates live in REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']).

Login is limited twice on purpose: by IP, which stops one machine grinding
through a password list, and by the submitted email, which stops the same
account being attacked from many IPs at once.
"""

from rest_framework.throttling import AnonRateThrottle, SimpleRateThrottle, UserRateThrottle


class LoginIPThrottle(AnonRateThrottle):
    """Cap login attempts coming from a single client address."""

    scope = 'login_ip'


class LoginEmailThrottle(SimpleRateThrottle):
    """Cap login attempts against a single account, whatever the source IP."""

    scope = 'login_email'

    def get_cache_key(self, request, view):
        email = request.data.get('email') if hasattr(request, 'data') else None
        email = str(email or '').strip().lower()
        if not email:
            # Nothing to attribute the attempt to; LoginIPThrottle still covers it.
            return None
        return self.cache_format % {'scope': self.scope, 'ident': email}


class RegisterThrottle(AnonRateThrottle):
    """Keep one client from mass-creating accounts."""

    scope = 'register'


class PasswordChangeThrottle(UserRateThrottle):
    """Limit old-password guesses on an already authenticated session."""

    scope = 'password_change'
