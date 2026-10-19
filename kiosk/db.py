"""Database setup. SQLite for now; the schema is plain SQL so it ports to PostgreSQL later."""

import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS products (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    name     TEXT    NOT NULL UNIQUE,
    price    INTEGER NOT NULL CHECK (price > 0),
    quantity INTEGER NOT NULL CHECK (quantity >= 0)
);

CREATE TABLE IF NOT EXISTS sales (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id   INTEGER NOT NULL REFERENCES products(id),
    product_name TEXT    NOT NULL,
    quantity     INTEGER NOT NULL CHECK (quantity > 0),
    total        INTEGER NOT NULL,
    sold_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);
"""


def get_connection(path="kiosk.db"):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row          # rows behave like dicts
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn):
    conn.executescript(SCHEMA)
    conn.commit()
