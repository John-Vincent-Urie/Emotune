#!/usr/bin/env bash
#
# Warm the shared per-emotion candidate pools.
#
# Why this runs on a schedule: a pool older than
# SPOTIFY_TRACK_POOL_MAX_AGE_SECONDS is ignored outright, and every
# recommendation then falls back to a full chain of live Spotify searches --
# measured at 6-9s per request instead of ~0.1s from a warm pool. The pools in
# this project were once left unrefreshed for three weeks, which is exactly the
# failure this script exists to prevent.
#
# Install (every 4 hours, against a 6h fresh window and a 72h max age, so two
# missed runs still degrade to "slightly stale" rather than "cold"):
#
#   crontab -e
#   0 */4 * * * /path/to/EmoTune-Capstone_project/backend/scripts/refresh_pools.sh
#
# Also run it once at the end of every deploy.
set -euo pipefail

BACKEND_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${EMOTUNE_PYTHON:-$BACKEND_DIR/venv/bin/python}"
LOG_FILE="${EMOTUNE_POOL_LOG:-$BACKEND_DIR/logs/refresh_pools.log}"

mkdir -p "$(dirname "$LOG_FILE")"

# The classifier is ~1.5GB resident and this job never classifies anything, so
# skipping warm-up keeps the cron run from doubling the box's memory use
# alongside the live server.
export EMOTUNE_WARM_MODELS_ON_STARTUP=false

cd "$BACKEND_DIR"

{
    echo "=== $(date -Is) refresh_emotion_pools starting ==="
    # --pause spaces the emotions out; refreshing all 13 back to back sends a
    # few hundred searches in a row and Spotify answers with 429.
    "$PYTHON" manage.py refresh_emotion_pools --pause 5 2>&1 |
        grep -vE '^Spotify (GET|POST) '
    echo "=== $(date -Is) refresh_emotion_pools finished ==="
} >>"$LOG_FILE" 2>&1
