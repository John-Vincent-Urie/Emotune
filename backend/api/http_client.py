"""
Pooled HTTP transport for EmoTune's outbound calls (Spotify, the LLM picker).

These calls used to go through the module-level `requests.post` /
`requests.request` helpers. Those build a throwaway `Session` per call, so each
one paid a fresh TCP connect plus a TLS handshake -- and a single pool refresh
makes on the order of 500 calls (see `SpotifyAuthClient._spotify_request`).
Keeping one `Session` alive lets urllib3 reuse the existing keep-alive
connection to the host instead.

The session is thread-local on purpose. `requests.Session` is not documented as
thread-safe, and the recommendation search fans queries out across a thread
pool, so each worker thread gets its own session and its own connection pool.
Pool threads are long-lived, so connections are still reused across requests.

Call `post` / `get` / `request` here rather than reaching for the session
directly: the test suite patches these module-level names, the same way it used
to patch `api.spotify_service.requests.post`.
"""
import threading

import requests
from requests.adapters import HTTPAdapter

#: Matches the default recommendation fan-out plus headroom for the pool
#: refresh command, which is the heaviest caller.
_POOL_CONNECTIONS = 10
_POOL_MAXSIZE = 20

_local = threading.local()


def get_session():
    """Return this thread's pooled session, building it on first use."""
    session = getattr(_local, 'session', None)
    if session is None:
        session = requests.Session()
        # Retries stay off: callers already classify upstream failures and
        # enforce their own time budgets, so a silent retry here would spend a
        # request's deadline without the caller ever seeing the first failure.
        adapter = HTTPAdapter(
            pool_connections=_POOL_CONNECTIONS,
            pool_maxsize=_POOL_MAXSIZE,
            max_retries=0,
        )
        session.mount('https://', adapter)
        session.mount('http://', adapter)
        _local.session = session
    return session


def request(method, url, **kwargs):
    return get_session().request(method, url, **kwargs)


def post(url, **kwargs):
    return get_session().post(url, **kwargs)


def get(url, **kwargs):
    return get_session().get(url, **kwargs)
