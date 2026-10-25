"""Database setup. SQLite for now; the schema is plain SQL so it ports to PostgreSQL later."""

import sqlite3

USERS = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    email         TEXT    NOT NULL UNIQUE,
    password_hash TEXT    NOT NULL,
    kiosk_name    TEXT    NOT NULL,
    is_demo       INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT    NOT NULL DEFAULT (datetime('now'))
);
"""

# {n} is the table name, so the same definition is used for new databases and for migration.
PRODUCTS = """
CREATE TABLE {n} (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id  INTEGER REFERENCES users(id),
    name     TEXT    NOT NULL,
    price    INTEGER NOT NULL CHECK (price > 0),
    quantity INTEGER NOT NULL CHECK (quantity >= 0),
    archived INTEGER NOT NULL DEFAULT 0,
    UNIQUE (user_id, name)
);
"""

SALES = """
CREATE TABLE {n} (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER REFERENCES users(id),
    product_id   INTEGER NOT NULL REFERENCES products(id),
    product_name TEXT    NOT NULL,
    quantity     INTEGER NOT NULL CHECK (quantity > 0),
    total        INTEGER NOT NULL,
    sold_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);
"""

INDEXES = """
CREATE INDEX IF NOT EXISTS idx_sales_user_time ON sales (user_id, sold_at);
CREATE INDEX IF NOT EXISTS idx_products_user ON products (user_id);
"""


def get_connection(path="kiosk.db"):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row          # rows behave like dicts
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _columns(conn, table):
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def _migrate_to_accounts(conn):
    """Stage 2 databases have no user_id. Rebuild the tables with it.
    Existing rows keep user_id NULL ("unclaimed"): the first account registered claims them."""
    conn.executescript("PRAGMA foreign_keys = OFF;")
    conn.executescript(
        PRODUCTS.format(n="products_new")
        + "INSERT INTO products_new (id, name, price, quantity) SELECT id, name, price, quantity FROM products;"
        + SALES.format(n="sales_new")
        + """INSERT INTO sales_new (id, product_id, product_name, quantity, total, sold_at)
             SELECT id, product_id, product_name, quantity, total, sold_at FROM sales;
           DROP TABLE sales;
           DROP TABLE products;
           ALTER TABLE products_new RENAME TO products;
           ALTER TABLE sales_new RENAME TO sales;"""
    )
    conn.executescript("PRAGMA foreign_keys = ON;")


def init_db(conn):
    old = _columns(conn, "products")
    if old and "user_id" not in old:
        _migrate_to_accounts(conn)
    cols = _columns(conn, "products")
    if cols and "archived" not in cols:
        # Stage 3 databases: "removed" products are hidden, not deleted, so old sales keep their history.
        conn.execute("ALTER TABLE products ADD COLUMN archived INTEGER NOT NULL DEFAULT 0")
    conn.executescript(
        USERS
        + PRODUCTS.format(n="IF NOT EXISTS products")
        + SALES.format(n="IF NOT EXISTS sales")
        + INDEXES
    )
    conn.commit()
