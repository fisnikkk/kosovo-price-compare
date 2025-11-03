# backend/app/schemas.py
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict

class ProductOut(BaseModel):
    id: int
    canonical_name: str
    category: str
    unit: str
    brand: Optional[str]
    size_ml_g: Optional[int]
    fat_pct: Optional[float]
    model_config = ConfigDict(from_attributes=True)

class PriceOut(BaseModel):
    store: str
    raw_name: str
    url: Optional[str]
    price_eur: float
    unit_price: Optional[float]
    currency: str
    collected_at: datetime
    promo: bool = False
    promo_valid_from: Optional[datetime] = None
    promo_valid_to: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)

class CompareOut(BaseModel):
    product: ProductOut
    offers: List[PriceOut]
    model_config = ConfigDict(from_attributes=True)
