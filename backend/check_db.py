# check_db.py
from sqlalchemy import create_engine, text
import os

# --- Configuration ---
# Make sure this matches your database file name!
db_file = "kpc.db"
# --- End Configuration ---

engine_url = f"sqlite:///./{db_file}"

if not os.path.exists(db_file):
    print(f"Error: Database file '{db_file}' not found in the current directory.")
    print("Make sure you are running this script from the 'backend' folder.")
else:
    try:
        e = create_engine(engine_url, future=True)
        with e.connect() as c:
            print("--- Total Price Counts Per Store (GROUP BY slug) ---")
            print(c.execute(text("""
                SELECT s.slug, COUNT(p.id) as count
                FROM prices p
                JOIN stores s ON s.id = p.store_id
                GROUP BY s.slug
                ORDER BY s.slug
            """)).all())

            print("\n--- Recent Price Counts (Last 10 Days) ---")
            print(c.execute(text("""
                SELECT s.slug, COUNT(p.id) as count
                FROM prices p
                JOIN stores s ON s.id = p.store_id
                WHERE p.collected_at >= date('now','-10 days')
                GROUP BY s.slug
                ORDER BY s.slug
            """)).all())

            print("\n--- Count of Prices with NULL unit_price ---")
            print(c.execute(text("""
                SELECT s.slug, COUNT(p.id) as count
                FROM prices p
                JOIN stores s ON s.id = p.store_id
                WHERE p.unit_price IS NULL
                GROUP BY s.slug
                ORDER BY s.slug
            """)).all())

            print("\n--- Count of StoreItems with NULL category_norm ---")
            print(c.execute(text("""
                SELECT s.slug, COUNT(si.id) as count
                FROM store_items si
                JOIN stores s ON s.id = si.store_id
                WHERE si.category_norm IS NULL
                GROUP BY s.slug
                ORDER BY s.slug
            """)).all())

            # --- 👇 ADDED QUERY TO CHECK PRODUCT IDs ---
            print("\n--- Milk Product IDs ---")
            print(c.execute(text("""
                SELECT id, canonical_name 
                FROM products 
                WHERE category = 'milk'
                ORDER BY id;
            """)).all())
            # --- END ADDED QUERY ---

    except Exception as ex:
        print(f"\nAn error occurred connecting to or querying the database: {ex}")
        print(f"Make sure '{db_file}' is a valid SQLite database.")
