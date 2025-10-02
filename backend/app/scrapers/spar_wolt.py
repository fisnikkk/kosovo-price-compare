import httpx, asyncio
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session
from ..models import Store, StoreItem, Price
from ..utils.normalize import parse_size_and_fat, unit_price_eur

WOLT_VENUE = "https://wolt.com/en/xkx/pristina/venue/spar-te-qafa"

async def crawl_spar_wolt(db: Session, city: str = "Prishtina"):
    store = db.query(Store).filter_by(slug="spar-wolt").one_or_none()
    if not store:
        store = Store(name="SPAR (Wolt)", slug="spar-wolt", city=city)
        db.add(store); db.commit(); db.refresh(store)

    async with httpx.AsyncClient(headers={"User-Agent":"kpc/1.0"}) as s:
        r = await s.get(WOLT_VENUE, timeout=30)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "lxml")
        # Wolt renders server-side enough HTML to parse items (if not, you would need a headless browser)
        for card in soup.select("[data-test-id='menu-item'], .MenuItem"):
            name_el = card.select_one("[data-test-id='menu-item-title'], h3, h4")
            price_el = card.select_one("[data-test-id='menu-item-price'], .Price")
            if not name_el or not price_el: continue
            name = name_el.get_text(strip=True)
            price_txt = price_el.get_text(strip=True).replace("€","").replace(",", ".")
            try:
                price = float("".join(ch for ch in price_txt if ch.isdigit() or ch in "."))
            except:
                continue

            size_ml_g, unit_hint, _ = parse_size_and_fat(name)
            urlp = WOLT_VENUE  # one venue link
            item = db.query(StoreItem).filter_by(store_id=store.id, raw_name=name).one_or_none()
            if not item:
                item = StoreItem(store_id=store.id, external_id=name[:64], raw_name=name, url=urlp)
                db.add(item); db.commit(); db.refresh(item)
            up = unit_price_eur(price, size_ml_g, unit_hint)
            db.add(Price(store_item_id=item.id, price_eur=price, unit_price=up)); db.commit()
