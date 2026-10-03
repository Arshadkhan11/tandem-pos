#!/usr/bin/env bash
# One-time setup of the analytics site on the droplet. Safe to re-run (it also
# serves as the "update" step after a git pull).
#
#   sudo bash /opt/tandem/insights/deploy/install.sh
#
# Afterwards, add the first login:  sudo bash /opt/tandem/insights/deploy/add_user.sh
set -euo pipefail
[ "$(id -u)" -eq 0 ] || { echo "Run as root (sudo)." >&2; exit 1; }

REPO=/opt/tandem
BASE=/opt/analytics

id analytics >/dev/null 2>&1 || \
  useradd --system --home-dir "$BASE" --shell /usr/sbin/nologin analytics

# data/: written by the tandem user, readable by analytics (setgid keeps the group).
# secret/: the phone-hash salt. Only tandem can read it; Datasette's user cannot.
install -d -o root   -g root      -m 0755 "$BASE"
install -d -o tandem -g analytics -m 2770 "$BASE/data"
install -d -o tandem -g tandem    -m 0700 "$BASE/secret"

[ -x "$BASE/venv/bin/pip" ] || python3 -m venv "$BASE/venv"
"$BASE/venv/bin/pip" install --quiet --upgrade pip
"$BASE/venv/bin/pip" install --quiet -r "$REPO/insights/requirements.txt"

install -o root -g root -m 0644 "$REPO/insights/metadata.yml" "$BASE/metadata.yml"
for unit in analytics-datasette.service analytics-refresh.service analytics-refresh.timer; do
  install -o root -g root -m 0644 "$REPO/insights/deploy/$unit" "/etc/systemd/system/$unit"
done
systemctl daemon-reload

# First build must exist before Datasette starts.
systemctl start analytics-refresh.service
systemctl enable --now analytics-datasette.service analytics-refresh.timer
systemctl restart analytics-datasette.service

echo
systemctl --no-pager --lines=0 status analytics-datasette.service | head -4 || true
echo
echo "Datasette is running on 127.0.0.1:8011 (not public yet)."
echo "Next: add DNS  analytics.tandemretreat.com -> this droplet, then run add_user.sh"
