import httpx, tempfile, os
from sqlalchemy.orm import Session
from bs4 import BeautifulSoup

from ..models import Store, StoreItem, Price
from ..utils.pdf_parser import parse_generic_flyer
from ..utils.normalize import parse_size_and_fat, unit_price_eur

LISTING = "https://fletushka.interex-rks.com/"

async def crawl_interex_flyer(db: Session, city: str | None = None):
    store = db.query(Store).filter_by(slug="interex").one_or_none()
    if not store:
        store = Store(name="Interex", slug="interex", city=city)
        db.add(store); db.commit(); db.refresh(store)

    async with httpx.AsyncClient(headers={"User-Agent": "kpc/1.0"}) as s:
        r = await s.get(LISTING, timeout=60)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "lxml")

        # Grab visible flyer blocks → find 'Shkarko PDF' anchors or any .pdf links
        pdf_urls = set()
        for a in soup.select("a"):
            href = a.get("href", "")
            text = a.get_text(" ", strip=True).lower()
            if href.lower().endswith(".pdf") or "shkarko pdf" in text:
                if href.startswith("http"):
                    pdf_urls.add(href)
                else:
                    pdf_urls.add(httpx.URL(LISTING).join(href))

        processed_total = 0
        for pdf_url in pdf_urls:
            r2 = await s.get(str(pdf_url), timeout=120)
            r2.raise_for_status()
            fd, path = tempfile.mkstemp(suffix=".pdf"); os.write(fd, r2.content); os.close(fd)

            items, (vfrom, vto) = parse_generic_flyer(path)
            print(f"[interex] parsed {len(items)} from {pdf_url}")

            for it in items:
                name = it["raw_name"]; price = it["price_eur"]
                size_ml_g, unit_hint, _ = parse_size_and_fat(name)

                # Interex flyers have no stable product URLs; key by name
                item = db.query(StoreItem).filter_by(store_id=store.id, raw_name=name).one_or_none()
                if not item:
                    item = StoreItem(store_id=store.id, external_id=name[:64], raw_name=name, url=str(pdf_url))
                    db.add(item); db.commit(); db.refresh(item)

                up = unit_price_eur(price, size_ml_g, unit_hint)
                db.add(Price(
                    store_item_id=item.id,
                    price_eur=price,
                    unit_price=up,
                    promo_flag=True,
                    promo_valid_from=vfrom,
                    promo_valid_to=vto,
                ))
                db.commit()
                processed_total += 1

        print(f"[interex] processed {processed_total} items from {LISTING}")
