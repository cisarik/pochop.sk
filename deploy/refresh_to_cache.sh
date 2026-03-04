#!/usr/bin/env bash
# Sync Vercel model catalog + refresh lazy AI caches (natal/day report).
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="$APP_DIR/venv/bin/python"

if [ ! -x "$PYTHON_BIN" ]; then
  echo "Missing Python virtualenv: $PYTHON_BIN"
  echo "Run init first, e.g. bash deploy/init_after_pull.sh"
  exit 1
fi

cd "$APP_DIR"

echo "[1/2] Sync Vercel model catalog..."
"$PYTHON_BIN" manage.py sync_vercel_models --keep-missing

echo "[2/2] Refresh AI caches..."
if [ "$#" -eq 0 ]; then
  set -- --profiles all --days 0,1,2 --with-global-natal --with-moment --moment-days 0,1
fi
"$PYTHON_BIN" manage.py refresh_to_cache "$@"

echo "refresh_to_cache done."
