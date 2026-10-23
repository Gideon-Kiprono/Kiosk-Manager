"""Business logic. No input() or print() here: functions take arguments and
return values, so the same code can power a CLI, a website or the tests."""

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

def list_products(conn):
    return conn.execute("SELECT * FROM products ORDER BY name").fetchall()


def get_product(conn, name):
    return conn.execute("SELECT * FROM products WHERE name = ?", (clean_name(name),)).fetchone()


def add_or_restock(conn, name, quantity, price=None):
    """Restock an existing product, or add a new one (price required)."""
    name = clean_name(name)
    quantity = positive_int(quantity, "quantity")
    product = conn.execute("SELECT * FROM products WHERE name = ?", (name,)).fetchone()

    if product:
        conn.execute("UPDATE products SET quantity = quantity + ? WHERE id = ?",
                     (quantity, product["id"]))
        action = "restocked"
    else:
        if price is None:
            raise KioskError("price_required", name=name)
        price = positive_int(price, "price")
        conn.execute("INSERT INTO products (name, price, quantity) VALUES (?, ?, ?)",
                     (name, price, quantity))
        action = "added"
    conn.commit()
    return action, get_product(conn, name)


def search_products(conn, term):
    term = str(term).strip().lower()
    if term == "":
        raise KioskError("empty_search")
    return conn.execute(
        "SELECT * FROM products WHERE lower(name) LIKE ? ORDER BY name",
        (f"%{term}%",)).fetchall()


# ---------- sales ----------

def sell(conn, name, quantity):
    name = clean_name(name)
    quantity = positive_int(quantity, "quantity")
    product = conn.execute("SELECT * FROM products WHERE name = ?", (name,)).fetchone()
    if product is None:
        raise KioskError("unknown_product", name=name)
    if quantity > product["quantity"]:
        raise KioskError("not_enough", available=product["quantity"])

    total = quantity * product["price"]
    # One transaction: stock and sale change together, or not at all.
    with conn:
        conn.execute("UPDATE products SET quantity = quantity - ? WHERE id = ?",
                     (quantity, product["id"]))
        conn.execute(
            "INSERT INTO sales (product_id, product_name, quantity, total) VALUES (?, ?, ?, ?)",
            (product["id"], name, quantity, total))
    return {"product": name, "quantity": quantity, "total": total}


def sales_report(conn, date_from=None, tz_hours=0):
    """Totals and best seller. date_from is 'YYYY-MM-DD' (inclusive, in local time) or None.
    Sales are stored in UTC; tz_hours shifts them to the kiosk's local time (Nairobi = 3)."""
    shift = f"{tz_hours:+d} hours"
    where = "WHERE date(sold_at, ?) >= ?" if date_from else ""
    params = (shift, date_from) if date_from else ()
    sales = conn.execute(
        f"SELECT *, datetime(sold_at, ?) AS local_time FROM sales {where} ORDER BY id DESC",
        (shift, *params)).fetchall()

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


def low_stock(conn, limit=5):
    return conn.execute("SELECT * FROM products WHERE quantity <= ? ORDER BY quantity, name",
                        (limit,)).fetchall()


# ---------- one-off migration from the original text files ----------

def import_legacy(conn, inventory_path, sales_path=None):
    """Load Dictionary.txt (name,price,quantity) and optionally sales_log.txt."""
    init_db(conn)
    with open(inventory_path) as f:
        for line in f:
            if line.strip():
                name, price, qty = line.strip().split(",")
                conn.execute(
                    "INSERT OR REPLACE INTO products (name, price, quantity) VALUES (?, ?, ?)",
                    (clean_name(name), int(float(price)), int(qty)))
    conn.commit()
