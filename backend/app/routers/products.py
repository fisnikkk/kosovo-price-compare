from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from ..db import SessionLocal
from ..models import Product
from ..schemas import ProductOut

router = APIRouter(prefix="/products", tags=["products"])

def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()

@router.get("/search", response_model=list[ProductOut])
def search_products(q: str = Query(..., min_length=1), db: Session = Depends(get_db)):
    rows = db.query(Product).filter(Product.canonical_name.ilike(f"%{q}%")).limit(50).all()
    return [ProductOut(**{
        "id": x.id, "canonical_name": x.canonical_name, "category": x.category, "unit": x.unit,
        "brand": x.brand, "size_ml_g": x.size_ml_g, "fat_pct": x.fat_pct
    }) for x in rows]

@router.get("/", response_model=list[ProductOut])
def list_products(db: Session = Depends(get_db)):
    rows = db.query(Product).order_by(Product.canonical_name).all()
    return [ProductOut(
        id=x.id, canonical_name=x.canonical_name, category=x.category, unit=x.unit,
        brand=x.brand, size_ml_g=x.size_ml_g, fat_pct=x.fat_pct
    ) for x in rows]
