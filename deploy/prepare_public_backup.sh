#!/usr/bin/env bash
# Prepare safe public GitHub backup (anonymized DB snapshot).
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$APP_DIR"

SNAPSHOT_PATH="${1:-snapshots/db_public.sqlite3}"

venv/bin/python manage.py create_public_snapshot --output "$SNAPSHOT_PATH" --overwrite

cat <<MSG

Public backup pripravený:
  $SNAPSHOT_PATH

Odporúčaný postup:
  1) git add $SNAPSHOT_PATH README.md deploy/init_after_pull.sh deploy/prepare_public_backup.sh
  2) git commit -m "public backup snapshot"
  3) git push origin main

MSG
