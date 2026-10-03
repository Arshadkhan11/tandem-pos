#!/usr/bin/env python3
"""Build a sanitized, analytics-friendly copy of Tandem's SQLite database.

The copy is what Datasette serves. It deliberately contains NO customer names,
NO phone numbers (only a salted one-way hash so repeat visits can be counted),
and none of Django's auth/session tables (password hashes, session keys).

Standard library only, so it runs with the system python3.

    python3 build_analytics_db.py --src /opt/tandem/db.sqlite3 \
        --dest /opt/analytics/data/tandem_analytics.db \
        --salt-file /opt/analytics/secret/phone_salt
"""
import argparse
import hashlib
import os
import secrets
import sqlite3
import sys
from pathlib import Path

CATEGORY_LABELS = {
    "tea_coffee": "Tea & Coffee",
    "maggi": "Maggi",
    "breakfast": "Sandwiches & Breakfast",
    "starters_veg": "Starters — Veg",
    "starters_nonveg": "Starters — Non-Veg",
    "fries": "Fries & Wedges",
    "rice_veg": "Rice, Noodles & Pasta — Veg",
    "rice_nonveg": "Rice, Noodles & Pasta — Non-Veg",
    "beverages": "Refreshers & Soft Drinks",
    "ice_signature": "Ice Creams — Signature",
    "ice_classic": "Ice Creams — Classic",
    "milkshakes": "Milkshakes",
}

# Django stores UTC; the restaurant runs on IST (UTC+5:30).
IST = "'+5 hours', '+30 minutes'"

