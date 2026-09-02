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

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
}

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(days=env_int('JWT_ACCESS_TOKEN_DAYS', 1)),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=env_int('JWT_REFRESH_TOKEN_DAYS', 30)),
    'ROTATE_REFRESH_TOKENS': True,
}

CORS_ALLOW_ALL_ORIGINS = env_bool('DJANGO_CORS_ALLOW_ALL_ORIGINS', True)
CORS_ALLOW_CREDENTIALS = env_bool('DJANGO_CORS_ALLOW_CREDENTIALS', True)

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
RECOMMENDATION_CONTINUATION_MAX_AGE_SECONDS = env_int(
    'RECOMMENDATION_CONTINUATION_MAX_AGE_SECONDS',
    900,
)
LIGHTFM_RECOMMENDER_ENABLED = env_bool(
    'LIGHTFM_RECOMMENDER_ENABLED',
    True,
)
LIGHTFM_RECOMMENDER_ALLOW_WINDOWS = env_bool(
    'LIGHTFM_RECOMMENDER_ALLOW_WINDOWS',
    False,
)
LIGHTFM_RECOMMENDER_LOSS = os.getenv(
    'LIGHTFM_RECOMMENDER_LOSS',
    'warp',
)
LIGHTFM_RECOMMENDER_COMPONENTS = env_int(
    'LIGHTFM_RECOMMENDER_COMPONENTS',
    16,
)
LIGHTFM_RECOMMENDER_EPOCHS = env_int(
    'LIGHTFM_RECOMMENDER_EPOCHS',
    20,
)
LIGHTFM_RECOMMENDER_ITEM_ALPHA = env_float(
    'LIGHTFM_RECOMMENDER_ITEM_ALPHA',
    0.000001,
)
LIGHTFM_RECOMMENDER_USER_ALPHA = env_float(
    'LIGHTFM_RECOMMENDER_USER_ALPHA',
    0.000001,
)
# LightFM only earns its 40% share of the ranking once there is enough
# behaviour to learn from. Below these floors a fresh model is fitting noise,
# so the deterministic emotion ranking is the better answer and the ranker
# hands back its heuristic result instead.
LIGHTFM_RECOMMENDER_MIN_INTERACTIONS = env_int(
    'LIGHTFM_RECOMMENDER_MIN_INTERACTIONS',
    200,
)
LIGHTFM_RECOMMENDER_MIN_USER_INTERACTIONS = env_int(
    'LIGHTFM_RECOMMENDER_MIN_USER_INTERACTIONS',
    20,
)
# The corpus is rebuilt on every request, so the history scans are bounded by
# age and row count instead of growing with the whole database.
LIGHTFM_RECOMMENDER_HISTORY_DAYS = env_int(
    'LIGHTFM_RECOMMENDER_HISTORY_DAYS',
    120,
)
LIGHTFM_RECOMMENDER_MAX_HISTORY_ROWS = env_int(
    'LIGHTFM_RECOMMENDER_MAX_HISTORY_ROWS',
    2000,
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
