"""
EmoTune Django Settings
"""
import os
from pathlib import Path
from datetime import timedelta
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BASE_DIR.parent

def load_env_file(path):
    env_path = Path(path)
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding='utf-8').splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


load_env_file(PROJECT_ROOT / '.env')
load_env_file(BASE_DIR / '.env')


def env_bool(name, default=False):
    value = os.getenv(name)
    if value is None:
        return default
    return str(value).strip().lower() in {'1', 'true', 'yes', 'on'}


def env_list(name, default=None):
    value = os.getenv(name)
    if value is None:
        return list(default or [])
    return [item.strip() for item in value.split(',') if item.strip()]


def env_float(name, default):
    value = os.getenv(name)
    if value is None:
        return float(default)
    try:
        return float(value)
    except ValueError:
        return float(default)


def env_int(name, default):
    value = os.getenv(name)
    if value is None:
        return int(default)
    try:
        return int(value)
    except ValueError:
        return int(default)

DEBUG = env_bool('DJANGO_DEBUG', True)

SECRET_KEY = os.getenv('DJANGO_SECRET_KEY')
if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = 'dev-only-secret-change-me'
    else:
        raise ImproperlyConfigured('DJANGO_SECRET_KEY must be set when DEBUG is false.')

ALLOWED_HOSTS = env_list(
    'DJANGO_ALLOWED_HOSTS',
    ['127.0.0.1', 'localhost'],
)

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',
    'corsheaders',
    'channels',
    'api',
    'users',
    'ml',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'emotune_project.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'emotune_project.wsgi.application'
ASGI_APPLICATION = 'emotune_project.asgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

AUTH_USER_MODEL = 'users.User'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Manila'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Email -- used by the forgotten-password code in users/emails.py.
#
# For Gmail, EMAIL_HOST_USER is the full address and EMAIL_HOST_PASSWORD must be
# a 16-character App Password (Google Account > Security > 2-Step Verification >
# App passwords). Gmail's SMTP refuses a normal account password outright.
EMAIL_HOST = os.getenv('EMAIL_HOST', 'smtp.gmail.com')
EMAIL_PORT = env_int('EMAIL_PORT', 587)
EMAIL_USE_TLS = env_bool('EMAIL_USE_TLS', True)
EMAIL_USE_SSL = env_bool('EMAIL_USE_SSL', False)
EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD', '')
# A hung SMTP connection would otherwise hold a request worker open.
EMAIL_TIMEOUT = env_int('EMAIL_TIMEOUT', 10)
DEFAULT_FROM_EMAIL = (
    os.getenv('DEFAULT_FROM_EMAIL')
    or (f'EmoTune <{EMAIL_HOST_USER}>' if EMAIL_HOST_USER else 'EmoTune <no-reply@emotune.local>')
)

# With no credentials there is nothing to authenticate with, so print the mail
# to the console instead. The reset flow then still works end to end offline --
# the code shows up in the runserver log.
EMAIL_BACKEND = os.getenv('DJANGO_EMAIL_BACKEND') or (
    'django.core.mail.backends.smtp.EmailBackend'
    if EMAIL_HOST_USER
    else 'django.core.mail.backends.console.EmailBackend'
)


REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    # Credential endpoints are the ones worth rate limiting: without this a
    # client can guess passwords against /api/users/login/ as fast as the
    # network allows. Scopes are applied by the throttles in users/throttles.py.
    'DEFAULT_THROTTLE_RATES': {
        'login_ip': os.getenv('THROTTLE_LOGIN_IP', '20/min'),
        'login_email': os.getenv('THROTTLE_LOGIN_EMAIL', '10/min'),
        'register': os.getenv('THROTTLE_REGISTER', '10/hour'),
        'password_change': os.getenv('THROTTLE_PASSWORD_CHANGE', '10/hour'),
        'password_reset_ip': os.getenv('THROTTLE_PASSWORD_RESET_IP', '20/hour'),
        'password_reset_email': os.getenv('THROTTLE_PASSWORD_RESET_EMAIL', '6/hour'),
        'password_reset_verify_ip': os.getenv('THROTTLE_PASSWORD_RESET_VERIFY_IP', '60/hour'),
        'password_reset_verify_email': os.getenv('THROTTLE_PASSWORD_RESET_VERIFY_EMAIL', '20/hour'),
    },
}

