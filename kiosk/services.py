"""Business logic. No input() or print() here: functions take arguments and
return values, so the same code can power a CLI, a website or the tests.

Every function takes a user_id and only ever touches that user's rows."""

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
    return conn.execute("SELECT * FROM products WHERE user_id = ? ORDER BY name",
                        (user_id,)).fetchall()


def get_product(conn, user_id, name):
    return conn.execute("SELECT * FROM products WHERE user_id = ? AND name = ?",
                        (user_id, clean_name(name))).fetchone()


def add_or_restock(conn, user_id, name, quantity, price=None):
    """Restock an existing product, or add a new one (price required)."""
    name = clean_name(name)
    quantity = positive_int(quantity, "quantity")
    product = conn.execute("SELECT * FROM products WHERE user_id = ? AND name = ?",
                           (user_id, name)).fetchone()

    if product:
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
        "SELECT * FROM products WHERE user_id = ? AND lower(name) LIKE ? ORDER BY name",
        (user_id, f"%{term}%")).fetchall()


# ---------- sales ----------

def sell(conn, user_id, name, quantity):
    name = clean_name(name)
    quantity = positive_int(quantity, "quantity")
    product = conn.execute("SELECT * FROM products WHERE user_id = ? AND name = ?",
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
        "SELECT * FROM products WHERE user_id = ? AND quantity <= ? ORDER BY quantity, name",
        (user_id, limit)).fetchall()


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
