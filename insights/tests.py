import sqlite3
import tempfile
import unittest
from pathlib import Path

from insights import build_analytics_db as build

SOURCE_DDL = """
CREATE TABLE orders_table (id INTEGER PRIMARY KEY, number INTEGER, name TEXT);
CREATE TABLE orders_menuitem (id INTEGER PRIMARY KEY, name TEXT, category TEXT, price DECIMAL, is_active BOOL);
CREATE TABLE orders_staffprofile (id INTEGER PRIMARY KEY, user_id INTEGER, role TEXT, display_name TEXT);
CREATE TABLE orders_order (
    id INTEGER PRIMARY KEY, table_id INTEGER, waiter_id INTEGER, status TEXT,
    created_at TEXT, closed_at TEXT, payment_method TEXT, discount_percent DECIMAL,
    discount_amount DECIMAL, customer_name TEXT, customer_phone TEXT, marketing_opt_in BOOL
);
CREATE TABLE orders_orderitem (
    id INTEGER PRIMARY KEY, order_id INTEGER, menu_item_id INTEGER, quantity INTEGER,
    note TEXT, status TEXT, added_at TEXT, ready_at TEXT
);
CREATE TABLE auth_user (id INTEGER PRIMARY KEY, username TEXT, password TEXT, email TEXT);
CREATE TABLE django_session (session_key TEXT, session_data TEXT);

INSERT INTO orders_table VALUES (1, 1, ''), (2, 2, '');
INSERT INTO orders_menuitem VALUES (1, 'Tea', 'tea_coffee', 40, 1), (2, 'Maggi', 'maggi', 99, 1);
INSERT INTO orders_staffprofile VALUES (1, 5, 'waiter', 'Asha');
INSERT INTO auth_user VALUES (5, 'asha', 'pbkdf2$secret-hash', 'asha@example.com');
INSERT INTO django_session VALUES ('abc', 'secret-session');

-- #1 closed cash, 3 x Tea = 120, 10% off -> 108. 10:30 UTC = 16:00 IST
INSERT INTO orders_order VALUES
 (1, 1, 5, 'closed', '2026-10-01 10:30:00.000000', '2026-10-01 11:00:00.000000',
  'cash', 10, 12, 'Ravi Kumar', '+91 98765 43210', 1);
-- #2 closed upi, 1 x Maggi = 99, same phone written differently
INSERT INTO orders_order VALUES
 (2, 2, 5, 'closed', '2026-10-01 12:00:00.000000', '2026-10-01 12:20:00.000000',
  'upi', 0, 0, '', '09876543210', 0);
-- #3 still open
INSERT INTO orders_order VALUES
 (3, 1, 5, 'open', '2026-10-02 05:00:00.000000', NULL, '', 0, 0, '', '', 0);

INSERT INTO orders_orderitem VALUES
 (1, 1, 1, 3, 'less sugar', 'ready', '2026-10-01 10:31:00.000000', '2026-10-01 10:37:00.000000'),
 (2, 2, 2, 1, '', 'ready', '2026-10-01 12:01:00.000000', '2026-10-01 12:11:00.000000'),
 (3, 3, 1, 1, '', 'pending', '2026-10-02 05:01:00.000000', NULL);
"""


class BuildAnalyticsDbTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.src = self.dir / "source.sqlite3"
        con = sqlite3.connect(self.src)
        con.executescript(SOURCE_DDL)
        con.commit()
        con.close()
        self.dest = self.dir / "out" / "analytics.db"
        self.salt_file = self.dir / "secret" / "salt"

    def run_build(self):
        build.main(
            ["--src", str(self.src), "--dest", str(self.dest), "--salt-file", str(self.salt_file)]
        )
        con = sqlite3.connect(self.dest)
        con.row_factory = sqlite3.Row
        self.addCleanup(con.close)
        return con

    def test_no_sensitive_tables_or_columns(self):
        con = self.run_build()
        names = {r[0] for r in con.execute("SELECT name FROM sqlite_master")}
        self.assertNotIn("auth_user", names)
        self.assertNotIn("django_session", names)
        for table in ("orders", "order_items", "staff", "menu_items", "dining_tables"):
            cols = {r[1] for r in con.execute(f"PRAGMA table_info({table})")}
            self.assertFalse({"customer_name", "customer_phone", "password", "email"} & cols)

    def test_phone_and_name_never_appear_in_any_value(self):
        con = self.run_build()
        for (table,) in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall():
            for row in con.execute(f"SELECT * FROM {table}"):
                for value in row:
                    text = str(value)
                    self.assertNotIn("9876543210", text)
                    self.assertNotIn("Ravi", text)
                    self.assertNotIn("secret", text)

    def test_order_math_and_ist_time(self):
        con = self.run_build()
        o = con.execute("SELECT * FROM orders WHERE id = 1").fetchone()
        self.assertEqual(o["subtotal"], 120)
        self.assertEqual(o["discount_amount"], 12)
        self.assertEqual(o["total"], 108)
        self.assertEqual(o["table_number"], 1)
        self.assertEqual(o["waiter_name"], "Asha")
        self.assertEqual(o["payment_method"], "cash")
        self.assertEqual(o["closed_at_ist"], "2026-10-01 16:30:00")
        self.assertEqual(o["hour_ist"], 16)
        self.assertEqual(o["date_ist"], "2026-10-01")
        self.assertEqual(o["minutes_open"], 30.0)

    def test_same_customer_gets_same_id_regardless_of_phone_format(self):
        con = self.run_build()
        ids = [r["customer_id"] for r in con.execute("SELECT customer_id FROM orders WHERE id IN (1, 2)")]
        self.assertEqual(len(set(ids)), 1)
        self.assertEqual(len(ids[0]), 12)
        self.assertIsNone(con.execute("SELECT customer_id FROM orders WHERE id = 3").fetchone()[0])
        visits = con.execute("SELECT visits FROM repeat_customers").fetchone()[0]
        self.assertEqual(visits, 2)

    def test_customer_id_is_stable_across_rebuilds_but_depends_on_salt(self):
        first = self.run_build().execute("SELECT customer_id FROM orders WHERE id = 1").fetchone()[0]
        second = self.run_build().execute("SELECT customer_id FROM orders WHERE id = 1").fetchone()[0]
        self.assertEqual(first, second)
        self.salt_file.unlink()
        third = self.run_build().execute("SELECT customer_id FROM orders WHERE id = 1").fetchone()[0]
        self.assertNotEqual(first, third)

    def test_summary_views_only_count_closed_bills(self):
        con = self.run_build()
        d = con.execute("SELECT * FROM daily_sales").fetchall()
        self.assertEqual(len(d), 1)  # the open order on 2026-10-02 is excluded
        self.assertEqual(d[0]["bills"], 2)
        self.assertEqual(d[0]["revenue"], 207)
        self.assertEqual(d[0]["cash_revenue"], 108)
        self.assertEqual(d[0]["upi_revenue"], 99)
        self.assertEqual(con.execute("SELECT qty_sold FROM item_sales WHERE item_name = 'Tea'").fetchone()[0], 3)

    def test_kitchen_minutes(self):
        con = self.run_build()
        row = con.execute("SELECT avg_minutes FROM kitchen_speed WHERE item_name = 'Tea'").fetchone()
        self.assertEqual(row[0], 6.0)

    def test_source_database_is_not_modified(self):
        before = self.src.read_bytes()
        self.run_build()
        self.assertEqual(before, self.src.read_bytes())


if __name__ == "__main__":
    unittest.main()