def _access_token_lifetime():
    """Short-lived access tokens, with the old day-based setting still honoured.

    A stolen access token cannot be revoked, so it should live minutes rather
    than a day; the refresh token (which can be blacklisted) carries the
    session. JWT_ACCESS_TOKEN_DAYS still wins when explicitly set so existing
    deployments keep their configured value.
    """
    configured_days = os.getenv('JWT_ACCESS_TOKEN_DAYS')
    if configured_days:
        return timedelta(days=env_int('JWT_ACCESS_TOKEN_DAYS', 1))
    return timedelta(minutes=env_int('JWT_ACCESS_TOKEN_MINUTES', 60))


SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': _access_token_lifetime(),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=env_int('JWT_REFRESH_TOKEN_DAYS', 30)),
    'ROTATE_REFRESH_TOKENS': True,
    # Without this, a refresh token that has already been rotated away stays
    # valid for its full lifetime, so a leaked one is usable for 30 days and
    # logging out cannot revoke anything.
    'BLACKLIST_AFTER_ROTATION': True,
    'UPDATE_LAST_LOGIN': True,
}

# Wide-open CORS is a development convenience, so it follows DEBUG rather than
# staying on by default: a deployed backend that echoes any origin lets any
# site on the internet script calls against it from a visitor's browser.
CORS_ALLOW_ALL_ORIGINS = env_bool('DJANGO_CORS_ALLOW_ALL_ORIGINS', DEBUG)
CORS_ALLOWED_ORIGINS = env_list('DJANGO_CORS_ALLOWED_ORIGINS', [])
# The API authenticates with an Authorization header, never a cookie, so it has
# no reason to accept credentialed cross-origin requests -- and pairing that
# with allow-all origins is the combination browsers specifically forbid.
CORS_ALLOW_CREDENTIALS = env_bool('DJANGO_CORS_ALLOW_CREDENTIALS', False)

# django-cors-headers answers allow-all by echoing the caller's own Origin, so
# pairing it with credentials does not hit the browser's "* plus credentials"
# ban -- it just works, and hands every site on the internet authenticated
# access. An .env carried over from development can set both without anyone
# noticing, so refuse to start rather than serve that.
if not DEBUG and CORS_ALLOW_ALL_ORIGINS and CORS_ALLOW_CREDENTIALS:
    raise ImproperlyConfigured(
        'DJANGO_CORS_ALLOW_ALL_ORIGINS and DJANGO_CORS_ALLOW_CREDENTIALS must not '
        'both be enabled when DEBUG is false. List the origins that may call the '
        'API in DJANGO_CORS_ALLOWED_ORIGINS instead.'
    )
# Needed once the admin panel is served over HTTPS behind a proxy, because
# Django checks the Origin of the admin's POST forms against this list.
CSRF_TRUSTED_ORIGINS = env_list('DJANGO_CSRF_TRUSTED_ORIGINS', [])

# --- Transport and cookie hardening -----------------------------------------
# Everything here keys off DEBUG so local HTTP development is untouched while a
# DEBUG=False deployment is hardened by default. Each one is still overridable
# for the odd environment that needs it.

# Only trust X-Forwarded-Proto when a proxy in front of Django actually sets it.
# Turning this on without one lets a client claim its plain HTTP request was
# secure just by sending the header.
if env_bool('DJANGO_TRUST_PROXY_SSL_HEADER', False):
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

SECURE_SSL_REDIRECT = env_bool('DJANGO_SECURE_SSL_REDIRECT', not DEBUG)
SESSION_COOKIE_SECURE = env_bool('DJANGO_SESSION_COOKIE_SECURE', not DEBUG)
CSRF_COOKIE_SECURE = env_bool('DJANGO_CSRF_COOKIE_SECURE', not DEBUG)

