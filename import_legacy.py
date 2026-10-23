"""One-off: load the original Dictionary.txt into the database.  python import_legacy.py"""
from kiosk.db import get_connection
from kiosk.services import import_legacy

conn = get_connection("kiosk.db")
import_legacy(conn, "legacy/Dictionary.txt")
print("Imported stock from legacy/Dictionary.txt into kiosk.db")
