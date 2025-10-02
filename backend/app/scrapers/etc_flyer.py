# app/scrapers/etc_flyer.py
from __future__ import annotations

import os
import re
import tempfile
import os as _os
from typing import List

import httpx
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session
from playwright.async_api import async_playwright, TimeoutError as PTimeout

from ..models import Store, StoreItem, Price
from ..utils.pdf_parser import parse_generic_flyer
from ..utils.normalize import parse_size_and_fat, unit_price_eur

DEFAULT_LISTING = "https://etc-ks.com/magazina.php"
ETC_LISTING = os.getenv("ETC_LISTING", DEFAULT_LISTING)

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)

PDF_RE = re.compile(r"""(?P<u>(?:https?:)?//[^'"<>\s]+?\.pdf(?:\?[^'"<>\s]*)?)""", re.I)
REL_PDF_RE = re.compile(r"""(?P<u>[^'"<>\s]+?\.pdf(?:\?[^'"<>\s]*)?)""", re.I)

def _dedupe(seq: List[str]) -> List[str]:
    seen = set(); out=[]
    for x in seq:
        if x not in seen:
            out.append(x); seen.add(x)
    return out

def _normalize_url(base: str, href: str) -> str:
    if not href:
        return ""
    # protocol-relative //domain/path
    if href.startswith("//"):
        href = "https:" + href
    return href if href.startswith("http") else str(httpx.URL(base).join(href))

def _extract_pdf_links_from_html(html: str, base: str) -> List[str]:
    soup = BeautifulSoup(html, "lxml")
    urls: List[str] = []

    # Obvious anchors
    for a in soup.select("a[href$='.pdf'], a[href*='.pdf']"):
        urls.append(_normalize_url(base, a.get("href", "")))

    # Nearby text that says PDF
    for a in soup.find_all("a"):
        txt = (a.get_text(" ", strip=True) or "").lower()
        href = a.get("href", "")
        if "pdf" in txt and href:
            urls.append(_normalize_url(base, href))

    # data-href
    for a in soup.select("[data-href]"):
        href = a.get("data-href", "")
        if ".pdf" in (href or "").lower():
            urls.append(_normalize_url(base, href))

    urls = [u for u in urls if u.lower().endswith(".pdf") or ".pdf?" in u.lower()]
    return _dedupe(urls)

async def _harvest_page_for_pdfs(page, base_url: str) -> List[str]:
    """Pull PDFs from *any* attribute, plus page HTML."""
    pdfs: List[str] = []

    # 1) From attribute sweep (href/src/data/onclick on ALL nodes)
    try:
        blobs = await page.eval_on_selector_all(
            "*",
            """els => els.map(e => ({
                href: e.getAttribute('href'),
                src: e.getAttribute('src'),
                data: e.getAttribute('data'),
                onclick: e.getAttribute('onclick')
            }))"""
        )
    except Exception:
        blobs = []

    for b in blobs or []:
        for key in ("href", "src", "data", "onclick"):
            val = (b.get(key) or "")
            # absolute/protocol-relative
            for m in PDF_RE.finditer(val):
                pdfs.append(_normalize_url(base_url, m.group("u")))
            # relative links inside attributes
            for m in REL_PDF_RE.finditer(val):
                pdfs.append(_normalize_url(base_url, m.group("u")))

    # 2) iframe/embed/object direct src/data
    for sel, attr in [("iframe[src]", "src"), ("embed[src]", "src"), ("object[data]", "data")]:
        try:
            for el in await page.query_selector_all(sel):
                v = await el.get_attribute(attr)
                if v and ".pdf" in v.lower():
                    pdfs.append(_normalize_url(base_url, v))
        except Exception:
            pass

    # 3) From full HTML content
    try:
        html = await page.content()
        for m in PDF_RE.finditer(html):
            pdfs.append(_normalize_url(base_url, m.group("u")))
        # and relative occurrences
        for m in REL_PDF_RE.finditer(html):
            pdfs.append(_normalize_url(base_url, m.group("u")))
    except Exception:
        pass

    return _dedupe(pdfs)