# The admin session cookie is the key to the dashboard, and nothing in the
# project reads either cookie from JavaScript, so keep both away from scripts.
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SAMESITE = 'Lax'

# A year, so the browser refuses to downgrade to HTTP after the first visit.
# Preload is left off by default: submitting a domain to the browser preload
# list is slow to undo, and that should be a deliberate choice.
SECURE_HSTS_SECONDS = env_int('DJANGO_SECURE_HSTS_SECONDS', 0 if DEBUG else 31536000)
SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool(
    'DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS',
    not DEBUG,
)
SECURE_HSTS_PRELOAD = env_bool('DJANGO_SECURE_HSTS_PRELOAD', False)

SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = 'same-origin'
# Nothing in EmoTune is meant to be framed, and the admin dashboard is exactly
# the kind of page clickjacking targets.
X_FRAME_OPTIONS = 'DENY'

# Spotify API
SPOTIFY_CLIENT_ID = os.getenv(
    'SPOTIFY_CLIENT_ID',
    '',
)
SPOTIFY_CLIENT_SECRET = os.getenv(
    'SPOTIFY_CLIENT_SECRET',
    '',
)
SPOTIFY_REDIRECT_URI = os.getenv(
    'SPOTIFY_REDIRECT_URI',
    'http://127.0.0.1:8000/api/spotify/callback/',
)
SPOTIFY_APP_REMOTE_REDIRECT_URI = os.getenv(
    'SPOTIFY_APP_REMOTE_REDIRECT_URI',
    'emotune://spotify-auth-callback',
)
# Deep link the OAuth callback page sends the browser back to so the phone
# returns to EmoTune once Spotify login finishes. Deliberately a different
# host from SPOTIFY_APP_REMOTE_REDIRECT_URI, which the Spotify SDK owns.
SPOTIFY_APP_RETURN_URI = os.getenv(
    'SPOTIFY_APP_RETURN_URI',
    'emotune://spotify-connected',
)
# How long a Spotify OAuth `state` stays valid. Long enough to log in and pick
# an account, short enough that a leaked callback URL goes stale quickly.
SPOTIFY_OAUTH_STATE_MAX_AGE_SECONDS = env_int(
    'SPOTIFY_OAUTH_STATE_MAX_AGE_SECONDS',
    600,
)
SPOTIFY_SCOPE = (
    'user-read-private user-read-email playlist-read-private '
    'playlist-read-collaborative user-library-read user-top-read '
    'user-read-recently-played streaming '
    'user-modify-playback-state user-read-playback-state '
    'user-read-currently-playing '
    'app-remote-control'
)
SPOTIFY_REQUIRED_PLAYBACK_SCOPES = (
    'streaming user-modify-playback-state user-read-playback-state '
    'user-read-currently-playing app-remote-control'
)
SPOTIFY_HTTP_TIMEOUT_SECONDS = float(
    os.getenv('SPOTIFY_HTTP_TIMEOUT_SECONDS', '3'),
)
SPOTIFY_RECOMMENDATION_BUDGET_SECONDS = float(
    os.getenv('SPOTIFY_RECOMMENDATION_BUDGET_SECONDS', '6'),
)
SPOTIFY_PROGRESSIVE_INITIAL_BUDGET_SECONDS = env_float(
    'SPOTIFY_PROGRESSIVE_INITIAL_BUDGET_SECONDS',
    2.5,
)
SPOTIFY_PROGRESSIVE_INITIAL_CANDIDATE_LIMIT = env_int(
    'SPOTIFY_PROGRESSIVE_INITIAL_CANDIDATE_LIMIT',
    6,
)
SPOTIFY_PROGRESSIVE_INITIAL_TRACK_LIMIT = env_int(
    'SPOTIFY_PROGRESSIVE_INITIAL_TRACK_LIMIT',
    1,
)
SPOTIFY_PROGRESSIVE_CONTINUATION_BUDGET_SECONDS = env_float(
    'SPOTIFY_PROGRESSIVE_CONTINUATION_BUDGET_SECONDS',
    8.0,
)
SPOTIFY_PROGRESSIVE_CONTINUATION_CANDIDATE_LIMIT = env_int(
    'SPOTIFY_PROGRESSIVE_CONTINUATION_CANDIDATE_LIMIT',
    20,
)
# Shared per-emotion candidate pool ("waiting room"). Pre-fetched Spotify
# candidates are served straight from the database so a recommendation no
# longer waits on a chain of live catalog searches. Keep the ages short: this
# is a cache, not a local copy of the Spotify catalog.
SPOTIFY_TRACK_POOL_ENABLED = env_bool('SPOTIFY_TRACK_POOL_ENABLED', True)
SPOTIFY_TRACK_POOL_TARGET_SIZE = env_int('SPOTIFY_TRACK_POOL_TARGET_SIZE', 100)
SPOTIFY_TRACK_POOL_FRESH_SECONDS = env_int(
    'SPOTIFY_TRACK_POOL_FRESH_SECONDS',
    6 * 60 * 60,
)
SPOTIFY_TRACK_POOL_MAX_AGE_SECONDS = env_int(
    'SPOTIFY_TRACK_POOL_MAX_AGE_SECONDS',
    24 * 60 * 60,
)
# What a pool hit may still spend on the queries that are specific to this
# request (preferred artists, LLM picks, playlist category).
SPOTIFY_TRACK_POOL_LIVE_QUERY_BUDGET_SECONDS = env_float(
    'SPOTIFY_TRACK_POOL_LIVE_QUERY_BUDGET_SECONDS',
    1.5,
)
SPOTIFY_TRACK_POOL_LIVE_QUERY_SHARE = env_float(
    'SPOTIFY_TRACK_POOL_LIVE_QUERY_SHARE',
    0.4,
)
SPOTIFY_TRACK_POOL_REFRESH_BUDGET_SECONDS = env_float(
    'SPOTIFY_TRACK_POOL_REFRESH_BUDGET_SECONDS',
    25.0,
)
MUSIC_PICKER_PLAYLIST_DOC = os.getenv(
    'MUSIC_PICKER_PLAYLIST_DOC',
    str(PROJECT_ROOT / 'docs' / 'music.md'),
)
# Appended to the crisis-safety fallback message (api/safety.py) when free-text
# input matches self-harm/suicide language. Left empty by default -- a wrong or
# outdated hotline is worse than none, so this must be set to a verified, current
# resource for your deployment's region before relying on it in front of real users.
CRISIS_HOTLINE_TEXT = os.getenv('CRISIS_HOTLINE_TEXT', '')
MUSIC_PICKER_EMOTION_SEED_TRACK_LIMIT = env_int(
    'MUSIC_PICKER_EMOTION_SEED_TRACK_LIMIT',
    10,
)
RECOMMENDATION_CONTINUATION_MAX_AGE_SECONDS = env_int(
    'RECOMMENDATION_CONTINUATION_MAX_AGE_SECONDS',
    900,
)
# The music picker's model: a linear ranker whose weights are fitted offline by
# ml_model/train_picker_ranker.py. Serving it costs one dot product per
# candidate -- no native build, no per-request model fitting, so it runs
# anywhere the backend runs. With no artifact on disk the built-in defaults
# reproduce the hand-tuned blend the picker shipped with.
PICKER_RANKER_ENABLED = env_bool(
    'PICKER_RANKER_ENABLED',
    True,
)
PICKER_RANKER_WEIGHTS_PATH = os.getenv(
    'PICKER_RANKER_WEIGHTS_PATH',
    str(BASE_DIR.parent / 'ml_model' / 'artifacts' / 'picker_weights.json'),
)

