# Deploy Tandem POS to Ubuntu 22.04 (VPS)

Target URL: **https://app.tandemretreat.com**  
Stack: Django + gunicorn (unix socket) + Caddy (HTTPS) + SQLite. No Docker, no nginx, no Postgres.

App lives at `/opt/tandem` (this repo’s `tandem/` project root — the folder that contains `manage.py`).

---

## 0. Firewall (do this first)

```bash
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
sudo ufw status
```

Point DNS **A** (and **AAAA** if you use IPv6) for `app.tandemretreat.com` at this VPS before enabling Caddy, so Let’s Encrypt can issue a cert.

---

## 1. Create a deploy user

```bash
sudo adduser --system --group --home /opt/tandem tandem
sudo mkdir -p /opt/tandem /opt/tandem/backups
sudo chown -R tandem:tandem /opt/tandem
```

Give the `caddy` user access to the gunicorn socket (group `tandem`):

```bash
# After Caddy is installed (step 8), run:
sudo usermod -aG tandem caddy
```

---

## 2. Install system packages

```bash
sudo apt update
sudo apt install -y python3 python3-pip python3-venv git sqlite3 libzbar0
```

`libzbar0` is required for UPI QR photo decoding in Django admin (`pyzbar`). Pip alone is not enough.

---

## 3. Put the app in `/opt/tandem`

Clone or copy so that `/opt/tandem/manage.py` exists. Examples:

```bash
# If the git repo root IS the Django project (manage.py at repo root):
sudo -u tandem git clone <YOUR_REPO_URL> /opt/tandem

# If the git repo contains a tandem/ subfolder, clone then move contents:
# sudo -u tandem git clone <YOUR_REPO_URL> /tmp/res-pos
# sudo cp -a /tmp/res-pos/tandem/. /opt/tandem/
# sudo chown -R tandem:tandem /opt/tandem
```

Ensure deploy scripts are executable:

```bash
sudo chmod +x /opt/tandem/deploy/backup_db.sh
```

---

## 4. Create the virtualenv and install requirements

```bash
sudo -u tandem python3 -m venv /opt/tandem/venv
sudo -u tandem /opt/tandem/venv/bin/pip install --upgrade pip
sudo -u tandem /opt/tandem/venv/bin/pip install -r /opt/tandem/requirements.txt
```

---

## 5. Create `/opt/tandem/.env`

```bash
sudo -u tandem cp /opt/tandem/.env.example /opt/tandem/.env
sudo -u tandem nano /opt/tandem/.env
```

Set at least:

```env
SECRET_KEY=<long-random-string>
DEBUG=False
ALLOWED_HOSTS=app.tandemretreat.com
CSRF_TRUSTED_ORIGINS=https://app.tandemretreat.com
```

Generate a secret key:

```bash
python3 -c 'import secrets; print(secrets.token_urlsafe(50))'
```

Lock down the file:

```bash
sudo chmod 600 /opt/tandem/.env
sudo chown tandem:tandem /opt/tandem/.env
```

Optional: set `TANDEM_UPI_ID`, `SMS_*`, etc. (see `.env.example`).

---

## 6. Migrate, seed, collectstatic

systemd loads `.env` for gunicorn; for one-off management commands, export it first:

```bash
sudo -u tandem bash -lc '
  set -a
  source /opt/tandem/.env
  set +a
  cd /opt/tandem
  ./venv/bin/python manage.py migrate
  ./venv/bin/python manage.py seed_menu
  ./venv/bin/python manage.py seed_staff
  ./venv/bin/python manage.py collectstatic --noinput
'
```

**Change default staff passwords** before opening day (`orders/management/commands/seed_staff.py`, then re-run `seed_staff`).

---

## 7. Install and start systemd units

```bash
sudo cp /opt/tandem/deploy/tandem.service /etc/systemd/system/
sudo cp /opt/tandem/deploy/tandem-backup.service /etc/systemd/system/
sudo cp /opt/tandem/deploy/tandem-backup.timer /etc/systemd/system/

sudo systemctl daemon-reload
sudo systemctl enable --now tandem.service
sudo systemctl enable --now tandem-backup.timer

sudo systemctl status tandem.service
sudo systemctl list-timers | grep tandem
```

Socket should appear at `/run/tandem/gunicorn.sock`.