SCHEMA_SQL = f"""
CREATE TABLE dining_tables AS
SELECT id, number AS table_number, name
FROM src.orders_table;

CREATE TABLE menu_items AS
SELECT id, name, category, category_label(category) AS category_label,
       ROUND(price, 2) AS price, is_active
FROM src.orders_menuitem;

CREATE TABLE staff AS
SELECT user_id, display_name, role
FROM src.orders_staffprofile;

CREATE TABLE orders AS
WITH totals AS (
    SELECT oi.order_id AS order_id,
           SUM(oi.quantity) AS item_count,
           ROUND(SUM(oi.quantity * mi.price), 2) AS subtotal
    FROM src.orders_orderitem oi
    JOIN src.orders_menuitem mi ON mi.id = oi.menu_item_id
    GROUP BY oi.order_id
),
base AS (
    SELECT o.id AS id,
           t.number AS table_number,
           o.waiter_id AS waiter_id,
           sp.display_name AS waiter_name,
           o.status AS status,
           NULLIF(o.payment_method, '') AS payment_method,
           o.discount_percent AS discount_percent,
           COALESCE(tt.subtotal, 0) AS subtotal,
           COALESCE(tt.item_count, 0) AS item_count,
           CASE WHEN o.status = 'closed' THEN o.discount_amount
                ELSE ROUND(COALESCE(tt.subtotal, 0) * o.discount_percent / 100.0, 2)
           END AS discount_amount,
           o.created_at AS created_at,
           o.closed_at AS closed_at,
           o.customer_phone AS customer_phone,
           o.marketing_opt_in AS marketing_opt_in
    FROM src.orders_order o
    JOIN src.orders_table t ON t.id = o.table_id
    LEFT JOIN src.orders_staffprofile sp ON sp.user_id = o.waiter_id
    LEFT JOIN totals tt ON tt.order_id = o.id
)
SELECT id, table_number, waiter_id, waiter_name, status, payment_method,
       discount_percent, subtotal, discount_amount,
       ROUND(subtotal - discount_amount, 2) AS total,
       item_count,
       datetime(created_at, {IST}) AS created_at_ist,
       datetime(closed_at, {IST}) AS closed_at_ist,
       date(COALESCE(closed_at, created_at), {IST}) AS date_ist,
       CAST(strftime('%H', COALESCE(closed_at, created_at), {IST}) AS INTEGER) AS hour_ist,
       CASE strftime('%w', COALESCE(closed_at, created_at), {IST})
            WHEN '0' THEN 'Sun' WHEN '1' THEN 'Mon' WHEN '2' THEN 'Tue'
            WHEN '3' THEN 'Wed' WHEN '4' THEN 'Thu' WHEN '5' THEN 'Fri'
            ELSE 'Sat' END AS weekday,
       CAST(strftime('%w', COALESCE(closed_at, created_at), {IST}) AS INTEGER) AS weekday_num,
       CASE WHEN closed_at IS NOT NULL
            THEN ROUND((julianday(closed_at) - julianday(created_at)) * 1440, 1)
       END AS minutes_open,
       CASE WHEN customer_phone <> '' THEN phone_hash(customer_phone) END AS customer_id,
       customer_phone <> '' AS has_phone,
       marketing_opt_in
FROM base;

CREATE TABLE order_items AS
SELECT oi.id AS id,
       oi.order_id AS order_id,
       oi.menu_item_id AS menu_item_id,
       mi.name AS item_name,
       mi.category AS category,
       category_label(mi.category) AS category_label,
       oi.quantity AS quantity,
       ROUND(mi.price, 2) AS unit_price,
       ROUND(oi.quantity * mi.price, 2) AS line_total,
       NULLIF(oi.note, '') AS note,
       oi.status AS status,
       datetime(oi.added_at, {IST}) AS added_at_ist,
       datetime(oi.ready_at, {IST}) AS ready_at_ist,
       CASE WHEN oi.ready_at IS NOT NULL
            THEN ROUND((julianday(oi.ready_at) - julianday(oi.added_at)) * 1440, 1)
       END AS kitchen_minutes,
       o.table_number AS table_number,
       o.waiter_name AS waiter_name,
       o.status AS order_status,
       o.date_ist AS date_ist
FROM src.orders_orderitem oi
JOIN src.orders_menuitem mi ON mi.id = oi.menu_item_id
JOIN orders o ON o.id = oi.order_id;

CREATE INDEX idx_orders_date ON orders(date_ist);
CREATE INDEX idx_items_order ON order_items(order_id);

CREATE VIEW daily_sales AS
SELECT date_ist AS date,
       COUNT(*) AS bills,
       SUM(item_count) AS items_sold,
       ROUND(SUM(subtotal), 2) AS gross_sales,
       ROUND(SUM(discount_amount), 2) AS discounts,
       ROUND(SUM(total), 2) AS revenue,
       ROUND(SUM(CASE WHEN payment_method = 'cash' THEN total ELSE 0 END), 2) AS cash_revenue,
       ROUND(SUM(CASE WHEN payment_method = 'upi' THEN total ELSE 0 END), 2) AS upi_revenue,
       ROUND(AVG(total), 2) AS avg_bill
FROM orders
WHERE status = 'closed'
GROUP BY date_ist
ORDER BY date_ist DESC;

CREATE VIEW hourly_sales AS
SELECT hour_ist AS hour,
       COUNT(*) AS bills,
       ROUND(SUM(total), 2) AS revenue
FROM orders
WHERE status = 'closed'
GROUP BY hour_ist
ORDER BY hour_ist;

CREATE VIEW weekday_sales AS
SELECT weekday,
       COUNT(*) AS bills,
       ROUND(SUM(total), 2) AS revenue,
       ROUND(AVG(total), 2) AS avg_bill
FROM orders
WHERE status = 'closed'
GROUP BY weekday_num
ORDER BY weekday_num;

CREATE VIEW item_sales AS
SELECT item_name,
       category_label,
       SUM(quantity) AS qty_sold,
       ROUND(SUM(line_total), 2) AS gross_revenue,
       COUNT(DISTINCT order_id) AS in_bills
FROM order_items
WHERE order_status = 'closed'
GROUP BY menu_item_id
ORDER BY qty_sold DESC;

CREATE VIEW waiter_performance AS
SELECT COALESCE(waiter_name, '(unknown)') AS waiter,
       COUNT(*) AS bills,
       ROUND(SUM(total), 2) AS revenue,
       ROUND(AVG(total), 2) AS avg_bill,
       ROUND(SUM(discount_amount), 2) AS discounts_given,
       ROUND(100.0 * SUM(CASE WHEN discount_percent > 0 THEN 1 ELSE 0 END) / COUNT(*), 1)
           AS pct_bills_discounted
FROM orders
WHERE status = 'closed'
GROUP BY waiter_id
ORDER BY revenue DESC;

CREATE VIEW kitchen_speed AS
SELECT item_name,
       category_label,
       COUNT(*) AS items,
       ROUND(AVG(kitchen_minutes), 1) AS avg_minutes,
       ROUND(MAX(kitchen_minutes), 1) AS max_minutes
FROM order_items
WHERE kitchen_minutes IS NOT NULL
GROUP BY menu_item_id
ORDER BY avg_minutes DESC;

CREATE VIEW payment_split AS
SELECT payment_method,
       COUNT(*) AS bills,
       ROUND(SUM(total), 2) AS revenue
FROM orders
WHERE status = 'closed'
GROUP BY payment_method;

CREATE VIEW repeat_customers AS
SELECT customer_id,
       COUNT(*) AS visits,
       ROUND(SUM(total), 2) AS total_spent,
       MIN(date_ist) AS first_visit,
       MAX(date_ist) AS last_visit
FROM orders
WHERE status = 'closed' AND customer_id IS NOT NULL
GROUP BY customer_id
ORDER BY visits DESC;

CREATE TABLE refresh_info AS
SELECT datetime('now', {IST}) AS refreshed_at_ist,
       (SELECT COUNT(*) FROM orders) AS orders,
       (SELECT COUNT(*) FROM order_items) AS order_items,
       (SELECT MIN(date_ist) FROM orders) AS first_order_date,
       (SELECT MAX(date_ist) FROM orders) AS last_order_date;
"""


