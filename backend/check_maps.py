# check_maps.py
from sqlalchemy import create_engine, text
e = create_engine("sqlite:///./kpc.db", future=True)
with e.connect() as c:
    print("\n-- Mappings per store --")
    print(c.execute(text("""
      SELECT s.slug, COUNT(*) 
      FROM mappings m 
      JOIN store_items si ON si.id = m.store_item_id
      JOIN stores s ON s.id = si.store_id
      GROUP BY s.slug ORDER BY s.slug
    """)).all())

    print("\n-- Mappings per product & store (first few) --")
    for row in c.execute(text("""
      SELECT p.id, p.canonical_name, s.slug, COUNT(*) as cnt
      FROM mappings m
      JOIN products p ON p.id = m.product_id
      JOIN store_items si ON si.id = m.store_item_id
      JOIN stores s ON s.id = si.store_id
      GROUP BY p.id, s.slug
      ORDER BY p.id, s.slug
    """)).fetchall()[:20]:
        print(row)
