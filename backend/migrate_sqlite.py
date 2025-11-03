# migrate_sqlite.py
import sqlite3, sys, os

db_path = sys.argv[1] if len(sys.argv) > 1 else "kpc.db"
if not os.path.exists(db_path):
    print(f"❌ DB not found: {db_path}")
    raise SystemExit(1)

print(f"Using DB: {db_path}")
conn = sqlite3.connect(db_path)
cur = conn.cursor()
cur.execute("PRAGMA foreign_keys=OFF;")

def has_column(table, col):
    cur.execute(f"PRAGMA table_info({table});")
    return any(r[1] == col for r in cur.fetchall())

def safe_alter(table, col, coldef):
    if not has_column(table, col):
        print(f"Adding {table}.{col} ...")
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {col} {coldef};")
    else:
        print(f"{table}.{col} already exists.")

# Ensure columns exist
safe_alter("store_items", "product_id", "INTEGER")
safe_alter("prices", "store_id", "INTEGER")

# Backfill prices.store_id from store_items.store_id where missing
print("Backfilling prices.store_id ...")
cur.execute("""
UPDATE prices
SET store_id = (
  SELECT si.store_id FROM store_items si
  WHERE si.id = prices.store_item_id
)
WHERE store_id IS NULL;
""")

conn.commit()

# Show final columns
for t in ("store_items", "prices"):
    cur.execute(f"PRAGMA table_info({t});")
    cols = ", ".join([r[1] for r in cur.fetchall()])
    print(f"{t} columns: {cols}")

conn.close()
print("✅ Done.")