def load_salt(path):
    """Return the secret salt, creating it (mode 0600) on first run."""
    p = Path(path)
    if p.exists():
        return p.read_text().strip()
    p.parent.mkdir(parents=True, exist_ok=True)
    salt = secrets.token_hex(32)
    fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(salt)
    return salt


def make_phone_hasher(salt):
    def phone_hash(raw):
        digits = "".join(c for c in (raw or "") if c.isdigit())
        if len(digits) < 10:
            return None
        # Last 10 digits so "+91 98765 43210" and "09876543210" match.
        return hashlib.sha256((salt + digits[-10:]).encode()).hexdigest()[:12]

    return phone_hash


def build(src, dest, salt):
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.parent / (dest.name + ".tmp")
    for stale in (tmp, dest.parent / (dest.name + ".tmp-journal")):
        if stale.exists():
            stale.unlink()

    con = sqlite3.connect(str(tmp), uri=True)
    try:
        con.create_function("phone_hash", 1, make_phone_hasher(salt), deterministic=True)
        con.create_function(
            "category_label", 1, lambda c: CATEGORY_LABELS.get(c, c), deterministic=True
        )
        src_uri = Path(src).resolve().as_uri() + "?mode=ro"
        con.execute("ATTACH DATABASE ? AS src", (src_uri,))
        con.executescript(SCHEMA_SQL)
        con.execute("DETACH DATABASE src")
        if con.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("integrity_check failed on the new analytics database")
        counts = {
            t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            for t in ("dining_tables", "menu_items", "staff", "orders", "order_items")
        }
    finally:
        con.close()

    os.chmod(tmp, 0o640)
    os.replace(tmp, dest)
    return counts


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--src", required=True, help="Tandem's live db.sqlite3 (opened read-only)")
    ap.add_argument("--dest", required=True, help="where to write the sanitized copy")
    ap.add_argument("--salt-file", required=True, help="secret salt used to hash phone numbers")
    args = ap.parse_args(argv)

    if not Path(args.src).exists():
        sys.exit(f"source database not found: {args.src}")
    counts = build(args.src, args.dest, load_salt(args.salt_file))
    print("analytics db rebuilt:", ", ".join(f"{k}={v}" for k, v in counts.items()))


if __name__ == "__main__":
    main()
