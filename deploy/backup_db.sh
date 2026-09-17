#!/usr/bin/env bash
# Daily SQLite backup for Tandem. Intended to run via systemd timer.
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/tandem}"
DB_PATH="${DB_PATH:-$APP_DIR/db.sqlite3}"
BACKUP_DIR="${BACKUP_DIR:-$APP_DIR/backups}"
KEEP_DAYS="${KEEP_DAYS:-30}"

mkdir -p "$BACKUP_DIR"

if [[ ! -f "$DB_PATH" ]]; then
  echo "ERROR: database not found at $DB_PATH" >&2
  exit 1
fi

STAMP="$(date +%Y-%m-%d)"
DEST="$BACKUP_DIR/db-${STAMP}.sqlite3"

# Consistent snapshot even if gunicorn has the DB open (SQLite online backup via .backup)
if command -v sqlite3 >/dev/null 2>&1; then
  sqlite3 "$DB_PATH" ".backup '$DEST'"
else
  cp -a "$DB_PATH" "$DEST"
fi

# Prune backups older than KEEP_DAYS
find "$BACKUP_DIR" -type f -name 'db-*.sqlite3' -mtime +"$KEEP_DAYS" -delete

echo "Backup written: $DEST"
