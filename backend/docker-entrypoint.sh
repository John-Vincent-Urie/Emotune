#!/bin/sh
# Container entrypoint: bring the database schema up to date, then run the
# command (gunicorn by default, or whatever `docker compose run` was given).
set -e

if [ "${EMOTUNE_MIGRATE_ON_START:-true}" = "true" ]; then
    # Warm-up off: migrate never classifies anything, and loading the emotion
    # models here would only double the memory spike at startup.
    EMOTUNE_WARM_MODELS_ON_STARTUP=false python manage.py migrate --noinput
fi

exec "$@"
