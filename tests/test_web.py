import os
import re
import tempfile
import unittest

from kiosk.web import create_app


class WebTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.app = create_app(os.path.join(self.dir.name, "t.db"), testing=True)
        self.client = self.app.test_client()

    def tearDown(self):
        self.dir.cleanup()

    # --- helpers ---
    def token(self, client=None):
        client = client or self.client
        client.get("/ingia")
        with client.session_transaction() as s:
            return s["csrf"]

    def post(self, url, data=None, client=None):
        client = client or self.client
        data = dict(data or {}, csrf_token=self.token(client))
        return client.post(url, data=data, follow_redirects=True)

    def text(self, resp):
        return resp.get_data(as_text=True)

    def signup(self, email="a@example.com", kiosk="Duka A", client=None):
        return self.post("/jisajili", {"email": email, "password": "password123",
                                       "kiosk_name": kiosk}, client)

    def stock_item(self, name, qty, price, client=None):
        return self.post("/ongeza", {"name": name, "quantity": qty, "price": price}, client)

    # --- access control ---
    def test_pages_require_login(self):
        for url in ["/", "/uza", "/ongeza", "/ripoti"]:
            r = self.client.get(url)
            self.assertEqual(r.status_code, 302, url)
            self.assertIn("/ingia", r.headers["Location"])

    def test_post_without_csrf_token_is_rejected(self):
        self.signup()
        r = self.client.post("/uza", data={"product": "Pen", "quantity": "1"}, follow_redirects=True)
        self.assertIn("Ombi halikuthibitishwa", self.text(r))

    # --- accounts ---
    def test_register_shows_welcome_and_kiosk_name(self):
        html = self.text(self.signup())
        self.assertIn("Karibu, Duka A!", html)
        self.assertIn("Mapato ya leo", html)

    def test_duplicate_and_weak_registration(self):
        self.signup()
        other = self.app.test_client()
        self.assertIn("tayari imesajiliwa", self.text(self.signup(client=other)))
        r = self.post("/jisajili", {"email": "b@example.com", "password": "123", "kiosk_name": "X"}, other)
        self.assertIn("angalau 8", self.text(r))

    def test_login_logout_cycle(self):
        self.signup()
        self.assertIn("Umetoka", self.text(self.post("/toka")))
        self.assertEqual(self.client.get("/").status_code, 302)
        r = self.post("/ingia", {"email": "a@example.com", "password": "password123"})
        self.assertIn("Karibu, Duka A!", self.text(r))

    def test_wrong_password_message(self):
        self.signup()
        self.post("/toka")
        r = self.post("/ingia", {"email": "a@example.com", "password": "nope-nope"})
        self.assertIn("si sahihi", self.text(r))

    def test_login_lockout_after_five_failures(self):
        self.signup()
        self.post("/toka")
        for _ in range(5):
            self.post("/ingia", {"email": "a@example.com", "password": "wrong-pass"})
        r = self.post("/ingia", {"email": "a@example.com", "password": "password123"})
        self.assertIn("Subiri dakika 15", self.text(r))

    def test_demo_account(self):
        html = self.text(self.post("/demo"))
        self.assertIn("Duka la Demo", html)
        self.assertIn("Mkate", self.text(self.client.get("/stoo")))

    # --- data isolation ---
    def test_kiosks_cannot_see_each_others_data(self):
        self.signup("a@example.com", "Duka A")
        self.stock_item("Pen", "10", "65")
        other = self.app.test_client()
        self.signup("b@example.com", "Duka B", client=other)
        self.assertNotIn("Pen", self.text(other.get("/stoo")))
        r = self.post("/uza", {"product": "Pen", "quantity": "1"}, other)
        self.assertIn("haipo kwenye stoo", self.text(r))
        self.assertIn("Pen", self.text(self.client.get("/stoo")))

    # --- the kiosk features (as before, now behind login) ---
    def test_sell_report_and_low_stock(self):
        self.signup()
        self.stock_item("Books", "15", "80")
        self.stock_item("Pen", "3", "65")
        self.assertIn("Inaisha", self.text(self.client.get("/stoo")))
        r = self.post("/uza", {"product": "Books", "quantity": "5"})
        self.assertIn("Umeuza 5 Books kwa KES 400", self.text(r))
        self.assertIn("KES 400", self.text(self.client.get("/ripoti")))

    def test_errors_are_swahili_not_crashes(self):
        self.signup()
        self.stock_item("Pen", "3", "65")
        self.assertIn("Zimebaki 3 tu", self.text(self.post("/uza", {"product": "Pen", "quantity": "99"})))
        self.assertIn("Idadi lazima", self.text(self.post("/uza", {"product": "Pen", "quantity": "abc"})))
        self.assertIn("weka bei", self.text(self.post("/ongeza", {"name": "Chai", "quantity": "5", "price": ""})))

    def test_search_and_restock(self):
        self.signup()
        self.stock_item("Books", "15", "80")
        self.stock_item("Pen", "3", "65")
        body = self.text(self.client.get("/stoo?q=boo")).split("<tbody>")[1]
        self.assertIn("Books", body)
        self.assertNotIn("Pen", body)
        self.assertIn("Idadi mpya: 10", self.text(self.post("/ongeza", {"name": "pen", "quantity": "7"})))

    # --- Stage 4 ---
    def product_id(self, name, client=None):
        import sqlite3
        conn = sqlite3.connect(self.app.config["DB_PATH"])
        try:
            return conn.execute("SELECT id FROM products WHERE name = ?", (name,)).fetchone()[0]
        finally:
            conn.close()

    def test_dashboard_shows_chart_hero_and_low_stock(self):
        self.signup()
        self.assertIn("Hakuna mauzo kwa siku 7", self.text(self.client.get("/")))       # empty state
        self.stock_item("Books", "15", "80")
        self.stock_item("Pen", "3", "65")
        self.post("/uza", {"product": "Books", "quantity": "5"})
        html = self.text(self.client.get("/"))
        self.assertIn("KES 400", html)                    # hero: today's revenue
        self.assertIn("<svg", html)
        self.assertIn("Zinaisha", html)
        self.assertIn("Pen", html.split("Zinaisha")[1])   # low-stock list
        self.assertIn("bidhaa=Pen", html)                 # refill link

    def test_edit_product(self):
        self.signup()
        self.stock_item("Pen", "3", "65")
        pid = self.product_id("Pen")
        r = self.post(f"/bidhaa/{pid}/hariri", {"name": "blue pen", "price": "70", "quantity": "9"})
        self.assertIn("Mabadiliko yamehifadhiwa", self.text(r))
        self.assertIn("Blue Pen", self.text(self.client.get("/stoo")))
        r = self.post(f"/bidhaa/{pid}/hariri", {"name": "Blue Pen", "price": "70", "quantity": "-1"})
        self.assertIn("namba nzima, 0 au zaidi", self.text(r))

    def test_edit_name_clash_rejected(self):
        self.signup()
        self.stock_item("Pen", "3", "65")
        self.stock_item("Books", "3", "80")
        r = self.post(f"/bidhaa/{self.product_id('Pen')}/hariri", {"name": "books", "price": "65", "quantity": "3"})
        self.assertIn("ipo tayari", self.text(r))

    def test_cannot_edit_or_delete_another_kiosks_product(self):
        self.signup("a@example.com", "Duka A")
        self.stock_item("Pen", "3", "65")
        pid = self.product_id("Pen")
        other = self.app.test_client()
        self.signup("b@example.com", "Duka B", client=other)
        self.assertEqual(other.get(f"/bidhaa/{pid}/hariri").status_code, 404)
        self.assertEqual(self.post(f"/bidhaa/{pid}/hariri", {"name": "X", "price": "1", "quantity": "1"}, other).status_code, 404)
        self.assertEqual(self.post(f"/bidhaa/{pid}/futa", {"confirm": "1"}, other).status_code, 404)
        self.assertIn("Pen", self.text(self.client.get("/stoo")))

    def test_delete_needs_confirmation_and_keeps_sales_history(self):
        self.signup()
        self.stock_item("Pen", "10", "65")
        self.post("/uza", {"product": "Pen", "quantity": "2"})
        pid = self.product_id("Pen")
        self.post(f"/bidhaa/{pid}/futa", {})                      # no tick: nothing happens
        self.assertIn("Pen", self.text(self.client.get("/stoo")))
        r = self.post(f"/bidhaa/{pid}/futa", {"confirm": "1"})
        self.assertIn("Pen imefutwa", self.text(r))
        self.assertIn("Hakuna bidhaa bado", self.text(self.client.get("/stoo")))
        self.assertIn("KES 130", self.text(self.client.get("/ripoti?period=all")))   # history kept

    def test_readding_a_removed_product_restores_it(self):
        self.signup()
        self.stock_item("Pen", "10", "65")
        self.post(f"/bidhaa/{self.product_id('Pen')}/futa", {"confirm": "1"})
        r = self.stock_item("pen", "4", "70")
        self.assertIn("Pen imeongezwa", self.text(r))
        self.assertIn("70", self.text(self.client.get("/stoo")))

    def test_csv_export(self):
        self.signup()
        self.stock_item("=Evil", "10", "5")
        self.post("/uza", {"product": "=Evil", "quantity": "2"})
        r = self.client.get("/ripoti.csv?period=all")
        self.assertEqual(r.status_code, 200)
        self.assertIn("text/csv", r.headers["Content-Type"])
        self.assertIn("attachment", r.headers["Content-Disposition"])
        body = r.get_data(as_text=True)
        self.assertIn("Wakati,Bidhaa,Idadi,Jumla (KES)", body)
        self.assertIn("'=Evil", body)                      # formula injection neutralised
        self.assertEqual(self.app.test_client().get("/ripoti.csv").status_code, 302)   # needs login

    def test_shopping_list_and_prefill(self):
        self.signup()
        self.stock_item("Pen", "2", "65")
        self.assertIn("Pen", self.text(self.client.get("/zinaisha")))
        self.assertIn('value="Pen"', self.text(self.client.get("/ongeza?bidhaa=Pen")))
        self.assertNotIn("<script>alert", self.text(self.client.get("/ongeza?bidhaa=<script>alert(1)</script>")))

    def test_security_headers_present(self):
        h = self.client.get("/ingia").headers
        self.assertEqual(h["X-Frame-Options"], "DENY")
        self.assertIn("default-src 'self'", h["Content-Security-Policy"])


if __name__ == "__main__":
    unittest.main()
