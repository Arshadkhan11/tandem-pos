#!/usr/bin/env bash
# Pre-deploy checks on a clean tree (run from tandem/ project root).
set -euo pipefail
cd "$(dirname "$0")/.."

echo "== files =="
test -f deploy/tandem.service
test -f deploy/tandem-backup.service
test -f deploy/tandem-backup.timer
test -f deploy/Caddyfile
test -x deploy/backup_db.sh
grep -q 'unix:/run/tandem/gunicorn.sock' deploy/tandem.service
grep -q 'EnvironmentFile=/opt/tandem/.env' deploy/tandem.service
grep -q 'app.tandemretreat.com' deploy/Caddyfile
grep -q 'X-Forwarded-Proto' deploy/Caddyfile
echo "deploy units OK"

echo "== django =="
export DEBUG=True
./venv/bin/python manage.py check
./venv/bin/python manage.py test orders -v1
echo "ALL PREDEPLOY CHECKS PASSED"
