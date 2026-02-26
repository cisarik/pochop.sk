#!/usr/bin/env bash
# Quick init after `git pull` on VPS.
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$APP_DIR"

if [ ! -f ".env" ] && [ -f ".env.example" ]; then
  cp .env.example .env
  echo ".env neexistoval, vytvorený z .env.example (skontroluj kľúče)."
fi

if [ ! -f "db.sqlite3" ] && [ -f "snapshots/db_public.sqlite3" ]; then
  cp snapshots/db_public.sqlite3 db.sqlite3
  echo "db.sqlite3 inicializovaná zo snapshots/db_public.sqlite3"
fi

if [ ! -d "venv" ]; then
  python3 -m venv venv
fi

venv/bin/pip install --upgrade pip
venv/bin/pip install -r requirements.txt

venv/bin/python manage.py migrate --noinput
venv/bin/python manage.py collectstatic --noinput
venv/bin/python manage.py populate_transits
venv/bin/python manage.py populate_cities

# Refresh cached daily public report so landing/okamih stay warm.
venv/bin/python manage.py generate_moment_report --force --email-admin || true

if command -v systemctl >/dev/null 2>&1; then
  systemctl restart pochop.service || true
  systemctl restart pochop-moment.timer || true
fi

echo "Init po pull hotový."
