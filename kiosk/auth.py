"""Accounts: register, log in, and temporary demo accounts."""

import re
import secrets

from werkzeug.security import check_password_hash, generate_password_hash

from kiosk import services
from kiosk.services import KioskError

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MIN_PASSWORD = 8
DEMO_LIFETIME_HOURS = 24

# Used so a login for an unknown email takes as long as one for a known email.
_DUMMY_HASH = generate_password_hash("not-a-real-password")


def normalise_email(raw):
    return str(raw).strip().lower()


def get_user(conn, user_id):
    return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()


def register(conn, email, password, kiosk_name, is_demo=False):
    email = normalise_email(email)
    kiosk_name = " ".join(str(kiosk_name).split())
    if not EMAIL_RE.match(email) or len(email) > 254:
        raise KioskError("invalid_email")
    if len(str(password)) < MIN_PASSWORD or len(str(password)) > 200:
        raise KioskError("weak_password")
    if kiosk_name == "" or len(kiosk_name) > 60:
        raise KioskError("invalid_kiosk_name")
    if conn.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone():
        raise KioskError("email_taken")

    first_real_user = not is_demo and not conn.execute(
        "SELECT 1 FROM users WHERE is_demo = 0").fetchone()

    with conn:
        cur = conn.execute(
            "INSERT INTO users (email, password_hash, kiosk_name, is_demo) VALUES (?, ?, ?, ?)",
            (email, generate_password_hash(str(password)), kiosk_name, int(is_demo)))
        user_id = cur.lastrowid
        if first_real_user:
            # Stock imported before accounts existed becomes this owner's.
            conn.execute("UPDATE products SET user_id = ? WHERE user_id IS NULL", (user_id,))
            conn.execute("UPDATE sales SET user_id = ? WHERE user_id IS NULL", (user_id,))
    return user_id


def authenticate(conn, email, password):
    user = conn.execute("SELECT * FROM users WHERE email = ?",
                        (normalise_email(email),)).fetchone()
    ok = check_password_hash(user["password_hash"] if user else _DUMMY_HASH, str(password))
    if not user or not ok:
        raise KioskError("bad_login")
    return user


def purge_old_demos(conn):
    old = "SELECT id FROM users WHERE is_demo = 1 AND created_at < datetime('now', ?)"
    age = (f"-{DEMO_LIFETIME_HOURS} hours",)
    with conn:
        conn.execute(f"DELETE FROM sales WHERE user_id IN ({old})", age)
        conn.execute(f"DELETE FROM products WHERE user_id IN ({old})", age)
        conn.execute("DELETE FROM users WHERE is_demo = 1 AND created_at < datetime('now', ?)", age)


DEMO_STOCK = [("Mkate", 65, 40), ("Maziwa", 60, 30), ("Sukari", 150, 15),
              ("Mayai", 20, 60), ("Chai Majani", 120, 12), ("Mandazi", 10, 50)]
DEMO_SALES = [("Mkate", 6), ("Maziwa", 4), ("Mayai", 12), ("Mandazi", 15), ("Sukari", 2)]


def create_demo(conn):
    """A throwaway account with sample data, so visitors can try the app."""
    purge_old_demos(conn)
    user_id = register(conn, f"demo-{secrets.token_hex(6)}@demo.invalid",
                       secrets.token_urlsafe(16), "Duka la Demo", is_demo=True)
    for name, price, qty in DEMO_STOCK:
        services.add_or_restock(conn, user_id, name, qty, price)
    for name, qty in DEMO_SALES:
        services.sell(conn, user_id, name, qty)
    return user_id
