#!/usr/bin/env bash
# Quick app refresh after manual template/CSS/backend changes.
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="$APP_DIR/venv/bin/python"
SERVICE_NAME="${POCHOP_SERVICE_NAME:-pochop.service}"

WITH_MIGRATE=0
WITH_MOMENT=0

usage() {
  cat <<'EOF'
Usage:
  bash deploy/refresh.sh [--with-migrate] [--with-moment]

Options:
  --with-migrate   Run database migrations before collectstatic.
  --with-moment    Regenerate daily moment report after restart.
  -h, --help       Show this help.
EOF
}

for arg in "$@"; do
  case "$arg" in
    --with-migrate) WITH_MIGRATE=1 ;;
    --with-moment) WITH_MOMENT=1 ;;
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

echo "[1/4] Django checks..."
"$PYTHON_BIN" manage.py check

if [ "$WITH_MIGRATE" -eq 1 ]; then
  echo "[2/4] Migrations..."
  "$PYTHON_BIN" manage.py migrate --noinput
else
  echo "[2/4] Migrations skipped (use --with-migrate if needed)."
fi

echo "[3/4] Collectstatic..."
"$PYTHON_BIN" manage.py collectstatic --noinput

echo "[4/4] Reload service..."
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

if [ "$WITH_MOMENT" -eq 1 ]; then
  echo "[extra] Regenerating moment report..."
  "$PYTHON_BIN" manage.py generate_moment_report --force --email-admin || true
fi

echo "Refresh done."
