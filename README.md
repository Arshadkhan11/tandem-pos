# Tandem order management — Day 1+2+3 scaffold

## What's here
- Models: Table, MenuItem, Order, OrderItem
- Waiter: table grid -> order screen -> tap items to add -> live cart total -> Bill button
- Kitchen: live queue (HTMX polls every 3s), turns red past 10 min waiting, tap Done to clear
- Billing: total auto-calculated, UPI QR generated (upi://pay URI, no payment gateway), close-table button
- Staff accounts (waiter / chef / admin) managed in **/django-admin/** (see below)
- Optional customer name/phone + marketing opt-in on the order screen
- Kitchen beep + vibrate when a new ticket appears
- Bill screen WhatsApp thanks link; optional thank-you SMS on close (see SMS_* in settings)
- Admin summary: KPI tiles, date ranges, Chart.js trends, CSV export (app login — `/admin-summary/`)
- Restaurant UPI settings (incl. QR scan) in `/django-admin/` → Restaurant settings

## Before you run this live
- Set UPI via `/django-admin/` → **Restaurant settings** (upload QR or type VPA), or `TANDEM_UPI_ID` env fallback
- Change default staff passwords (via `/django-admin/` or re-run `seed_staff` after editing the command)
- Replace the placeholder ITEMS list in `orders/management/commands/seed_menu.py` with real items
- For VPS deploy (Caddy + gunicorn + HTTPS): see **[deploy/README.md](deploy/README.md)**
  - QR scanning needs system package **`libzbar0`**: `sudo apt install libzbar0` (pip `pyzbar` alone is not enough)

## Run it (local)
```
pip install -r requirements.txt
DEBUG=True python manage.py migrate
DEBUG=True python manage.py seed_menu
DEBUG=True python manage.py seed_staff
DEBUG=True python manage.py runserver
```

### Staff logins (after `seed_staff`)
- `/login/waiter/` — `waiter1` / `waiter111` (also waiter2, waiter3)
- `/login/chef/` — `chef1` / `chef1111` (also chef2)
- `/login/admin/` — `admin` / `admin123` (POS admin summary)
- `/django-admin/` — same `admin` / `admin123` (Django admin; **admin role only**)

### Managing staff in `/django-admin/` (preferred day-to-day)
Use this instead of editing `seed_staff.py` when someone joins or leaves.

1. Sign in at `/django-admin/` as **admin** (must be Tandem role Admin — only that role gets `is_staff` / `is_superuser`).
2. **Users** → **Add user** → set username + password → Save.  
   Django’s add form may not keep a complete “Tandem role” inline until the user exists, so treat this as step one.
3. Open the user again (**Change user**). Under **Tandem role**, set **Role** (waiter / chef / admin) and **Display name** → Save.  
   On save, Django admin flags are synced automatically: only role **Admin** keeps `/django-admin/` access; waiters and chefs do not.
4. They can now sign in at `/login/waiter/` or `/login/chef/` (or `/login/admin/` for Admin).

**Offboard (do not delete the User):** uncheck **Active** on that same page and Save.  
Inactive accounts cannot use the custom `/login/<role>/` flow (`authenticate` rejects them). Past orders are unrelated to the User row and stay intact — deleting a User is unnecessary and riskier.

`python manage.py seed_staff` remains useful for **first-time bootstrap** (or resetting the six demo accounts), not for everyday hires.

### Staff handling a stuck table
Open tables are locked to the waiter who opened them (others can’t add items until the bill is closed). Billing/closing stays available to any waiter.

If a waiter’s phone dies mid-shift and a table is stuck: `/django-admin/` → **Orders** → find the open order → change or clear the **Waiter** field (list or detail) → Save. Clearing it lets the next waiter claim the table; assigning another waiter transfers the lock.

## Next (Day 3+)
- Swap in the real ~30 menu items/prices and real UPI VPA
- Deploy on a local device on Tandem's own WiFi (not a cloud VPS) for opening-week reliability
- Real-world test with actual waiter + chef, on their actual phones