LLM_MUSIC_PICKER_ENABLED = env_bool(
    'LLM_MUSIC_PICKER_ENABLED',
    False,
)
LLM_MUSIC_PICKER_PROVIDER = os.getenv(
    'LLM_MUSIC_PICKER_PROVIDER',
    '',
)
LLM_MUSIC_PICKER_API_URL = os.getenv(
    'LLM_MUSIC_PICKER_API_URL',
    '',
)
LLM_MUSIC_PICKER_API_KEY = os.getenv(
    'LLM_MUSIC_PICKER_API_KEY',
    '',
)
LLM_MUSIC_PICKER_MODEL = os.getenv(
    'LLM_MUSIC_PICKER_MODEL',
    '',
)
LLM_MUSIC_PICKER_GEMINI_API_VERSION = os.getenv(
    'LLM_MUSIC_PICKER_GEMINI_API_VERSION',
    'v1beta',
)
LLM_MUSIC_PICKER_TIMEOUT_SECONDS = env_float(
    'LLM_MUSIC_PICKER_TIMEOUT_SECONDS',
    8.0,
)
LLM_MUSIC_PICKER_MAX_CANDIDATES = env_int(
    'LLM_MUSIC_PICKER_MAX_CANDIDATES',
    18,
)
LLM_MUSIC_PICKER_PLAYLIST_SIZE = env_int(
    'LLM_MUSIC_PICKER_PLAYLIST_SIZE',
    12,
)
LLM_MUSIC_PICKER_SEARCH_QUERY_COUNT = env_int(
    'LLM_MUSIC_PICKER_SEARCH_QUERY_COUNT',
    6,
)
LLM_MUSIC_PICKER_EXACT_SONG_SEED_ENABLED = env_bool(
    'LLM_MUSIC_PICKER_EXACT_SONG_SEED_ENABLED',
    True,
)
LLM_MUSIC_PICKER_EXACT_SONG_SEED_QUERY_LIMIT = env_int(
    'LLM_MUSIC_PICKER_EXACT_SONG_SEED_QUERY_LIMIT',
    3,
)
LLM_MUSIC_PICKER_TEMPERATURE = env_float(
    'LLM_MUSIC_PICKER_TEMPERATURE',
    0.2,
)
EMOTION_HIGH_CONFIDENCE_THRESHOLD = env_float(
    'EMOTION_HIGH_CONFIDENCE_THRESHOLD',
    0.68,
)
EMOTION_MEDIUM_CONFIDENCE_THRESHOLD = env_float(
    'EMOTION_MEDIUM_CONFIDENCE_THRESHOLD',
    0.45,
)
EMOTION_MIN_MARGIN_THRESHOLD = env_float(
    'EMOTION_MIN_MARGIN_THRESHOLD',
    0.12,
)
EMOTION_TOP_EMOTIONS_COUNT = env_int(
    'EMOTION_TOP_EMOTIONS_COUNT',
    2,
)
EMOTION_GOEMOTIONS_ENABLED = env_bool(
    'EMOTION_GOEMOTIONS_ENABLED',
    True,
)
EMOTION_GOEMOTIONS_MODEL_ID = os.getenv(
    'EMOTION_GOEMOTIONS_MODEL_ID',
    'SamLowe/roberta-base-go_emotions',
)
EMOTION_GOEMOTIONS_LOCAL_ONLY = env_bool(
    'EMOTION_GOEMOTIONS_LOCAL_ONLY',
    True,
)
EMOTION_GOEMOTIONS_MIN_CONFIDENCE_THRESHOLD = env_float(
    'EMOTION_GOEMOTIONS_MIN_CONFIDENCE_THRESHOLD',
    0.30,
)
EMOTION_GOEMOTIONS_MIN_MARGIN_THRESHOLD = env_float(
    'EMOTION_GOEMOTIONS_MIN_MARGIN_THRESHOLD',
    0.05,
)

# ML Model
ML_MODEL_PATH = os.getenv(
    'ML_MODEL_PATH',
    str(BASE_DIR / 'ml' / 'models' / 'bert_emotion_model'),
) or str(BASE_DIR / 'ml' / 'models' / 'bert_emotion_model')

CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels.layers.InMemoryChannelLayer',
    },
}

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {'class': 'logging.StreamHandler'},
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
}
