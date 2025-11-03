# app/scrapers/maxi.py
from __future__ import annotations

import asyncio
import re
from datetime import date, datetime
import httpx
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime
from ..utils.normalize import classify, parse_fat_pct

from ..models import Store, StoreItem, Price
from ..utils.normalize import parse_size_and_fat, unit_price_eur

BASE = "https://maxiks.shop"

# valid listing endpoints
LISTING_PATHS = [
    "/products?category=bulmet",
    "/products?subcategory=jogurt",
    "/products?subcategory=jogurt-frutash",
    "/products?subcategory=kos",
    "/products?subcategory=ajran",
    "/products?subcategory=qumesht",
    "/products?subcategory=gjalpe-bulmet",
    "/products?subcategory=gjize",
    "/products?subcategory=krem-djathi",
    "/products?subcategory=kackavall",
    "/products?subcategory=speca-ajke",
]

HEADERS = {"User-Agent": "kosovo-price-compare/1.0 (+https://yourapp.example.com)"}


async def fetch(client: httpx.AsyncClient, url: str) -> str | None:
    """Fetch a page and return its HTML or None on failure."""
    try:
        resp = await client.get(url, timeout=30)
        resp.raise_for_status()
        return resp.text
    except (httpx.HTTPStatusError, httpx.RequestError) as e:
        print(f"[maxi] request failed for {url}: {e}")
        return None


async def crawl_maxi(db: Session, city: str | None = None) -> int:
    """
    Crawl Maxi's website for dairy products (Bulmet) and store their prices.
    Returns the number of products processed.
    """
    store = db.query(Store).filter_by(slug="maxi").one_or_none()
    if not store:
        store = Store(name="Maxi", slug="maxi", city=city)
        db.add(store)
        db.commit()
        db.refresh(store)

    processed_count = 0
    seen_products: set[str] = set()

    async with httpx.AsyncClient(base_url=BASE, headers=HEADERS, follow_redirects=True) as client:
        product_urls: list[str] = []
        for path in LISTING_PATHS:
            page = 1
            while True:
                url = f"{path}&page={page}" if page > 1 else path
                html = await fetch(client, url)
                if not html: break
                soup = BeautifulSoup(html, "lxml")
                found_any = False
                for a in soup.select('a[href*="/product/"]'):
                    href = a.get("href")
                    if not href: continue
                    full_url = href if href.startswith("http") else f"{BASE}{href}"
                    if full_url not in seen_products:
                        seen_products.add(full_url)
                        product_urls.append(full_url)
                        found_any = True
                if not found_any: break
                page += 1
        
        for url in product_urls:
            html = await fetch(client, url)
            if not html: continue
            soup = BeautifulSoup(html, "lxml")
            title_el = soup.select_one("h4.p-title-main, h4.mb-2.p-title-main")
            if not title_el: continue
            name = title_el.get_text(strip=True)
            price_el = soup.select_one("#main_price")
            if not price_el: continue
            price_text = price_el.get_text(strip=True).replace("€", "").replace(",", ".")
            try:
                price_eur = float(re.sub(r"[^\d.]", "", price_text))
            except ValueError:
                continue

            size_ml_g, unit_hint, _fat = parse_size_and_fat(name)
            unit_price = unit_price_eur(price_eur, size_ml_g, unit_hint)

            item = db.query(StoreItem).filter_by(store_id=store.id, url=url).one_or_none()
            if not item:
                item = StoreItem(
                    store_id=store.id,
                    external_id=url[-64:],
                    raw_name=name,
                    raw_size=None,
                    url=url,
                    category_norm = classify(name),
                    fat_pct = parse_fat_pct(name)
                )
                db.add(item)
                db.flush()

            # Same-day upsert logic
            existing = (
                db.query(Price)
                .filter(
                    Price.store_item_id == item.id,
                    func.date(Price.collected_at) == date.today().isoformat()
                )
                .first()
            )
            
            if existing:
                if abs(existing.price_eur - price_eur) > 1e-4 or existing.unit_price != unit_price:
                    existing.price_eur = price_eur
                    existing.unit_price = unit_price
                    existing.collected_at = datetime.utcnow()
            else:
                db.add(Price(
                    store_item_id=item.id,
                    store_id=store.id,
                    price_eur=price_eur,
                    unit_price=unit_price,
                    collected_at=datetime.utcnow()
                ))
            processed_count += 1
    db.commit()
    print(f"[maxi] processed {processed_count} items")
    return processed_count