Test the app directly via the socket (optional):

```bash
curl --unix-socket /run/tandem/gunicorn.sock http://localhost/health/
# expect: ok
```

---

## 8. Install Caddy and enable HTTPS

```bash
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update
sudo apt install -y caddy
```

Install the site config (backup the default first):

```bash
sudo cp /etc/caddy/Caddyfile /etc/caddy/Caddyfile.bak
sudo cp /opt/tandem/deploy/Caddyfile /etc/caddy/Caddyfile

# Socket access for Caddy
sudo usermod -aG tandem caddy
sudo systemctl restart caddy
sudo systemctl enable caddy
sudo systemctl restart tandem.service
```

Check:

```bash
curl -I https://app.tandemretreat.com/health/
# expect HTTP/2 200
```

Staff URLs:

- https://app.tandemretreat.com/login/waiter/
- https://app.tandemretreat.com/login/chef/
- https://app.tandemretreat.com/login/admin/

---

## 9. Backups

- Timer: `tandem-backup.timer` runs `deploy/backup_db.sh` daily at **02:00**
- Files: `/opt/tandem/backups/db-YYYY-MM-DD.sqlite3`
- Retention: deletes backups older than **30 days**

Manual run:

```bash
sudo systemctl start tandem-backup.service
ls -la /opt/tandem/backups/
```

---

## 10. Monitoring (keep it light on a $5 / 1GB droplet)

Do **not** install Grafana/Prometheus on this box — they eat RAM. Use:

### DigitalOcean droplet graphs (free, no agent)
1. DigitalOcean control panel → your droplet → **Graphs** / **Insights**
2. Watch CPU, memory, disk, bandwidth after opening week
3. Optional: enable email alerts for high CPU / disk full in DO monitoring settings

### UptimeRobot free tier → `/health/`
1. Sign up at https://uptimerobot.com
2. Add monitor: **HTTPS**, URL `https://app.tandemretreat.com/health/`
3. Interval: 5 minutes; expect body containing `ok` / status 200
4. Alert to your phone/email if the endpoint is down

### After deploy smoke + light load check
```bash
curl -sS https://app.tandemretreat.com/health/
# expect: ok

# ApacheBench (often preinstalled) — adjust host after DNS is live
ab -n 200 -c 20 https://app.tandemretreat.com/health/
```

Record p50/mean times from `ab` output in your runbook so you have a baseline.

---

## Deploy file checklist (clean checkout)

Confirm these exist and match this README before `systemctl enable`:

| File | Purpose |
|------|---------|
| `deploy/tandem.service` | gunicorn → `unix:/run/tandem/gunicorn.sock`, `EnvironmentFile=/opt/tandem/.env`, `Restart=always`, user `tandem` |
| `deploy/tandem-backup.service` | oneshot → `deploy/backup_db.sh` |
| `deploy/tandem-backup.timer` | daily 02:00 |
| `deploy/Caddyfile` | `app.tandemretreat.com` → unix socket + `X-Forwarded-Proto` |
| `deploy/backup_db.sh` | executable; writes `/opt/tandem/backups/db-YYYY-MM-DD.sqlite3` |

Full sequence on a clean VPS: ufw → user → packages (`libzbar0`) → copy app to `/opt/tandem` → venv + `pip install -r requirements.txt` → `.env` → `migrate` / `seed_*` / `collectstatic` → copy systemd units → `enable --now tandem.service` + `tandem-backup.timer` → install Caddy → `usermod -aG tandem caddy` → copy Caddyfile → `restart caddy` + `restart tandem` → curl `/health/`.

```bash
cd tandem
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
DEBUG=True python manage.py runserver
```

Or copy `.env.example` → `.env` with `DEBUG=True`. Do not commit `.env`.

---

## Useful ops commands

```bash
sudo journalctl -u tandem.service -f
sudo systemctl restart tandem.service
sudo systemctl reload caddy   # after Caddyfile edits
```

After code deploys:

```bash
sudo -u tandem bash -lc '
  set -a; source /opt/tandem/.env; set +a
  cd /opt/tandem
  git pull   # if using git
  ./venv/bin/pip install -r requirements.txt
  ./venv/bin/python manage.py migrate
  ./venv/bin/python manage.py collectstatic --noinput
'
sudo systemctl restart tandem.service
```
