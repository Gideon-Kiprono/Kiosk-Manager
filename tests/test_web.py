import unittest

from kiosk import services
from kiosk.db import get_connection
from kiosk.web import create_app


class WebTests(unittest.TestCase):
    def setUp(self):
        import tempfile, os
        self.dir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.dir.name, "t.db")
        self.app = create_app(self.path, testing=True)
        self.client = self.app.test_client()
        conn = get_connection(self.path)
        services.add_or_restock(conn, "books", 15, price=80)
        services.add_or_restock(conn, "pen", 3, price=65)
        conn.close()

    def tearDown(self):
        self.dir.cleanup()

    def test_pages_load_in_swahili(self):
        for url, word in [("/", "Bidhaa zilizopo"), ("/uza", "Uza bidhaa"),
                          ("/ongeza", "Ongeza au jaza stoo"), ("/ripoti", "Ripoti ya mauzo")]:
            r = self.client.get(url)
            self.assertEqual(r.status_code, 200)
            self.assertIn(word, r.get_data(as_text=True))

    def test_low_stock_tag(self):
        self.assertIn("Inaisha", self.client.get("/").get_data(as_text=True))

    def test_search(self):
        html = self.client.get("/?q=boo").get_data(as_text=True)
        self.assertIn("Books", html)
        self.assertNotIn("Pen", html.split("<tbody>")[1])

    def test_sell_success_and_report(self):
        r = self.client.post("/uza", data={"product": "Books", "quantity": "5"}, follow_redirects=True)
        self.assertIn("Umeuza 5 Books kwa KES 400", r.get_data(as_text=True))
        report = self.client.get("/ripoti").get_data(as_text=True)
        self.assertIn("KES 400", report)

    def test_oversell_shows_swahili_error(self):
        r = self.client.post("/uza", data={"product": "Pen", "quantity": "99"}, follow_redirects=True)
        self.assertIn("Stoo haitoshi. Zimebaki 3 tu.", r.get_data(as_text=True))

    def test_bad_quantity_shows_error_not_crash(self):
        r = self.client.post("/uza", data={"product": "Pen", "quantity": "abc"}, follow_redirects=True)
        self.assertEqual(r.status_code, 200)
        self.assertIn("Idadi lazima", r.get_data(as_text=True))

    def test_add_new_needs_price_then_succeeds(self):
        r = self.client.post("/ongeza", data={"name": "chai", "quantity": "10", "price": ""}, follow_redirects=True)
        self.assertIn("ni bidhaa mpya, weka bei", r.get_data(as_text=True))
        r = self.client.post("/ongeza", data={"name": "chai", "quantity": "10", "price": "50"}, follow_redirects=True)
        self.assertIn("Chai imeongezwa", r.get_data(as_text=True))

    def test_restock(self):
        r = self.client.post("/ongeza", data={"name": "pen", "quantity": "7"}, follow_redirects=True)
        self.assertIn("Pen imejazwa. Idadi mpya: 10", r.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
