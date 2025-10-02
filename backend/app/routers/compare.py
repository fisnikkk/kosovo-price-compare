from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import select, func, desc
from ..db import SessionLocal
from ..models import Product, Mapping, StoreItem, Price, Store
from ..schemas import CompareOut, ProductOut, PriceOut

router = APIRouter(prefix="/compare", tags=["compare"])

def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()

@router.get("", response_model=CompareOut)
def compare_prices(product_id: int = Query(...), db: Session = Depends(get_db)):
    prod = db.get(Product, product_id)
    if not prod:
        raise HTTPException(status_code=404, detail="Product not found")
    # Latest price per item mapped to this product
    q = (
        db.query(Price, StoreItem, Store)
        .join(StoreItem, StoreItem.id == Price.store_item_id)
        .join(Mapping, Mapping.store_item_id == StoreItem.id)
        .join(Store, Store.id == StoreItem.store_id)
        .filter(Mapping.product_id == product_id)
        .order_by(Store.id, desc(Price.collected_at))
    )
    # pick latest per store_item
    latest = {}
    for p, item, store in q:
        if item.id not in latest:
            latest[item.id] = (p, item, store)

    offers = []
    for p, item, store in latest.values():
        offers.append(PriceOut(
            store=store.name, raw_name=item.raw_name, url=item.url,
            price_eur=p.price_eur, unit_price=p.unit_price, currency=p.currency,
            collected_at=p.collected_at, promo=p.promo_flag,
            promo_valid_from=p.promo_valid_from, promo_valid_to=p.promo_valid_to
        ))
    offers.sort(key=lambda x: (x.unit_price if x.unit_price is not None else 9999, x.price_eur))
    return CompareOut(
        product=ProductOut(
            id=prod.id, canonical_name=prod.canonical_name, category=prod.category,
            unit=prod.unit, brand=prod.brand, size_ml_g=prod.size_ml_g, fat_pct=prod.fat_pct
        ),
        offers=offers
    )
