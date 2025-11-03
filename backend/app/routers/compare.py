# backend/app/routers/compare.py
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, aliased
from sqlalchemy import func, and_, desc, select, literal_column, or_, asc, true, not_, exists

from ..db import SessionLocal
from ..models import Product, Mapping, StoreItem, Price, Store
from ..schemas import CompareOut, ProductOut, PriceOut

router = APIRouter(prefix="/compare", tags=["compare"])

# how far back we accept price rows
RECENT_DAYS = 14


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("", response_model=CompareOut)
def compare_prices(
    product_id: int = Query(..., ge=1),
    db: Session = Depends(get_db),
):
    prod = db.get(Product, product_id)
    if not prod:
        raise HTTPException(status_code=404, detail="Product not found")

    # --- Resilient Query with OUTER JOIN replacement via EXISTS and Robust Name-Based Fallback ---

    # 1. Alias the tables
    P = aliased(Price)
    SI = aliased(StoreItem)
    S = aliased(Store)
    M = aliased(Mapping)  # Alias for Mapping

    # --- Fallback Heuristics (unchanged structure, reused below) ---
    name_lower = func.lower(SI.raw_name)

    # milk-like tokens
    is_milkish = or_(
        name_lower.like("%qum%"),  # Covers "qumesht" variations
        name_lower.like("%milk%")
    )

    # 1L variations
    is_1l = or_(
        name_lower.like("%1l%"),
        name_lower.like("%1 l%"),
        name_lower.like("%1000ml%"),
        name_lower.like("%1000 ml%")
    )

    # 250g variations (butter)
    is_250g = or_(
        name_lower.like("%250g%"),
        name_lower.like("%250 g%"),
        name_lower.like("%250gr%"),
        name_lower.like("%250 gr%")
    )

    # Fat % guard (handles comma/dot)
    fat_ok = true()  # Assume OK if product has no fat % specified
    if prod.fat_pct:
        fat_str_comma = f"%{str(prod.fat_pct).replace('.', ',')}%"
        fat_str_dot = f"%{str(prod.fat_pct).replace(',', '.')}%"

        fat_ok = or_(
            SI.fat_pct.between(prod.fat_pct - 0.3, prod.fat_pct + 0.3),
            name_lower.like(fat_str_comma),
            name_lower.like(fat_str_dot),
        )

    # Exclude alternative milks
    exclude_alt_milk = or_(
        name_lower.like("%soja%"), name_lower.like("%soya%"),
        name_lower.like("%badem%"), name_lower.like("%almond%"),
        name_lower.like("%oriz%"),  name_lower.like("%rice%"),
        name_lower.like("%oat%"),   name_lower.like("%tersh%"),
        name_lower.like("%kokos%"), name_lower.like("%coco%"),
        name_lower.like("%dhie%"),  name_lower.like("%goat%")
    )

    # Category-specific fallback
    fallback_condition = true()
    if prod.category == 'milk' and prod.size_ml_g and 900 <= prod.size_ml_g <= 1100:
        fallback_condition = and_(is_milkish, is_1l, fat_ok, not_(exclude_alt_milk))
    elif prod.category == 'butter' and prod.size_ml_g == 250:
        fallback_condition = and_(name_lower.like('%gjalp%'), is_250g)
    # Extend with more categories as needed (yogurt, cheese, etc.)

    # ----- Stage A: latest-price-per-item with robust mapping/fallback -----
    # exists() helpers
    mapping_exists_for_product = exists(
        select(M.id).where(and_(M.store_item_id == SI.id, M.product_id == product_id))
    )
    mapping_exists_any = exists(select(M.id).where(M.store_item_id == SI.id))

    subq_latest_per_item = (
        select(
            P.id.label("price_id"),
            P.store_id.label("store_id"),
            P.unit_price.label("unit_price"),
            P.price_eur.label("price_eur"),
            P.collected_at.label("collected_at"),
            func.row_number().over(
                partition_by=P.store_item_id,
                order_by=P.collected_at.desc(),
            ).label("rn_item"),
        )
        .join(SI, SI.id == P.store_item_id)
        .filter(
            or_(
                # Explicit mapping to the requested product
                mapping_exists_for_product,
                # Or: no mappings at all AND fallback matches
                and_(not_(mapping_exists_any), fallback_condition),
            )
        )
        .filter(P.collected_at >= func.date('now', f'-{RECENT_DAYS} days'))
    ).subquery()

    # ----- Stage B: single best offer per store (null unit_price last) -----
    subq_best_per_store = (
        select(
            subq_latest_per_item.c.price_id,
            func.row_number().over(
                partition_by=subq_latest_per_item.c.store_id,
                order_by=(
                    subq_latest_per_item.c.unit_price.is_(None),
                    subq_latest_per_item.c.unit_price.asc(),
                    subq_latest_per_item.c.price_eur.asc(),
                    subq_latest_per_item.c.collected_at.desc(),
                ),
            ).label("rn_store"),
        )
        .where(subq_latest_per_item.c.rn_item == 1)
    ).subquery()

    # 3. Main query: rows where rn_store = 1
    q = (
        db.query(P, S, SI)
        .join(subq_best_per_store, and_(P.id == subq_best_per_store.c.price_id, subq_best_per_store.c.rn_store == 1))
        .join(SI, SI.id == P.store_item_id)
        .join(S, S.id == P.store_id)
        .order_by(
            P.unit_price.is_(None),
            asc(P.unit_price),
            asc(P.price_eur),
            asc(S.name),
        )
    )

    rows = q.all()

    offers: list[PriceOut] = []
    seen_store_item = set()
    for price_obj, store, item in rows:
        store_item_key = (store.id, item.id)
        if store_item_key in seen_store_item:
            continue
        seen_store_item.add(store_item_key)

        offers.append(
            PriceOut(
                store=store.name,
                raw_name=item.raw_name,
                url=item.url,
                price_eur=price_obj.price_eur,
                unit_price=price_obj.unit_price,
                currency=price_obj.currency,
                collected_at=price_obj.collected_at,
                promo=price_obj.promo_flag,
            )
        )

    print(f"DEBUG: Found {len(offers)} offers for product_id {product_id}")
    if not offers:
        print(f"DEBUG: Query for product_id {product_id} returned no results matching the filter OR fallback.")

    return CompareOut(
        product=ProductOut(
            id=prod.id,
            canonical_name=prod.canonical_name,
            category=prod.category,
            unit=prod.unit,
            brand=prod.brand,
            size_ml_g=prod.size_ml_g,
            fat_pct=prod.fat_pct,
        ),
        offers=offers,
    )
