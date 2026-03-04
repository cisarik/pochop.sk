#!/usr/bin/env bash
# Quick app refresh after manual template/CSS/backend changes.
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="$APP_DIR/venv/bin/python"
SERVICE_NAME="${POCHOP_SERVICE_NAME:-pochop.service}"

WITH_MIGRATE=0
WITH_MOMENT=0
WITH_AI_WARMUP=1

usage() {
  cat <<'EOF'
Usage:
  bash deploy/refresh.sh [--with-migrate] [--with-moment] [--skip-ai-warmup]

Options:
  --with-migrate   Run database migrations before collectstatic.
  --with-moment    Regenerate daily moment report after restart.
  --skip-ai-warmup Skip full AI warmup step (sync models + refresh_to_cache).
  -h, --help       Show this help.
EOF
}

for arg in "$@"; do
  case "$arg" in
    --with-migrate) WITH_MIGRATE=1 ;;
    --with-moment) WITH_MOMENT=1 ;;
    --skip-ai-warmup) WITH_AI_WARMUP=0 ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $arg"
      usage
      exit 1
      ;;
  esac
done

if [ ! -x "$PYTHON_BIN" ]; then
  echo "Missing Python virtualenv: $PYTHON_BIN"
  echo "Run init first, e.g. bash deploy/init_after_pull.sh"
  exit 1
fi

cd "$APP_DIR"

TOTAL_STEPS=4
if [ "$WITH_AI_WARMUP" -eq 1 ]; then
  TOTAL_STEPS=5
fi

step_label() {
  local num="$1"
  echo "[$num/$TOTAL_STEPS]"
}

step=1
echo "$(step_label "$step") Django checks..."
"$PYTHON_BIN" manage.py check
step=$((step + 1))

if [ "$WITH_MIGRATE" -eq 1 ]; then
  echo "$(step_label "$step") Migrations..."
  "$PYTHON_BIN" manage.py migrate --noinput
else
  echo "$(step_label "$step") Migrations skipped (use --with-migrate if needed)."
fi
step=$((step + 1))

echo "$(step_label "$step") Collectstatic..."
"$PYTHON_BIN" manage.py collectstatic --noinput
step=$((step + 1))

echo "$(step_label "$step") Reload service..."
if command -v systemctl >/dev/null 2>&1; then
  if systemctl reload "$SERVICE_NAME"; then
    echo "Service reloaded: $SERVICE_NAME"
  else
    echo "Reload failed or unsupported, trying restart..."
    systemctl restart "$SERVICE_NAME"
  fi

  if ! systemctl is-active --quiet "$SERVICE_NAME"; then
    echo "Service inactive after reload/restart, trying start..."
    systemctl start "$SERVICE_NAME"
  fi

  if systemctl is-active --quiet "$SERVICE_NAME"; then
    echo "Service is active: $SERVICE_NAME"
  else
    echo "Service failed: $SERVICE_NAME"
    systemctl status "$SERVICE_NAME" --no-pager -l || true
    exit 1
  fi
else
  echo "systemctl not found, service restart skipped."
fi
step=$((step + 1))

if [ "$WITH_AI_WARMUP" -eq 1 ]; then
  WARMUP_PROFILE_SCOPE="${AI_WARMUP_PROFILE_SCOPE:-all}"
  WARMUP_DAYS="${AI_WARMUP_DAYS:-0,1,2}"
  WARMUP_MOMENT_DAYS="${AI_WARMUP_MOMENT_DAYS:-0,1}"
  WARMUP_MAX_PROFILES="${AI_WARMUP_MAX_PROFILES:-0}"

  echo "$(step_label "$step") Sync Vercel model catalog..."
  "$PYTHON_BIN" manage.py sync_vercel_models --keep-missing

  echo "Prewarm AI caches (day compare, natal compare, global natal, moment)..."
  WARMUP_CMD=(
    "$PYTHON_BIN" manage.py refresh_to_cache
    --profiles "$WARMUP_PROFILE_SCOPE"
    --days "$WARMUP_DAYS"
    --with-global-natal
    --with-moment
    --moment-days "$WARMUP_MOMENT_DAYS"
  )
  if [ "$WARMUP_MAX_PROFILES" -gt 0 ]; then
    WARMUP_CMD+=(--max-profiles "$WARMUP_MAX_PROFILES")
  fi
  "${WARMUP_CMD[@]}"
fi

if [ "$WITH_MOMENT" -eq 1 ]; then
  echo "[extra] Regenerating moment report..."
  "$PYTHON_BIN" manage.py generate_moment_report --force --email-admin || true
fi

echo "Refresh done."
