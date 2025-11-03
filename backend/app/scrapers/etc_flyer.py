# app/scrapers/etc_flyer.py
from __future__ import annotations

import os
import tempfile
import os as _os
from typing import List
from datetime import date, datetime
import httpx
import anyio
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime

from ..models import Store, StoreItem, Price
from ..utils.pdf_parser import parse_generic_flyer
from ..utils.normalize import parse_size_and_fat, unit_price_eur

DEFAULT_LISTING = "https://etc-ks.com/magazina.php"
ETC_LISTING = os.getenv("ETC_LISTING", DEFAULT_LISTING)
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"

async def _collect_pdf_urls_headless_async(listing_url: str) -> List[str]:
    from ._playwright_thread import collect_etc_pdfs_sync
    return await anyio.to_thread.run_sync(collect_etc_pdfs_sync, listing_url)

async def crawl_etc_flyer(db: Session, city: str = "Prishtina"):
    store = db.query(Store).filter_by(slug="etc-flyer").one_or_none()
    if not store:
        store = Store(name="ETC (Flyer)", slug="etc-flyer", city=city)
        db.add(store); db.commit(); db.refresh(store)

    pdf_urls = await _collect_pdf_urls_headless_async(ETC_LISTING)
    if not pdf_urls and "://etc-ks.com/" in ETC_LISTING:
        alt = ETC_LISTING.replace("://etc-ks.com/", "://www.etc-ks.com/")
        pdf_urls = await _collect_pdf_urls_headless_async(alt)

    print(f"[etc-flyer] found {len(pdf_urls)} pdf links")
    processed = 0
    async with httpx.AsyncClient(headers={"User-Agent": UA}, follow_redirects=True) as s:
        for pdf_url in pdf_urls:
            path = None
            try:
                r = await s.get(pdf_url, timeout=90)
                ct = (r.headers.get("content-type") or "").lower()
                if r.status_code != 200 or "pdf" not in ct: continue
                fd, path = tempfile.mkstemp(suffix=".pdf")
                _os.write(fd, r.content); _os.close(fd)
                
                items, (vfrom, vto) = parse_generic_flyer(path)
            except Exception:
                items, vfrom, vto = [], None, None
            finally:
                if path and _os.path.exists(path):
                    _os.unlink(path)

            for it in items:
                name, price = it["raw_name"], it["price_eur"]
                size_ml_g, unit_hint, _ = parse_size_and_fat(name)

                item = db.query(StoreItem).filter_by(store_id=store.id, raw_name=name).one_or_none()
                if not item:
                    item = StoreItem(store_id=store.id, external_id=name[:64], raw_name=name, url=pdf_url, category=it.get("category"))
                    db.add(item); db.flush(); db.refresh(item)
                
                up = unit_price_eur(price, size_ml_g, unit_hint)
                
                # Same-day upsert logic
                existing = (
                    db.query(Price)
                    .filter(
                        Price.store_item_id == item.id,
                        func.date(Price.collected_at) == date.today().isoformat()
                    )
                    .one_or_none()
                )
                
                if existing:
                    if abs(existing.price_eur - price) > 1e-4 or existing.unit_price != up:
                        existing.price_eur = price
                        existing.unit_price = up
                        existing.collected_at = datetime.utcnow()
                else:
                    db.add(Price(
                        store_item_id=item.id,
                        store_id=store.id,
                        price_eur=price,
                        unit_price=up,
                        promo_flag=True,
                        promo_valid_from=vfrom,
                        promo_valid_to=vto,
                        collected_at=datetime.utcnow()
                    ))
                processed += 1
            db.commit()
    print(f"[etc-flyer] processed {processed} items")
