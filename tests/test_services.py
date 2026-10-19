import unittest

from kiosk import services
from kiosk.db import get_connection, init_db
from kiosk.services import KioskError


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.conn = get_connection(":memory:")      # fresh empty database per test
        init_db(self.conn)
        services.add_or_restock(self.conn, "pen", 20, price=65)
        services.add_or_restock(self.conn, "books", 15, price=80)

    def qty(self, name):
        return services.get_product(self.conn, name)["quantity"]

    def test_names_are_cleaned(self):
        self.assertEqual(services.get_product(self.conn, "  PEN ")["name"], "Pen")

    def test_restock_existing_adds_units(self):
        action, product = services.add_or_restock(self.conn, "pen", 5)
        self.assertEqual((action, product["quantity"]), ("restocked", 25))

    def test_new_product_needs_price(self):
        with self.assertRaises(KioskError):
            services.add_or_restock(self.conn, "chai", 10)

    def test_sell_reduces_stock_and_records_sale(self):
        result = services.sell(self.conn, "books", "5")
        self.assertEqual(result["total"], 400)
        self.assertEqual(self.qty("books"), 10)

    def test_cannot_oversell(self):
        with self.assertRaises(KioskError):
            services.sell(self.conn, "pen", 99)
        self.assertEqual(self.qty("pen"), 20)          # unchanged

    def test_bad_quantities_rejected(self):
        for bad in ["abc", "0", "-3", "", "2.5"]:
            with self.subTest(bad=bad), self.assertRaises(KioskError):
                services.sell(self.conn, "pen", bad)

    def test_unknown_product(self):
        with self.assertRaises(KioskError):
            services.sell(self.conn, "ghost", 1)

    def test_search_is_partial_and_case_insensitive(self):
        self.assertEqual([p["name"] for p in services.search_products(self.conn, "BOO")], ["Books"])
        self.assertEqual(services.search_products(self.conn, "zzz"), [])

    def test_report_matches_hand_calculation(self):
        services.sell(self.conn, "books", 5)       # 400
        services.sell(self.conn, "pen", 2)         # 130
        services.sell(self.conn, "books", 1)       # 80
        report = services.sales_report(self.conn)
        self.assertEqual(report["revenue"], 610)
        self.assertEqual(report["unique_products"], 2)
        self.assertEqual(report["best_seller"], ("Books", 6))

    def test_empty_report(self):
        report = services.sales_report(self.conn)
        self.assertEqual(report["revenue"], 0)
        self.assertIsNone(report["best_seller"])

    def test_low_stock(self):
        services.sell(self.conn, "pen", 17)
        self.assertEqual([p["name"] for p in services.low_stock(self.conn)], ["Pen"])


if __name__ == "__main__":
    unittest.main()
