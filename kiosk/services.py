"""Business logic. No input() or print() here: functions take arguments and
return values, so the same code can power a CLI, a website or the tests.

Every function takes a user_id and only ever touches that user's rows."""

import csv
import io
from datetime import date, timedelta

from kiosk.db import init_db


class KioskError(Exception):
    """A rule was broken. Carries a code + params so the UI can translate it."""

    MESSAGES = {
        "invalid_name": "Please enter a valid product name.",
        "invalid_number": "{field} must be a whole number greater than 0.",
        "unknown_product": "{name} is not available in the inventory.",
        "not_enough": "Not enough stock. Only {available} units available.",
        "price_required": "{name} is new, so a price is required.",
        "empty_search": "Please type something to search for.",
        "invalid_email": "Please enter a valid email address.",
        "weak_password": "Password must be at least 8 characters.",
        "email_taken": "That email is already registered.",
        "bad_login": "Wrong email or password.",
        "invalid_kiosk_name": "Please enter a kiosk name.",
        "too_many_attempts": "Too many attempts. Wait 15 minutes.",
        "csrf": "The request could not be verified. Please try again.",
        "product_exists": "A product with that name already exists.",
        "invalid_stock": "Stock must be a whole number, 0 or more.",
    }

    def __init__(self, code, **params):
        self.code = code
        self.params = params
        super().__init__(self.MESSAGES[code].format(**{"field": "", **params}))


# ---------- helpers ----------

def clean_name(raw):
    name = " ".join(str(raw).split()).title()     # strip + collapse spaces + Title Case
    if name == "" or name.isdigit():
        raise KioskError("invalid_name")
    return name


def positive_int(value, field):
    text = str(value).strip()
    if not text.isdigit() or int(text) <= 0:
        raise KioskError("invalid_number", field=field)
    return int(text)


# ---------- inventory ----------

def list_products(conn, user_id):
    return conn.execute("SELECT * FROM products WHERE user_id = ? AND archived = 0 ORDER BY name",
                        (user_id,)).fetchall()


def get_product(conn, user_id, name):
    return conn.execute("SELECT * FROM products WHERE user_id = ? AND name = ? AND archived = 0",
                        (user_id, clean_name(name))).fetchone()


def add_or_restock(conn, user_id, name, quantity, price=None):
    """Restock an existing product, or add a new one (price required)."""
    name = clean_name(name)
    quantity = positive_int(quantity, "quantity")
    product = conn.execute("SELECT * FROM products WHERE user_id = ? AND name = ?",
                           (user_id, name)).fetchone()

    if product and product["archived"]:
        # A removed product is being added again: bring it back with fresh stock.
        new_price = positive_int(price, "price") if price is not None else product["price"]
        conn.execute("UPDATE products SET archived = 0, quantity = ?, price = ? WHERE id = ? AND user_id = ?",
                     (quantity, new_price, product["id"], user_id))
        action = "added"
    elif product:
        conn.execute("UPDATE products SET quantity = quantity + ? WHERE id = ? AND user_id = ?",
                     (quantity, product["id"], user_id))
        action = "restocked"
    else:
        if price is None:
            raise KioskError("price_required", name=name)
        price = positive_int(price, "price")
        conn.execute("INSERT INTO products (user_id, name, price, quantity) VALUES (?, ?, ?, ?)",
                     (user_id, name, price, quantity))
        action = "added"
    conn.commit()
    return action, get_product(conn, user_id, name)


def search_products(conn, user_id, term):
    term = str(term).strip().lower()
    if term == "":
        raise KioskError("empty_search")
    return conn.execute(
        "SELECT * FROM products WHERE user_id = ? AND archived = 0 AND lower(name) LIKE ? ORDER BY name",
        (user_id, f"%{term}%")).fetchall()


# ---------- sales ----------

