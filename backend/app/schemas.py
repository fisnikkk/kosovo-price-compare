from pydantic import BaseModel
from datetime import datetime

class PriceOut(BaseModel):
    store: str
    raw_name: str
    url: str | None
    price_eur: float
    unit_price: float | None
    currency: str
    collected_at: datetime
    promo: bool = False
    promo_valid_from: datetime | None = None
    promo_valid_to: datetime | None = None

class ProductOut(BaseModel):
    id: int
    canonical_name: str
    category: str
    unit: str
    brand: str | None
    size_ml_g: int | None
    fat_pct: float | None

class CompareOut(BaseModel):
    product: ProductOut
    offers: list[PriceOut]
