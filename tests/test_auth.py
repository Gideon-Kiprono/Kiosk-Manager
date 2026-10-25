import os
import shutil
import tempfile
import unittest

from kiosk import auth, services
from kiosk.db import get_connection, init_db
from kiosk.services import KioskError


class AuthTests(unittest.TestCase):
    def setUp(self):
        self.conn = get_connection(":memory:")
        init_db(self.conn)

    def tearDown(self):
        self.conn.close()

    def test_register_and_login(self):
        uid = auth.register(self.conn, "  Ann@Example.COM ", "password123", "Ann's Kiosk")
        user = auth.authenticate(self.conn, "ann@example.com", "password123")
        self.assertEqual(user["id"], uid)
        self.assertEqual(user["kiosk_name"], "Ann's Kiosk")

    def test_password_is_hashed(self):
        auth.register(self.conn, "a@example.com", "password123", "K")
        stored = self.conn.execute("SELECT password_hash FROM users").fetchone()[0]
        self.assertNotIn("password123", stored)

    def test_bad_inputs_rejected(self):
        cases = [("not-an-email", "password123", "K", "invalid_email"),
                 ("a@example.com", "short", "K", "weak_password"),
                 ("a@example.com", "password123", "   ", "invalid_kiosk_name")]
        for email, pw, kiosk, code in cases:
            with self.subTest(code=code), self.assertRaises(KioskError) as ctx:
                auth.register(self.conn, email, pw, kiosk)
            self.assertEqual(ctx.exception.code, code)

    def test_duplicate_email(self):
        auth.register(self.conn, "a@example.com", "password123", "K")
        with self.assertRaises(KioskError) as ctx:
            auth.register(self.conn, "A@example.com", "password123", "K2")
        self.assertEqual(ctx.exception.code, "email_taken")

    def test_wrong_password_and_unknown_email_give_same_error(self):
        auth.register(self.conn, "a@example.com", "password123", "K")
        for email, pw in [("a@example.com", "wrongpass1"), ("nobody@example.com", "password123")]:
            with self.assertRaises(KioskError) as ctx:
                auth.authenticate(self.conn, email, pw)
            self.assertEqual(ctx.exception.code, "bad_login")

    def test_first_real_account_claims_imported_stock(self):
        self.conn.execute("INSERT INTO products (user_id, name, price, quantity) VALUES (NULL, 'Pen', 65, 20)")
        self.conn.commit()
        first = auth.register(self.conn, "a@example.com", "password123", "K")
        second = auth.register(self.conn, "b@example.com", "password123", "K2")
        self.assertEqual(len(services.list_products(self.conn, first)), 1)
        self.assertEqual(services.list_products(self.conn, second), [])

    def test_demo_does_not_claim_stock_and_has_sample_data(self):
        self.conn.execute("INSERT INTO products (user_id, name, price, quantity) VALUES (NULL, 'Pen', 65, 20)")
        self.conn.commit()
        demo = auth.create_demo(self.conn)
        self.assertEqual(self.conn.execute(
            "SELECT count(*) FROM products WHERE user_id IS NULL").fetchone()[0], 1)
        self.assertGreater(services.sales_report(self.conn, demo)["revenue"], 0)

    def test_old_demos_are_purged(self):
        demo = auth.create_demo(self.conn)
        self.conn.execute("UPDATE users SET created_at = datetime('now', '-30 hours') WHERE id = ?", (demo,))
        self.conn.commit()
        auth.purge_old_demos(self.conn)
        self.assertIsNone(auth.get_user(self.conn, demo))
        self.assertEqual(services.list_products(self.conn, demo), [])


class ChartTests(unittest.TestCase):
    def test_chart_has_one_bar_per_day_and_labels_peak_once(self):
        from kiosk import chart
        days = [{"date": f"2026-10-{19 + i}", "revenue": r, "units": 1}
                for i, r in enumerate([0, 500, 1200, 0, 1200, 300, 80])]
        svg = str(chart.sales_bars(days, "Test"))
        self.assertEqual(svg.count('class="bar"'), 7)
        self.assertEqual(svg.count('class="value-text"'), 1)
        self.assertEqual(svg.count('class="mark"'), 5)           # zero days draw no bar
        self.assertEqual(str(chart.sales_bars(days[:1], "Test")), "")   # no sales: no chart

    def test_nice_ticks(self):
        from kiosk import chart
        self.assertEqual(chart.nice_ticks(1320), [0, 500, 1000, 1500])
        self.assertEqual(chart.nice_ticks(7)[0], 0)
        self.assertGreaterEqual(chart.nice_ticks(7)[-1], 7)


class MigrationTests(unittest.TestCase):
    def test_stage3_database_gets_archived_column(self):
        c = get_connection(":memory:")
        c.executescript("""
            CREATE TABLE users (id INTEGER PRIMARY KEY, email TEXT, password_hash TEXT, kiosk_name TEXT,
                is_demo INTEGER DEFAULT 0, created_at TEXT DEFAULT (datetime('now')));
            CREATE TABLE products (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, name TEXT NOT NULL,
                price INTEGER NOT NULL, quantity INTEGER NOT NULL, UNIQUE (user_id, name));
            CREATE TABLE sales (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, product_id INTEGER NOT NULL,
                product_name TEXT NOT NULL, quantity INTEGER NOT NULL, total INTEGER NOT NULL,
                sold_at TEXT NOT NULL DEFAULT (datetime('now')));
            INSERT INTO products (user_id, name, price, quantity) VALUES (1, 'Pen', 65, 5);
        """)
        init_db(c)
        self.assertEqual(c.execute("SELECT archived FROM products").fetchone()[0], 0)
        c.close()

    def test_stage2_database_is_upgraded_without_losing_data(self):
        tmp = tempfile.mkdtemp()
        try:
            path = os.path.join(tmp, "old.db")
            old = get_connection(path)
            old.executescript("""
                CREATE TABLE products (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE,
                    price INTEGER NOT NULL CHECK (price > 0), quantity INTEGER NOT NULL CHECK (quantity >= 0));
                CREATE TABLE sales (id INTEGER PRIMARY KEY AUTOINCREMENT, product_id INTEGER NOT NULL REFERENCES products(id),
                    product_name TEXT NOT NULL, quantity INTEGER NOT NULL, total INTEGER NOT NULL,
                    sold_at TEXT NOT NULL DEFAULT (datetime('now')));
                INSERT INTO products (name, price, quantity) VALUES ('Books', 80, 10), ('Pen', 65, 5);
                INSERT INTO sales (product_id, product_name, quantity, total) VALUES (1, 'Books', 2, 160);
            """)
            old.commit()
            init_db(old)
            self.assertEqual(old.execute("SELECT count(*) FROM products").fetchone()[0], 2)
            self.assertEqual(old.execute("SELECT count(*) FROM sales").fetchone()[0], 1)
            self.assertEqual(old.execute("PRAGMA foreign_key_check").fetchall(), [])
            uid = auth.register(old, "a@example.com", "password123", "K")
            self.assertEqual(services.sales_report(old, uid)["revenue"], 160)
            old.close()
        finally:
            shutil.rmtree(tmp)


if __name__ == "__main__":
    unittest.main()
