# backend/app/models.py
from datetime import datetime
from typing import List, Optional

from sqlalchemy import (
    String, Integer, Float, ForeignKey, DateTime, Boolean, UniqueConstraint, Index, func, Column
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .db import Base

class Store(Base):
    __tablename__ = "stores"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    city: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)

    store_items: Mapped[List["StoreItem"]] = relationship(back_populates="store")
    prices: Mapped[List["Price"]] = relationship(back_populates="store")

class Product(Base):
    __tablename__ = "products"
    id: Mapped[int] = mapped_column(primary_key=True)
    canonical_name: Mapped[str] = mapped_column(String(200), index=True)
    category: Mapped[str] = mapped_column(String(80), index=True)
    unit: Mapped[str] = mapped_column(String(8))  # "kg" or "l" (price per)
    brand: Mapped[Optional[str]] = mapped_column(String(80))
    size_ml_g: Mapped[Optional[int]] = mapped_column(Integer)
    fat_pct: Mapped[Optional[float]] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class StoreItem(Base):
    __tablename__ = "store_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"), index=True)

    # original columns (no product_id here)
    external_id: Mapped[Optional[str]] = mapped_column(String(128), index=True)
    raw_name: Mapped[str] = mapped_column(String(300))
    raw_size: Mapped[Optional[str]] = mapped_column(String(80))
    url: Mapped[Optional[str]] = mapped_column(String(300))
    brand: Mapped[Optional[str]] = mapped_column(String(120))
    category: Mapped[Optional[str]] = mapped_column(String(120))

    # --- 👇 ADDITIONS FROM THE REPORT ---
    category_norm: Mapped[Optional[str]] = mapped_column(String(80), index=True)
    fat_pct: Mapped[Optional[float]] = mapped_column(Float)
    # --- END ADDITIONS ---

    store: Mapped["Store"] = relationship(back_populates="store_items")
    prices: Mapped[List["Price"]] = relationship(
        back_populates="store_item", cascade="all, delete-orphan"
    )
    mappings: Mapped[List["Mapping"]] = relationship(back_populates="item")

    __table_args__ = (Index("ix_store_external", "store_id", "external_id"),)

class Price(Base):
    __tablename__ = "prices"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    store_item_id: Mapped[int] = mapped_column(ForeignKey("store_items.id"), index=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"), index=True)

    price_eur: Mapped[float] = mapped_column(Float)
    unit_price: Mapped[Optional[float]] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(8), default="€")

    # 👇 add defaults so inserts never pass NULL
    collected_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        server_default=func.now()
    )

    promo_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    promo_valid_from: Mapped[Optional[datetime]] = mapped_column(DateTime)
    promo_valid_to: Mapped[Optional[datetime]] = mapped_column(DateTime)

    store_item: Mapped["StoreItem"] = relationship(back_populates="prices")
    store: Mapped["Store"] = relationship(back_populates="prices")

class Mapping(Base):
    __tablename__ = "mappings"
    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    store_item_id: Mapped[int] = mapped_column(ForeignKey("store_items.id"))
    match_score: Mapped[float] = mapped_column(Float)

    product: Mapped["Product"] = relationship()
    item: Mapped["StoreItem"] = relationship(back_populates="mappings")

    __table_args__ = (UniqueConstraint("product_id", "store_item_id"),)