def sell(conn, user_id, name, quantity):
    name = clean_name(name)
    quantity = positive_int(quantity, "quantity")
    product = conn.execute("SELECT * FROM products WHERE user_id = ? AND name = ? AND archived = 0",
                           (user_id, name)).fetchone()
    if product is None:
        raise KioskError("unknown_product", name=name)
    if quantity > product["quantity"]:
        raise KioskError("not_enough", available=product["quantity"])

    total = quantity * product["price"]
    # One transaction: stock and sale change together, or not at all.
    with conn:
        conn.execute("UPDATE products SET quantity = quantity - ? WHERE id = ? AND user_id = ?",
                     (quantity, product["id"], user_id))
        conn.execute(
            "INSERT INTO sales (user_id, product_id, product_name, quantity, total) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, product["id"], name, quantity, total))
    return {"product": name, "quantity": quantity, "total": total}


def sales_report(conn, user_id, date_from=None, tz_hours=0):
    """Totals and best seller. date_from is 'YYYY-MM-DD' (inclusive, in local time) or None.
    Sales are stored in UTC; tz_hours shifts them to the kiosk's local time (Nairobi = 3)."""
    shift = f"{tz_hours:+d} hours"
    where = "WHERE user_id = ?"
    params = [shift, user_id]
    if date_from:
        where += " AND date(sold_at, ?) >= ?"
        params += [shift, date_from]
    sales = conn.execute(
        f"SELECT *, datetime(sold_at, ?) AS local_time FROM sales {where} ORDER BY id DESC",
        params).fetchall()

    units = {}
    for sale in sales:
        units[sale["product_name"]] = units.get(sale["product_name"], 0) + sale["quantity"]

    best = max(units, key=units.get) if units else None
    return {
        "sales": sales,
        "revenue": sum(s["total"] for s in sales),
        "unique_products": len(units),
        "best_seller": (best, units[best]) if best else None,
    }


def low_stock(conn, user_id, limit=5):
    return conn.execute(
        "SELECT * FROM products WHERE user_id = ? AND archived = 0 AND quantity <= ? ORDER BY quantity, name",
        (user_id, limit)).fetchall()


# ---------- editing and removing products ----------

def get_product_by_id(conn, user_id, product_id):
    return conn.execute("SELECT * FROM products WHERE id = ? AND user_id = ? AND archived = 0",
                        (product_id, user_id)).fetchone()


def update_product(conn, user_id, product_id, name, price, quantity):
    """Correct a product's name, price and stock (for fixing mistakes)."""
    product = get_product_by_id(conn, user_id, product_id)
    if product is None:
        raise KioskError("unknown_product", name="")
    name = clean_name(name)
    price = positive_int(price, "price")
    text = str(quantity).strip()
    if not text.isdigit():
        raise KioskError("invalid_stock")
    clash = conn.execute("SELECT 1 FROM products WHERE user_id = ? AND name = ? AND id != ?",
                         (user_id, name, product_id)).fetchone()
    if clash:
        raise KioskError("product_exists")
    conn.execute("UPDATE products SET name = ?, price = ?, quantity = ? WHERE id = ? AND user_id = ?",
                 (name, price, int(text), product_id, user_id))
    conn.commit()
    return get_product_by_id(conn, user_id, product_id)


def remove_product(conn, user_id, product_id):
    """Hide a product. Its past sales stay in the reports."""
    product = get_product_by_id(conn, user_id, product_id)
    if product is None:
        raise KioskError("unknown_product", name="")
    conn.execute("UPDATE products SET archived = 1 WHERE id = ? AND user_id = ?",
                 (product_id, user_id))
    conn.commit()
    return product


# ---------- dashboard and export ----------

def daily_sales(conn, user_id, today, days=7, tz_hours=0):
    """Revenue and units per local day for the last `days` days, ending on `today`
    ('YYYY-MM-DD', local). Days with no sales are included as zeros."""
    shift = f"{tz_hours:+d} hours"
    last = date.fromisoformat(today)
    first = last - timedelta(days=days - 1)
    rows = conn.execute(
        "SELECT date(sold_at, ?) AS d, SUM(total) AS revenue, SUM(quantity) AS units "
        "FROM sales WHERE user_id = ? AND date(sold_at, ?) >= ? GROUP BY d",
        (shift, user_id, shift, first.isoformat())).fetchall()
    by_day = {r["d"]: r for r in rows}
    result = []
    for i in range(days):
        day = (first + timedelta(days=i)).isoformat()
        row = by_day.get(day)
        result.append({"date": day,
                       "revenue": row["revenue"] if row else 0,
                       "units": row["units"] if row else 0})
    return result


def csv_safe(value):
    """Stop spreadsheet programs treating a product name as a formula (=, +, -, @)."""
    text = str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


def export_sales_csv(conn, user_id, date_from=None, tz_hours=0, header=None):
    report = sales_report(conn, user_id, date_from=date_from, tz_hours=tz_hours)
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\r\n")
    writer.writerow(header or ["Time", "Product", "Quantity", "Total (KES)"])
    for sale in reversed(report["sales"]):                      # oldest first
        writer.writerow([sale["local_time"], csv_safe(sale["product_name"]),
                         sale["quantity"], sale["total"]])
    return "\ufeff" + out.getvalue()                            # BOM so Excel reads UTF-8


# ---------- one-off migration from the original text files ----------

def import_legacy(conn, inventory_path, user_id=None):
    """Load Dictionary.txt (name,price,quantity). With user_id=None the rows are
    'unclaimed' and the first account to register takes them over."""
    init_db(conn)
    with open(inventory_path) as f:
        for line in f:
            if not line.strip():
                continue
            name, price, qty = line.strip().split(",")
            name, price, qty = clean_name(name), int(float(price)), int(qty)
            exists = conn.execute("SELECT id FROM products WHERE user_id IS ? AND name = ?",
                                  (user_id, name)).fetchone()
            if exists:
                conn.execute("UPDATE products SET price = ?, quantity = ? WHERE id = ?",
                             (price, qty, exists["id"]))
            else:
                conn.execute("INSERT INTO products (user_id, name, price, quantity) VALUES (?, ?, ?, ?)",
                             (user_id, name, price, qty))
    conn.commit()