async def _collect_pdf_urls_headless_async(listing_url: str) -> List[str]:
    """Visit listing; if needed, follow detail pages and harvest PDFs."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(user_agent=UA)
        page = await ctx.new_page()

        await page.goto(listing_url, wait_until="domcontentloaded", timeout=30000)
        try:
            await page.wait_for_load_state("networkidle", timeout=5000)
        except PTimeout:
            pass

        # First, try harvesting directly from listing page.
        pdfs = await _harvest_page_for_pdfs(page, listing_url)
        if pdfs:
            await browser.close()
            return _dedupe(pdfs)

        # If none, gather potential detail links from all anchors.
        try:
            hrefs = await page.eval_on_selector_all("a[href]", "els => els.map(e => e.getAttribute('href'))")
        except Exception:
            hrefs = []

        hrefs = [h or "" for h in hrefs]
        hrefs = [_normalize_url(listing_url, h) for h in hrefs]
        candidates: List[str] = []

        for h in hrefs:
            hl = h.lower()
            if (
                hl.startswith("http")
                and "etc-ks.com" in hl
                and (".php" in hl or "/magazina" in hl or "/fletushk" in hl or "leaflet" in hl or "show" in hl)
                and ".pdf" not in hl        # skip direct PDFs (we already have none anyway)
            ):
                candidates.append(h)

        if not candidates:
            # last resort: any internal php page
            candidates = [h for h in hrefs if "etc-ks.com" in h.lower() and h.lower().endswith(".php")]

        found: List[str] = []
        for link in _dedupe(candidates)[:20]:
            try:
                dp = await ctx.new_page()
                await dp.goto(link, wait_until="domcontentloaded", timeout=30000)
                try:
                    await dp.wait_for_load_state("networkidle", timeout=4000)
                except PTimeout:
                    pass
                found.extend(await _harvest_page_for_pdfs(dp, link))
                await dp.close()
            except Exception:
                pass

        await browser.close()
        return _dedupe(found)

# ---------------- main entry ----------------

async def crawl_etc_flyer(db: Session, city: str = "Prishtina"):
    store = db.query(Store).filter_by(slug="etc-flyer").one_or_none()
    if not store:
        store = Store(name="ETC (Flyer)", slug="etc-flyer", city=city)
        db.add(store); db.commit(); db.refresh(store)

    # 1) Try plain HTML first
    async with httpx.AsyncClient(headers={"User-Agent": UA}, follow_redirects=True) as s:
        pdf_urls: List[str] = []
        try:
            r = await s.get(ETC_LISTING, timeout=60)
            if r.status_code == 200:
                pdf_urls = _extract_pdf_links_from_html(r.text, ETC_LISTING)
        except Exception:
            pdf_urls = []

    # 2) Headless: listing page
    if not pdf_urls:
        pdf_urls = await _collect_pdf_urls_headless_async(ETC_LISTING)

    # 3) Headless: www variant
    if not pdf_urls and "://etc-ks.com/" in ETC_LISTING:
        alt = ETC_LISTING.replace("://etc-ks.com/", "://www.etc-ks.com/")
        pdf_urls = await _collect_pdf_urls_headless_async(alt)

    print(f"[etc-flyer] found {len(pdf_urls)} pdf links")

    processed = 0
    async with httpx.AsyncClient(headers={"User-Agent": UA}, follow_redirects=True) as s:
        for pdf_url in pdf_urls:
            try:
                r = await s.get(pdf_url, timeout=90)
                ct = (r.headers.get("content-type") or "").lower()
                if r.status_code != 200 or "pdf" not in ct:
                    continue
                fd, path = tempfile.mkstemp(suffix=".pdf")
                _os.write(fd, r.content); _os.close(fd)
            except Exception:
                continue

            # parse PDF -> items
            try:
                items, (vfrom, vto) = parse_generic_flyer(path)
            except Exception:
                try:
                    items = parse_generic_flyer(path)
                    vfrom = vto = None
                except Exception:
                    items = []
                    vfrom = vto = None

            print(f"[etc-flyer] parsed {len(items)} from {pdf_url}")

            for it in items:
                name = it["raw_name"]; price = it["price_eur"]
                size_ml_g, unit_hint, _ = parse_size_and_fat(name)

                item = db.query(StoreItem).filter_by(store_id=store.id, raw_name=name).one_or_none()
                if not item:
                    item = StoreItem(
                        store_id=store.id,
                        external_id=name[:64],
                        raw_name=name,
                        url=pdf_url,
                    )
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
                processed += 1

    print(f"[etc-flyer] processed {processed} items")
