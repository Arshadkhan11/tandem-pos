#!/usr/bin/env bash
# Remove a login from the analytics site.   sudo bash remove_user.sh <username>
set -euo pipefail
[ "$(id -u)" -eq 0 ] || { echo "Run as root (sudo)." >&2; exit 1; }
NAME="${1:?usage: remove_user.sh <username>}"
USERS=/etc/caddy/analytics_users
grep -q "^${NAME//./\\.} " "$USERS" || { echo "No such user: $NAME" >&2; exit 1; }
[ "$(wc -l < "$USERS")" -gt 1 ] || { echo "Refusing to remove the last user (the site needs at least one)." >&2; exit 1; }
sed -i "/^${NAME//./\\.} /d" "$USERS"
caddy validate --config /etc/caddy/Caddyfile >/dev/null
systemctl reload caddy
echo "Removed $NAME."
