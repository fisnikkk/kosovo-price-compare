from __future__ import annotations
import httpx, tempfile, os, re
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session
from datetime import datetime

from ..models import Store, StoreItem, Price
from ..utils.pdf_parser import parse_generic_flyer
from ..utils.normalize import parse_size_and_fat, unit_price_eur

HOME = "https://spar-kosova.com/"

async def _find_flyer_pdfs(html: str, base: str) -> list[str]:
    soup = BeautifulSoup(html, "lxml")
    urls = []
    for a in soup.select("a"):
        href = a.get("href", "")
        text = a.get_text(" ", strip=True).lower()
        if href.lower().endswith(".pdf") or "oferta" in text or "fletushk" in text:
            full = href if href.startswith("http") else str(httpx.URL(base).join(href))
            if full.lower().endswith(".pdf"):
                urls.append(full)
    # dedupe while preserving order
    seen = set(); out=[]
    for u in urls:
        if u not in seen:
            out.append(u); seen.add(u)
    return out

async def crawl_spar_flyer(db: Session, city: str = "Prishtina"):
    store = db.query(Store).filter_by(slug="spar-flyer").one_or_none()
    if not store:
        store = Store(name="SPAR (Flyer)", slug="spar-flyer", city=city)
        db.add(store); db.commit(); db.refresh(store)

    async with httpx.AsyncClient(headers={"User-Agent": "kpc/1.0"}) as s:
        r = await s.get(HOME, timeout=60)
        r.raise_for_status()
        pdf_urls = await _find_flyer_pdfs(r.text, HOME)

        processed_total = 0
        for pdf_url in pdf_urls:
            r2 = await s.get(pdf_url, timeout=120)
            if r2.status_code != 200 or "application/pdf" not in r2.headers.get("content-type", ""):
                # Some SPAR pages link to an intermediate page; try to resolve one level deep
                r_mid = await s.get(pdf_url, timeout=60)
                soup_mid = BeautifulSoup(r_mid.text, "lxml")
                for a in soup_mid.select("a[href$='.pdf']"):
                    pdf_url = str(httpx.URL(pdf_url).join(a.get("href")))
                    r2 = await s.get(pdf_url, timeout=120)
                    if r2.status_code == 200:
                        break

            if r2.status_code != 200:
                print(f"[spar-flyer] skip non-200 for {pdf_url}")
                continue

            fd, path = tempfile.mkstemp(suffix=".pdf"); os.write(fd, r2.content); os.close(fd)
            items, (vfrom, vto) = parse_generic_flyer(path)
            print(f"[spar-flyer] parsed {len(items)} from {pdf_url}")

            for it in items:
                name = it["raw_name"]; price = it["price_eur"]
                size_ml_g, unit_hint, _ = parse_size_and_fat(name)

                item = db.query(StoreItem).filter_by(store_id=store.id, raw_name=name).one_or_none()
                if not item:
                    item = StoreItem(store_id=store.id, external_id=name[:64], raw_name=name, url=pdf_url, category=it.get("category"))
                    db.add(item); db.commit(); db.refresh(item)

                up = unit_price_eur(price, size_ml_g, unit_hint)
                db.add(Price(store_item_id=item.id, price_eur=price, unit_price=up,
                             promo_flag=True, promo_valid_from=vfrom, promo_valid_to=vto, collected_at=datetime.utcnow()))
                db.commit()
                processed_total += 1

        print(f"[spar-flyer] processed {processed_total} items")
