import unittest

from kiosk import auth, services
from kiosk.db import get_connection, init_db
from kiosk.services import KioskError


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.conn = get_connection(":memory:")      # fresh empty database per test
        init_db(self.conn)
        self.uid = auth.register(self.conn, "owner@example.com", "password123", "Test Kiosk")
        services.add_or_restock(self.conn, self.uid, "pen", 20, price=65)
        services.add_or_restock(self.conn, self.uid, "books", 15, price=80)

    def tearDown(self):
        self.conn.close()

    def qty(self, name):
        return services.get_product(self.conn, self.uid, name)["quantity"]

    def test_names_are_cleaned(self):
        self.assertEqual(services.get_product(self.conn, self.uid, "  PEN ")["name"], "Pen")

    def test_restock_existing_adds_units(self):
        action, product = services.add_or_restock(self.conn, self.uid, "pen", 5)
        self.assertEqual((action, product["quantity"]), ("restocked", 25))

    def test_new_product_needs_price(self):
        with self.assertRaises(KioskError):
            services.add_or_restock(self.conn, self.uid, "chai", 10)

    def test_sell_reduces_stock_and_records_sale(self):
        result = services.sell(self.conn, self.uid, "books", "5")
        self.assertEqual(result["total"], 400)
        self.assertEqual(self.qty("books"), 10)

    def test_cannot_oversell(self):
        with self.assertRaises(KioskError):
            services.sell(self.conn, self.uid, "pen", 99)
        self.assertEqual(self.qty("pen"), 20)          # unchanged

    def test_bad_quantities_rejected(self):
        for bad in ["abc", "0", "-3", "", "2.5"]:
            with self.subTest(bad=bad), self.assertRaises(KioskError):
                services.sell(self.conn, self.uid, "pen", bad)

    def test_unknown_product(self):
        with self.assertRaises(KioskError):
            services.sell(self.conn, self.uid, "ghost", 1)

    def test_search_is_partial_and_case_insensitive(self):
        self.assertEqual([p["name"] for p in services.search_products(self.conn, self.uid, "BOO")], ["Books"])
        self.assertEqual(services.search_products(self.conn, self.uid, "zzz"), [])

    def test_report_matches_hand_calculation(self):
        services.sell(self.conn, self.uid, "books", 5)       # 400
        services.sell(self.conn, self.uid, "pen", 2)         # 130
        services.sell(self.conn, self.uid, "books", 1)       # 80
        report = services.sales_report(self.conn, self.uid)
        self.assertEqual(report["revenue"], 610)
        self.assertEqual(report["unique_products"], 2)
        self.assertEqual(report["best_seller"], ("Books", 6))

    def test_one_kiosk_cannot_see_or_sell_anothers_stock(self):
        other = auth.register(self.conn, "other@example.com", "password123", "Other Kiosk")
        self.assertEqual(services.list_products(self.conn, other), [])
        with self.assertRaises(KioskError):
            services.sell(self.conn, other, "pen", 1)
        services.add_or_restock(self.conn, other, "pen", 4, price=99)       # same name, own row
        self.assertEqual(services.get_product(self.conn, other, "pen")["price"], 99)
        self.assertEqual(services.get_product(self.conn, self.uid, "pen")["price"], 65)
        services.sell(self.conn, other, "pen", 2)
        self.assertEqual(services.sales_report(self.conn, self.uid)["revenue"], 0)
        self.assertEqual(services.sales_report(self.conn, other)["revenue"], 198)

    def test_daily_sales_fills_missing_days_with_zero(self):
        services.sell(self.conn, self.uid, "books", 2)
        self.conn.execute("UPDATE sales SET sold_at = '2026-10-23 10:00:00'")      # a known day (UTC)
        self.conn.commit()
        days = services.daily_sales(self.conn, self.uid, "2026-10-25", days=4, tz_hours=3)
        self.assertEqual([d["date"] for d in days],
                         ["2026-10-22", "2026-10-23", "2026-10-24", "2026-10-25"])
        self.assertEqual([d["revenue"] for d in days], [0, 160, 0, 0])

    def test_daily_sales_uses_local_midnight(self):
        services.sell(self.conn, self.uid, "pen", 1)
        self.conn.execute("UPDATE sales SET sold_at = '2026-10-24 22:30:00'")      # 01:30 on the 25th in Nairobi
        self.conn.commit()
        days = services.daily_sales(self.conn, self.uid, "2026-10-25", days=2, tz_hours=3)
        self.assertEqual([d["revenue"] for d in days], [0, 65])

    def test_update_product_validates(self):
        pid = services.get_product(self.conn, self.uid, "pen")["id"]
        updated = services.update_product(self.conn, self.uid, pid, "red pen", "70", "0")
        self.assertEqual((updated["name"], updated["price"], updated["quantity"]), ("Red Pen", 70, 0))
        with self.assertRaises(KioskError):
            services.update_product(self.conn, self.uid, pid, "Books", "70", "1")      # name taken
        with self.assertRaises(KioskError):
            services.update_product(self.conn, self.uid, pid, "Red Pen", "0", "1")     # bad price

    def test_removed_product_is_hidden_but_sales_remain(self):
        services.sell(self.conn, self.uid, "pen", 2)
        pid = services.get_product(self.conn, self.uid, "pen")["id"]
        services.remove_product(self.conn, self.uid, pid)
        self.assertNotIn("Pen", [p["name"] for p in services.list_products(self.conn, self.uid)])
        with self.assertRaises(KioskError):
            services.sell(self.conn, self.uid, "pen", 1)
        self.assertEqual(services.sales_report(self.conn, self.uid)["revenue"], 130)

    def test_csv_export_is_oldest_first_and_safe(self):
        services.add_or_restock(self.conn, self.uid, "@home", 5, price=10)
        services.sell(self.conn, self.uid, "pen", 1)
        services.sell(self.conn, self.uid, "@home", 1)
        lines = services.export_sales_csv(self.conn, self.uid).strip().split("\r\n")
        self.assertEqual(len(lines), 3)
        self.assertIn("Pen", lines[1])
        self.assertIn("'@Home", lines[2])

    def test_empty_report(self):
        report = services.sales_report(self.conn, self.uid)
        self.assertEqual(report["revenue"], 0)
        self.assertIsNone(report["best_seller"])

    def test_low_stock(self):
        services.sell(self.conn, self.uid, "pen", 17)
        self.assertEqual([p["name"] for p in services.low_stock(self.conn, self.uid)], ["Pen"])


if __name__ == "__main__":
    unittest.main()
