# backend/scripts/backfill_brand_category.py
import os, sys, sqlite3

# Make sure project root is on sys.path so "backend.app..." imports work
THIS_DIR = os.path.dirname(__file__)
PROJECT_ROOT = os.path.abspath(os.path.join(THIS_DIR, "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from backend.app.utils.taxonomy import detect_brand, detect_category

DB = os.path.join(PROJECT_ROOT, r"backend\kpc.db")

con = sqlite3.connect(DB)
cur = con.cursor()

rows = cur.execute(
    "SELECT id, raw_name FROM store_items WHERE brand IS NULL OR category IS NULL"
).fetchall()

updated = 0
for _id, raw in rows:
    brand = detect_brand(raw)
    cat = detect_category(raw)
    cur.execute(
        """
        UPDATE store_items
        SET brand = COALESCE(brand, ?),
            category = COALESCE(category, ?)
        WHERE id = ?
        """,
        (brand, cat, _id),
    )
    updated += cur.rowcount

con.commit()
con.close()
print(f"Updated {updated} rows.")
