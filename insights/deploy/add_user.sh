#!/usr/bin/env bash
# Add (or change the password of) a login for the analytics site.
# The first run also publishes the site by adding its block to the Caddyfile.
#
#   sudo bash /opt/tandem/insights/deploy/add_user.sh
set -euo pipefail
[ "$(id -u)" -eq 0 ] || { echo "Run as root (sudo)." >&2; exit 1; }

USERS=/etc/caddy/analytics_users
CADDYFILE=/etc/caddy/Caddyfile

read -rp "Username (letters, digits, . _ -): " NAME
[[ "$NAME" =~ ^[A-Za-z0-9._-]+$ ]] || { echo "Invalid username." >&2; exit 1; }
read -rsp "Password: " PW; echo
read -rsp "Repeat password: " PW2; echo
[ "$PW" = "$PW2" ] || { echo "Passwords do not match." >&2; exit 1; }
[ "${#PW}" -ge 10 ] || { echo "Use at least 10 characters." >&2; exit 1; }

HASH="$(caddy hash-password --plaintext "$PW" | tail -n 1)"
unset PW PW2

touch "$USERS"
sed -i "/^${NAME//./\\.} /d" "$USERS"
echo "$NAME $HASH" >> "$USERS"
chown root:caddy "$USERS"; chmod 0640 "$USERS"

if ! grep -q "analytics.tandemretreat.com" "$CADDYFILE"; then
  cp "$CADDYFILE" "$CADDYFILE.bak.$(date +%Y%m%d%H%M%S)"
  cat >> "$CADDYFILE" <<'BLOCK'

analytics.tandemretreat.com {
	encode gzip
	header X-Robots-Tag "noindex, nofollow"

	basic_auth {
		import /etc/caddy/analytics_users
	}

	reverse_proxy 127.0.0.1:8011
}
BLOCK
fi

caddy validate --config "$CADDYFILE" >/dev/null
systemctl reload caddy
echo "Done. '$NAME' can now sign in at https://analytics.tandemretreat.com"
