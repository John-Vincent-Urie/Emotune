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


class EmailScopedThrottle(SimpleRateThrottle):
    """Rate limit keyed on the submitted email rather than the caller's IP.

    Subclasses only need to set a scope. Attributing the attempt to the account
    being targeted is what stops a distributed attack on one mailbox.
    """

    def get_cache_key(self, request, view):
        email = request.data.get('email') if hasattr(request, 'data') else None
        email = str(email or '').strip().lower()
        if not email:
            # Nothing to attribute the attempt to; the IP throttle still covers it.
            return None
        return self.cache_format % {'scope': self.scope, 'ident': email}


class LoginEmailThrottle(EmailScopedThrottle):
    """Cap login attempts against a single account, whatever the source IP."""

    scope = 'login_email'


class RegisterThrottle(AnonRateThrottle):
    """Keep one client from mass-creating accounts."""

    scope = 'register'


class PasswordChangeThrottle(UserRateThrottle):
    """Limit old-password guesses on an already authenticated session."""

    scope = 'password_change'


class PasswordResetIPThrottle(AnonRateThrottle):
    """Keep one client from spraying reset codes at many addresses."""

    scope = 'password_reset_ip'


class PasswordResetEmailThrottle(EmailScopedThrottle):
    """Cap how often one address can be mailed a code -- anti mail-bomb."""

    scope = 'password_reset_email'


# Entering a code is scoped separately from asking for one. Sharing a bucket
# means a user who mistypes their code burns the budget that lets them request
# a replacement, and the two actions deserve very different rates: a handful of
# mails an hour, but enough guesses to spend the code's own attempt budget.
class PasswordResetVerifyIPThrottle(AnonRateThrottle):
    """Cap code submissions from a single client address."""

    scope = 'password_reset_verify_ip'


class PasswordResetVerifyEmailThrottle(EmailScopedThrottle):
    """Cap code submissions against a single account, whatever the source IP."""

    scope = 'password_reset_verify_email'
