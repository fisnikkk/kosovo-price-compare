# app/scrapers/maxi.py
from __future__ import annotations

import asyncio
import re
import httpx
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from ..models import Store, StoreItem, Price
from ..utils.normalize import parse_size_and_fat, unit_price_eur

BASE = "https://maxiks.shop"

# valid listing endpoints – you can add or remove subcategories as needed
LISTING_PATHS = [
    "/products?category=bulmet",        # entire Bulmet (dairy) category:contentReference[oaicite:2]{index=2}
    "/products?subcategory=jogurt",     # Jogurt subcategory:contentReference[oaicite:3]{index=3}
    "/products?subcategory=jogurt-frutash",  # fruit yogurts:contentReference[oaicite:4]{index=4}
    "/products?subcategory=kos",        # buttermilk/kefir
    "/products?subcategory=ajran",      # ayran
    "/products?subcategory=qumesht",    # qumësht (milk)
    "/products?subcategory=gjalpe-bulmet",   # gjalpë (butter)
    "/products?subcategory=gjize",      # gjize (curds)
    "/products?subcategory=krem-djathi",
    "/products?subcategory=kackavall",
    "/products?subcategory=speca-ajke",
    # Add other subcategories as needed
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

    # ensure the store exists in the database
    store = db.query(Store).filter_by(slug="maxi").one_or_none()
    if not store:
        store = Store(name="Maxi", slug="maxi", city=city)
        db.add(store)
        db.commit()
        db.refresh(store)

    processed_count = 0
    seen_products: set[str] = set()

    async with httpx.AsyncClient(base_url=BASE, headers=HEADERS, follow_redirects=True) as client:
        # Step 1: gather all product URLs from listing pages
        product_urls: list[str] = []

        for path in LISTING_PATHS:
            page = 1
            while True:
                url = f"{path}&page={page}" if page > 1 else path
                html = await fetch(client, url)
                if not html:
                    break

                soup = BeautifulSoup(html, "lxml")
                found_any = False

                for a in soup.select('a[href*="/product/"]'):
                    href = a.get("href")
                    if not href:
                        continue
                    # build absolute URL
                    full_url = href if href.startswith("http") else f"{BASE}{href}"
                    if full_url not in seen_products:
                        seen_products.add(full_url)
                        product_urls.append(full_url)
                        found_any = True

                # if no products found on this page, stop pagination
                if not found_any:
                    break
                page += 1

        # Step 2: fetch each product page and extract details
        for url in product_urls:
            html = await fetch(client, url)
            if not html:
                continue

            soup = BeautifulSoup(html, "lxml")
            # product name appears in h4.mb-2.p-title-main
            title_el = soup.select_one("h4.p-title-main, h4.mb-2.p-title-main")
            if not title_el:
                continue
            name = title_el.get_text(strip=True)

            # main price appears in span#main_price
            price_el = soup.select_one("#main_price")
            if not price_el:
                continue
            price_text = price_el.get_text(strip=True).replace("€", "").replace(",", ".")
            try:
                price_eur = float(re.sub(r"[^\d.]", "", price_text))
            except ValueError:
                continue

            # derive package size and unit price using your helper utils
            size_ml_g, unit_hint, _fat = parse_size_and_fat(name)
            unit_price = unit_price_eur(price_eur, size_ml_g, unit_hint)

            # upsert product
            item = db.query(StoreItem).filter_by(store_id=store.id, url=url).one_or_none()
            if not item:
                item = StoreItem(
                    store_id=store.id,
                    external_id=url[-64:],  # last 64 chars as an external id fallback
                    raw_name=name,
                    raw_size=None,
                    url=url,
                )
                db.add(item)
                db.flush()  # get item.id without full commit

            db.add(
                Price(
                    store_item_id=item.id,
                    price_eur=price_eur,
                    unit_price=unit_price,
                )
            )
            processed_count += 1

        db.commit()

    print(f"[maxi] processed {processed_count} items")
    return processed_count
