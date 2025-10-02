# app/scrapers/vivafresh.py
from __future__ import annotations

import re
from sqlalchemy.orm import Session
from playwright.async_api import async_playwright, TimeoutError as PTimeout

from ..models import Store, StoreItem, Price
from ..utils.normalize import parse_size_and_fat, unit_price_eur

BASE = "https://online.vivafresh.shop/"

# Dairy & eggs lvl2 categories (adjust/add as needed)
DAIRY_SUBCATEGORIES = [13, 14, 15, 16, 17, 18, 19]

# Centralized selectors – easy to tweak
NAME_SELECTORS = [
    ".product-title", ".title", ".name", "h3", "a[title]"
]
PRICE_SELECTORS = [
    # text nodes
    ".current-price", ".new-price", ".price", ".product-price", ".price__current",
    # attributes
    "[data-price]", "[data-product-price]", "meta[itemprop=price]"
]
CARD_SELECTORS = ".product-card, .product-box, .product-item"

async def _accept_cookies_and_pick_location(page):
    # Accept cookies if there is a visible button
    try:
        for txt in ["Accept", "I agree", "Pranoj", "Lejo", "OK", "Continue"]:
            btns = page.get_by_text(txt, exact=False)
            if await btns.count():
                await btns.first.click(timeout=1500)
                await page.wait_for_timeout(300)
                break
    except PTimeout:
        pass

    # Pick a location if a modal appears (adjust the texts to what you actually see)
    try:
        for txt in ["Prishtinë", "Prishtina", "Qendër"]:
            el = page.get_by_text(txt, exact=False)
            if await el.count():
                await el.first.click(timeout=2000)
                await page.wait_for_timeout(500)
                break
    except PTimeout:
        pass

async def _scroll_to_load_all(page):
    last_h = 0
    for _ in range(40):
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(350)
        h = await page.evaluate("document.body.scrollHeight")
        if h == last_h:
            break
        last_h = h

async def crawl_vivafresh(db: Session, city: str = "Prishtina") -> int:
    # Ensure store exists
    store = db.query(Store).filter_by(slug="vivafresh").one_or_none()
    if not store:
        store = Store(name="Viva Fresh", slug="vivafresh", city=city)
        db.add(store); db.commit(); db.refresh(store)

    processed = 0

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/123.0 Safari/537.36 kpc/1.0"
        )
        page = await context.new_page()
        await page.goto(BASE, wait_until="domcontentloaded")
        await _accept_cookies_and_pick_location(page)

        for lvl2 in DAIRY_SUBCATEGORIES:
            url = f"{BASE}categories/?lvl2={lvl2}"
            await page.goto(url, wait_until="domcontentloaded")

            # Wait for grid/cards to be visible
            try:
                await page.wait_for_selector(CARD_SELECTORS, timeout=8000)
            except PTimeout:
                print(f"[vivafresh] no cards for lvl2={lvl2}")
                continue

            # Trigger lazy loading (infinite scroll)
            await _scroll_to_load_all(page)

            cards = await page.query_selector_all(CARD_SELECTORS)
            print(f"[vivafresh] lvl2={lvl2} found {len(cards)} cards")

            for c in cards:
                # --- NAME ---
                name = None
                for sel in NAME_SELECTORS:
                    el = await c.query_selector(sel)
                    if el:
                        txt = (await el.inner_text() or "").strip()
                        if txt:
                            name = txt
                            break
                if not name:
                    # fallback to card text, keep it short
                    name = ((await c.inner_text()) or "").strip().split("\n")[0]
                    if not name:
                        continue

                # --- PRICE (robust) ---
                price_eur = None

                # A) try explicit price containers/attributes/meta
                for sel in PRICE_SELECTORS:
                    el = await c.query_selector(sel)
                    if not el:
                        continue

                    # attribute-based selectors
                    if sel.startswith("[data-"):
                        attr = sel[1:-1]  # strip []
                        val = await el.get_attribute(attr)
                        if val:
                            try:
                                price_eur = float(val.replace(",", "."))
                                break
                            except:
                                pass
                        continue

                    if sel.startswith("meta["):
                        val = await el.get_attribute("content")
                        if val:
                            try:
                                price_eur = float(val.replace(",", "."))
                                break
                            except:
                                pass
                        continue

                    # text nodes
                    txt = (await el.inner_text() or "").strip()
                    txt = txt.replace("€", "").replace(",", ".")
                    m = re.search(r"\d+(?:\.\d+)?", txt)
                    if m:
                        try:
                            price_eur = float(m.group())
                            break
                        except:
                            pass

                # B) fallback: search whole card text
                if price_eur is None:
                    whole = (await c.inner_text() or "")
                    whole = whole.replace("€", "").replace(",", ".")
                    m = re.search(r"\d+(?:\.\d+)?", whole)
                    if m:
                        try:
                            price_eur = float(m.group())
                        except:
                            price_eur = None

                if price_eur is None:
                    # log first few misses so we can refine later
                    html_snip = (await c.inner_html() or "")[:300]
                    print("[vivafresh][debug] price not found; snippet:", html_snip)
                    continue

                # --- LINK ---
                urlp = None
                a = await c.query_selector("a[href]")
                if a:
                    href = await a.get_attribute("href")
                    if href:
                        urlp = href if href.startswith("http") else BASE.rstrip("/") + href

                # --- NORMALIZE & UPSERT ---
                size_ml_g, unit_hint, _fat = parse_size_and_fat(name)
                unit_price = unit_price_eur(price_eur, size_ml_g, unit_hint)

                item = db.query(StoreItem).filter_by(store_id=store.id, url=urlp).one_or_none()
                if not item:
                    item = StoreItem(
                        store_id=store.id,
                        external_id=(urlp or name)[:64],
                        raw_name=name,
                        raw_size=None,
                        url=urlp
                    )
                    db.add(item); db.flush()

                db.add(Price(store_item_id=item.id, price_eur=price_eur, unit_price=unit_price))
                processed += 1

        db.commit()
        await browser.close()

    print(f"[vivafresh] processed {processed} items")
    return processed
