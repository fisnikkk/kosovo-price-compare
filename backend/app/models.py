from sqlalchemy import String, Integer, Float, ForeignKey, DateTime, Boolean, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime
from .db import Base

class Store(Base):
    __tablename__ = "stores"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    city: Mapped[str | None] = mapped_column(String(80), nullable=True)
    items: Mapped[list["StoreItem"]] = relationship(back_populates="store")

class Product(Base):
    __tablename__ = "products"
    id: Mapped[int] = mapped_column(primary_key=True)
    canonical_name: Mapped[str] = mapped_column(String(200), index=True)
    category: Mapped[str] = mapped_column(String(80), index=True)
    unit: Mapped[str] = mapped_column(String(8))  # "kg" or "l" (price per)
    brand: Mapped[str | None] = mapped_column(String(80))
    size_ml_g: Mapped[int | None] = mapped_column(Integer)  # canonical reference size (optional)
    fat_pct: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class StoreItem(Base):
    __tablename__ = "store_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"))
    external_id: Mapped[str | None] = mapped_column(String(128), index=True)
    raw_name: Mapped[str] = mapped_column(String(300))
    raw_size: Mapped[str | None] = mapped_column(String(80))
    url: Mapped[str | None] = mapped_column(String(300))
    store: Mapped["Store"] = relationship(back_populates="items")
    prices: Mapped[list["Price"]] = relationship(back_populates="item")
    mappings: Mapped[list["Mapping"]] = relationship(back_populates="item")
    __table_args__ = (Index("ix_store_external", "store_id", "external_id"),)

class Price(Base):
    __tablename__ = "prices"
    id: Mapped[int] = mapped_column(primary_key=True)
    store_item_id: Mapped[int] = mapped_column(ForeignKey("store_items.id"))
    price_eur: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(8), default="€")
    collected_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    promo_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    promo_valid_from: Mapped[datetime | None] = mapped_column(DateTime)
    promo_valid_to: Mapped[datetime | None] = mapped_column(DateTime)
    unit_price: Mapped[float | None] = mapped_column(Float)  # €/kg or €/l
    item: Mapped["StoreItem"] = relationship(back_populates="prices")

class Mapping(Base):
    __tablename__ = "mappings"
    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    store_item_id: Mapped[int] = mapped_column(ForeignKey("store_items.id"))
    match_score: Mapped[float] = mapped_column(Float)
    product: Mapped["Product"] = relationship()
    item: Mapped["StoreItem"] = relationship(back_populates="mappings")
    __table_args__ = (UniqueConstraint("product_id", "store_item_id"),)
