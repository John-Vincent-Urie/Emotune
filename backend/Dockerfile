# syntax=docker/dockerfile:1
#
# EmoTune backend. Build from the repository root, not from backend/: the
# settings read docs/music.md from the project root, so the build context has to
# include it. docker-compose.yml at the root does this for you.
#
#   docker compose up --build
#
# The trained emotion models are not baked in (the served one alone is 11GB
# with its checkpoints); compose mounts backend/ml/models read-only instead.

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Match the host user's UID so the read-only model and Hugging Face cache
# mounts stay readable, and files written to bind mounts stay yours.
ARG APP_UID=1000
RUN useradd --create-home --uid "${APP_UID}" app \
    && mkdir -p /data/media \
    && chown -R app:app /data

WORKDIR /app/backend

# CPU-only torch first, pinned to the version the dev venv runs: the default
# PyPI wheel drags in several GB of CUDA libraries this backend never uses.
# requirements.txt then sees torch as already satisfied.
ARG TORCH_VERSION=2.13.0
COPY backend/requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --index-url https://download.pytorch.org/whl/cpu "torch==${TORCH_VERSION}" \
    && pip install -r requirements.txt

COPY docs/music.md /app/docs/music.md
COPY backend/ .

# Collected at build time so the image serves the admin's CSS/JS (through
# WhiteNoise) without a writable code directory.
RUN EMOTUNE_WARM_MODELS_ON_STARTUP=false python manage.py collectstatic --noinput \
    && chmod +x docker-entrypoint.sh

# TZ matches settings.TIME_ZONE so gunicorn log timestamps
# line up with Django's.
ENV DJANGO_SQLITE_PATH=/data/db.sqlite3 \
    DJANGO_MEDIA_ROOT=/data/media \
    HF_HOME=/home/app/.cache/huggingface \
    TZ=Asia/Manila

USER app
EXPOSE 8000

ENTRYPOINT ["./docker-entrypoint.sh"]
# One worker: each process loads its own ~1.5GB copy of the emotion models.
# Threads give the concurrency instead. Tune with GUNICORN_CMD_ARGS or
# WEB_CONCURRENCY without rebuilding.
CMD ["gunicorn", "emotune_project.wsgi:application", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "1", \
     "--threads", "4", \
     "--timeout", "120", \
     "--access-logfile", "-"]
