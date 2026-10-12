#!/usr/bin/env bash
# EmoTune automated white-box test runner.
#
# Runs the Django backend suite under coverage.py (statement + branch) and the
# Flutter suite with --coverage, then writes everything to test-reports/:
#   backend-coverage.txt    per-module statement/branch table
#   backend-html/index.html browsable line-by-line backend coverage
#   flutter-coverage.txt    per-file line coverage from lcov.info
#   summary.txt             pass/fail and totals for both suites
#
# Usage:  ./run_whitebox_tests.sh            # both suites
#         ./run_whitebox_tests.sh backend    # backend only
#         ./run_whitebox_tests.sh flutter    # flutter only
# Exit code is non-zero if any suite fails.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
REPORTS="$ROOT/test-reports"
TARGET="${1:-all}"
PYTHON="${PYTHON:-$ROOT/backend/venv/bin/python}"
mkdir -p "$REPORTS"
: > "$REPORTS/summary.txt"
status=0

log() { echo "$*" | tee -a "$REPORTS/summary.txt"; }

run_backend() {
  log "== Backend (Django + coverage.py) =="
  if ! "$PYTHON" -m coverage --version >/dev/null 2>&1; then
    echo "coverage.py missing; installing into the backend venv"
    "$PYTHON" -m pip install -q coverage || return 1
  fi
  cd "$ROOT/backend" || return 1
  # Keep tests off the BERT warm-up thread and away from a developer's MySQL.
  export EMOTUNE_WARM_MODELS_ON_STARTUP=false
  "$PYTHON" -m coverage run --branch \
      --source=api,users,ml,emotune_project \
      --omit='*/migrations/*,*/test*.py,*/tests.py,*/management/*,*/asgi.py,*/wsgi.py' \
      manage.py test --noinput 2>&1 | tee "$REPORTS/backend-tests.log"
  local rc=${PIPESTATUS[0]}
  "$PYTHON" -m coverage report --sort=cover > "$REPORTS/backend-coverage.txt"
  "$PYTHON" -m coverage html -d "$REPORTS/backend-html" >/dev/null
  log "$(grep -E '^Ran [0-9]+ tests' "$REPORTS/backend-tests.log")"
  log "$(grep -E '^(OK|FAILED)' "$REPORTS/backend-tests.log" | tail -1)"
  log "Backend coverage (stmt+branch): $(tail -1 "$REPORTS/backend-coverage.txt" | awk '{print $NF}')"
  return "$rc"
}

run_flutter() {
  log "== Flutter (flutter test --coverage) =="
  cd "$ROOT/flutter_app" || return 1
  flutter test --coverage 2>&1 | tee "$REPORTS/flutter-tests.log"
  local rc=${PIPESTATUS[0]}
  awk -F: '/^SF:/{f=$2} /^LF:/{lf=$2} /^LH:/{lh=$2; th+=lh; tf+=lf;
             printf "%6.1f%%  %5d/%-5d %s\n", (lf?100*lh/lf:0), lh, lf, f}
           END{printf "%6.1f%%  %5d/%-5d TOTAL\n", (tf?100*th/tf:0), th, tf}' \
      coverage/lcov.info | sort -n > "$REPORTS/flutter-coverage.txt"
  log "$(grep -E 'All tests passed|Some tests failed' "$REPORTS/flutter-tests.log" | tail -1 | sed 's/.*: //')"
  log "Flutter line coverage: $(grep TOTAL "$REPORTS/flutter-coverage.txt" | awk '{print $1}')"
  return "$rc"
}

if [[ "$TARGET" == all || "$TARGET" == backend ]]; then
  run_backend || status=1
fi
if [[ "$TARGET" == all || "$TARGET" == flutter ]]; then
  run_flutter || status=1
fi

log ""
log "Reports written to $REPORTS"
exit "$status"
