# backfill_mappings.py
import re
from sqlalchemy import create_engine, text
import os
import unicodedata # Needed for _strip_accents if you use it later

# --- Configuration ---
DB_FILE = "kpc.db" # Make sure this matches your database file
DB_URL = f"sqlite:///./{DB_FILE}"

# !!! IMPORTANT: Verify these IDs match your 'products' table !!!
# Run: SELECT id, canonical_name FROM products WHERE category = 'milk';
# And update the 'id' values below if needed.
PRODUCTS = {
    "milk_28": {
        "id": 1, # Assumed ID for 'Milk 1L 2.8%'
        "patterns": [
            # Looser patterns: Look for keywords anywhere, handle spacing variations
            r"(?=.*\b(qum[eë]sht|milk)\b)(?=.*\b1\s?l\b)(?=.*\b2[.,]8)" # Lookahead ensures all parts exist
        ]
    },
    "milk_35": {
        "id": 2, # Assumed ID for 'Milk 1L 3.5%'
        "patterns": [
            # Looser patterns: Look for keywords anywhere, handle spacing variations
             r"(?=.*\b(qum[eë]sht|milk)\b)(?=.*\b1\s?l\b)(?=.*\b3[.,]5)" # Lookahead ensures all parts exist
        ]
    },
    # Add other products here if needed following the same pattern
    # "butter_250": { "id": 5, "patterns": [r"(?=.*\b(gjalp[eë]?|butter)\b)(?=.*\b250\s?g\b)"]},
}
# --- End Configuration ---

def _strip_accents(s): # Helper from instructions, used by like_frag indirectly
   # Added basic handling for None input
   if s is None:
       return ""
   return ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn')

# like_frag function is not used in the current logic, can be removed or kept for reference
# def like_frag(pat): ...

if not os.path.exists(DB_FILE):
    print(f"Error: Database file '{DB_FILE}' not found.")
    exit()

try:
    e = create_engine(DB_URL, future=True)
    with e.begin() as c: # Use begin() for transaction
        # --- MODIFIED QUERY ---
        # Get store items that have a price collected in the last 30 days
        # Fetching original raw_name as well for printing
        recent_si = c.execute(text("""
          SELECT DISTINCT si.id, si.raw_name AS rn_original, LOWER(si.raw_name) AS rn_lower
          FROM store_items si
          JOIN prices p ON p.store_item_id = si.id
          WHERE p.collected_at >= date('now','-30 days')
        """)).fetchall()
        # --- END MODIFIED QUERY ---

        if not recent_si:
            print("No store items with prices found in the last 30 days. No mappings backfilled.")
        else:
            print(f"Found {len(recent_si)} unique recent store items (with prices) to check.")

            # --- NEW DEBUG PRINTING ---
            print("\n--- Sample raw_names containing 'milk' or 'qum' (first 30) ---")
            count = 0
            printed_samples = False
            for _, rn_original, rn_lower in recent_si:
                # Use original name for checking keywords before stripping accents
                name_to_check = rn_original.lower() if rn_original else ""
                if 'milk' in name_to_check or 'qum' in name_to_check:
                    print(f"  - \"{rn_original}\"") # Print the original name as stored
                    count += 1
                    printed_samples = True
                if count >= 30:
                    break
            if not printed_samples:
                print("  (No recent item names containing 'milk' or 'qum' found)")
            # --- END NEW DEBUG PRINTING ---


        total_inserted = 0
        for key, cfg in PRODUCTS.items():
            prod_id = cfg["id"]

            # Filter recent_si in Python for candidates
            # Apply _strip_accents to the lowercase raw_name for matching
            candidates = [
                si_id for si_id, _, rn_lower in recent_si # Adjusted tuple unpacking
                # Use _strip_accents on the lowercase name before regex search
                if any(re.search(pat, _strip_accents(rn_lower or ""), re.IGNORECASE) for pat in cfg["patterns"])
            ]


            print(f"\nProduct '{key}' (ID: {prod_id}): Found {len(candidates)} potential candidate items.")

            # Print examples IF candidates were found (using original names)
            if candidates:
               print("  Examples that matched:")
               # Find the original names for the first 5 candidate IDs
               candidate_ids_set = set(candidates[:5])
               # Match IDs and retrieve original names correctly
               names_to_print = [rn_original for si_id, rn_original, _ in recent_si if si_id in candidate_ids_set]

               for name in names_to_print:
                   print(f"    - \"{name}\"")


            if candidates:
                # Use tuple() for the IN clause
                # Ensure tuple is not empty, handle single item case
                if len(candidates) == 1:
                   candidate_tuple = (candidates[0],) # Comma makes it a tuple
                else:
                   candidate_tuple = tuple(candidates)


                # Use INSERT OR IGNORE to avoid errors if a mapping already exists
                # Use named parameters directly with execute for clarity and safety
                params = {'pid': prod_id}
                ids_placeholders = ', '.join(f':id_{i}' for i, _ in enumerate(candidate_tuple))
                insert_sql_formatted = text(f"""
                    INSERT OR IGNORE INTO mappings (product_id, store_item_id, match_score)
                    SELECT :pid, si.id, 0.5
                    FROM store_items si
                    WHERE si.id IN ({ids_placeholders})
                """)
                for i, id_val in enumerate(candidate_tuple):
                    params[f'id_{i}'] = id_val

                result = c.execute(insert_sql_formatted, params)


                inserted_count = result.rowcount
                total_inserted += inserted_count
                print(f" -> Inserted {inserted_count} new mappings for product {prod_id}.")

    print(f"\nDone. Total new mappings inserted: {total_inserted}. Now refresh the UI.")

except Exception as ex:
    print(f"\nAn error occurred: {ex}")

