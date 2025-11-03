# backend/app/routers/products.py
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from ..db import SessionLocal
from ..models import Product, Mapping, Price, StoreItem
from ..schemas import ProductOut

router = APIRouter(prefix="/products", tags=["products"])

# keep consistent with compare
RECENT_DAYS = 14


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/search", response_model=list[ProductOut])
def search_products(q: str = Query(..., min_length=1), db: Session = Depends(get_db)):
    rows = (
        db.query(Product)
        .filter(Product.canonical_name.ilike(f"%{q}%"))
        .limit(50)
        .all()
    )
    return [
        ProductOut(
            id=x.id,
            canonical_name=x.canonical_name,
            category=x.category,
            unit=x.unit,
            brand=x.brand,
            size_ml_g=x.size_ml_g,
            fat_pct=x.fat_pct,
        )
        for x in rows
    ]


@router.get("/", response_model=list[ProductOut])
def list_products(db: Session = Depends(get_db)):
    rows = db.query(Product).order_by(Product.canonical_name).limit(500).all()
    return [
        ProductOut(
            id=x.id,
            canonical_name=x.canonical_name,
            category=x.category,
            unit=x.unit,
            brand=x.brand,
            size_ml_g=x.size_ml_g,
            fat_pct=x.fat_pct,
        )
        for x in rows
    ]


@router.get("/popular", response_model=list[ProductOut])
def popular_products(
    db: Session = Depends(get_db),
    limit: int = Query(50, ge=1, le=200),
    min_price_rows: int = Query(1, ge=1, le=5),
):
    """
    Returns products that actually have recent price rows (via Mapping → StoreItem → Price).
    Ordered by 'number of recent price rows' desc, then name.
    """
    subq = (
        db.query(
            Mapping.product_id.label("pid"),
            func.count(Price.id).label("n")
        )
        .join(StoreItem, StoreItem.id == Mapping.store_item_id)
        .join(Price, Price.store_item_id == StoreItem.id)
        .filter(Price.collected_at >= func.date('now', f'-{RECENT_DAYS} days'))
        .group_by(Mapping.product_id)
        .subquery()
    )

    rows = (
        db.query(Product)
        .join(subq, subq.c.pid == Product.id)
        .filter(subq.c.n >= min_price_rows)
        .order_by(subq.c.n.desc(), Product.canonical_name.asc())
        .limit(limit)
        .all()
    )

    return [
        ProductOut(
            id=x.id,
            canonical_name=x.canonical_name,
            category=x.category,
            unit=x.unit,
            brand=x.brand,
            size_ml_g=x.size_ml_g,
            fat_pct=x.fat_pct,
        )
        for x in rows
    ]
