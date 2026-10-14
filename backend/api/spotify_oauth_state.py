"""Signed state for the Spotify OAuth handshake.

The ``state`` parameter is the only thing tying a Spotify callback back to an
EmoTune account. It used to be the plain user id, which anyone can guess, so a
crafted callback URL could bind an attacker's Spotify account to somebody
else's EmoTune account (or the reverse). Signing it means the backend only
accepts a state it issued itself, to the user it issued it to.

Replay is covered by Spotify: the authorization code that arrives alongside the
state can only be exchanged once, so a re-sent callback fails at the token
exchange before anything is linked. The short lifetime keeps a leaked URL from
being useful later.
"""

import logging
import secrets

from django.conf import settings
from django.core import signing

logger = logging.getLogger('api.spotify_service')

# Namespaces the signature so a state token cannot be swapped in for some other
# signed value the project produces with the same SECRET_KEY.
STATE_SALT = 'emotune.spotify.oauth.state'

DEFAULT_STATE_MAX_AGE_SECONDS = 600


def state_max_age_seconds():
    """How long an issued state stays valid, in seconds."""
    return int(
        getattr(
            settings,
            'SPOTIFY_OAUTH_STATE_MAX_AGE_SECONDS',
            DEFAULT_STATE_MAX_AGE_SECONDS,
        )
        or DEFAULT_STATE_MAX_AGE_SECONDS
    )


def issue_state(user):
    """Return a signed state that identifies ``user`` for one login attempt."""
    return signing.dumps(
        {'uid': user.id, 'nonce': secrets.token_urlsafe(8)},
        salt=STATE_SALT,
    )


def read_state(state):
    """Return the user id carried by ``state``, or None when it is not ours.

    Never raises: a bad state is an untrusted caller, not a server fault, so
    the callers turn a None into a refusal to link the account.
    """
    state = str(state or '').strip()
    if not state:
        return None

    try:
        payload = signing.loads(
            state,
            salt=STATE_SALT,
            max_age=state_max_age_seconds(),
        )
    except signing.SignatureExpired:
        logger.warning("Spotify OAuth state rejected: expired")
        return None
    except signing.BadSignature:
        logger.warning("Spotify OAuth state rejected: bad signature")
        return None

    if not isinstance(payload, dict):
        logger.warning("Spotify OAuth state rejected: unexpected payload shape")
        return None

    user_id = payload.get('uid')
    if not isinstance(user_id, int):
        logger.warning("Spotify OAuth state rejected: missing user id")
        return None

    return user_id
