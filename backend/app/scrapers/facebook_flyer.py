# backend/app/scrapers/facebook_flyer.py
from __future__ import annotations
import asyncio, tempfile, os, re, logging, httpx, anyio
import urllib.parse as up
from typing import Optional, List, Tuple
from sqlalchemy.orm import Session
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from dotenv import load_dotenv
from PIL import Image  # For aspect-ratio check
from datetime import datetime
from ..utils.normalize import canon_store, parse_fat_pct, classify

# --- PATCH A: Constants & helpers START ---
import datetime as dt
import json

# Tunables (also read from env if set)
DEFAULT_WANT_N = int(os.getenv("FB_WANT_N", "12"))
MAX_AGE_DAYS = int(os.getenv("FB_MAX_AGE_DAYS", "10"))  # skip photos older than this

# Heuristics for product-vs-greeting
PRICE_PAT = re.compile(r'(\d+[.,]?\d*)\s?(€|eur|euro)\b', re.I)
PCT_PAT   = re.compile(r'\b\d{1,2}\s?%')  # 5%, 10 %, etc.
UNIT_PAT  = re.compile(r'\b(\d+(\.\d+)?)\s?(kg|g|l|ml)\b', re.I)

PROMO_WORDS = [
    "ofert", "zbritje", "akc", "super çmim", "cmim", "çmim", "promo", "ulje",
    "speciale", "aksion", "akcija", "popust"
]
GREETING_WORDS = [
    "gëzuar", "urime", "përshëndetje", "fest", "viti i ri", "shën valentine",
    "pashk", "bajram", "kristlindje"
]

def _text_has_any(text: str, words: list[str]) -> bool:
    t = text.lower()
    return any(w in t for w in words)

def looks_like_product(text: str) -> bool:
    """Cheap classifier: keep if price, % or unit is present or promo wording appears."""
    if not text:
        return False
    if PRICE_PAT.search(text): return True
    if PCT_PAT.search(text):   return True
    if UNIT_PAT.search(text):  return True
    if _text_has_any(text, PROMO_WORDS): return True
    return False

def looks_like_greeting(text: str) -> bool:
    if not text:
        return False
    return _text_has_any(text, GREETING_WORDS)

def _parse_fb_epoch_from_datastore_attr(tag) -> int | None:
    """m.facebook often puts an attribute like data-store='{"time": 1729876543, ...}'."""
    ds = tag.get("data-store") or tag.get("data-store-id") or ""
    if not ds:
        return None
    try:
        js = json.loads(ds)
        # Facebook varies: "time", "publish_time", "creation_time"
        for k in ("time", "publish_time", "creation_time", "utime"):
            if k in js and isinstance(js[k], (int, float)):
                return int(js[k])
    except Exception:
        pass
    return None

# --- NEW FUNCTION from Instruction D ---
async def _get_with_dns_retry(s: httpx.AsyncClient, url: str, **kw):
    for i in range(3):
        try:
            return await s.get(url, **kw)
        except httpx.ConnectError:
            if i == 2: raise
            await anyio.sleep(0.7 * (i+1))
        except httpx.ConnectTimeout:
            if i == 2: raise
            await anyio.sleep(0.7 * (i+1))
# --- END NEW FUNCTION ---

async def _extract_post_timestamp(s, href: str) -> dt.datetime | None:
    """
    Return UTC datetime for a photo/story link (m.facebook.com or www.facebook.com).
    Tries several strategies because FB markup varies by surface, locale, and session.
    """
    if not href:
        return None
    url = href
    if url.startswith("/"):
        url = "https://m.facebook.com" + url
    # prefer m-dot, but let redirects go to www if needed
    url = url.replace("mbasic.facebook.com", "m.facebook.com")

    r = await s.get(url, follow_redirects=True)
    html = r.text
    soup = BeautifulSoup(html, "html.parser")

    # 1) Structured hints on visible tags (best case on m.facebook)
    for tag in soup.find_all(["abbr", "time", "span"], attrs=True):
        epoch = _parse_fb_epoch_from_datastore_attr(tag)
        if epoch:
            return dt.datetime.utcfromtimestamp(epoch)

    # 2) Meta properties (sometimes present on www)
    for prop in ("og:updated_time", "og:published_time", "article:published_time"):
        meta = soup.find("meta", attrs={"property": prop})
        if meta and meta.get("content"):
            try:
                return dt.datetime.fromisoformat(meta["content"].replace("Z", "+00:00")).astimezone(dt.timezone.utc).replace(tzinfo=None)
            except Exception:
                pass

    # 3) JSON-LD blocks
    try:
        for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
            try:
                data = json.loads(script.string or "{}")
            except Exception:
                continue
            for key in ("datePublished", "uploadDate", "dateCreated"):
                val = data.get(key)
                if isinstance(val, str) and val:
                    try:
                        dtv = dt.datetime.fromisoformat(val.replace("Z", "+00:00")).astimezone(dt.timezone.utc).replace(tzinfo=None)
                        return dtv
                    except Exception:
                        continue
    except Exception:
        pass

    # 4) Script-blob regex (very robust): scan raw HTML for an epoch
    #    Common keys: publish_time, creation_time, utime (all seconds since epoch)
    m = re.search(r'(?:"publish_time"|\"creation_time\"|\"utime\")\s*:\s*(\d{10})', html)
    if m:
        try:
            return dt.datetime.utcfromtimestamp(int(m.group(1)))
        except Exception:
            pass

    # 5) As a last resort, parse human text (locale dependent; try English months too)
    #    We look at title attributes on abbr/time or visible text like "October 13 at 7:00 PM"
    for tag in soup.find_all(["abbr", "time"]):
        title = (tag.get("title") or "").strip()
        if title:
            try:
                # loose parse; assumes server returns English or ISO-ish strings
                return dt.datetime.fromisoformat(title.replace(" at ", " ").replace("Z", "+00:00"))
            except Exception:
                pass
        txt = (tag.get_text() or "").strip()
        if txt:
            # Try a coarse month-name match in English; skip if clearly relative like "2h"
            if not re.search(r'\b\d+h\b|\b\d+m\b', txt):
                try:
                    # Very forgiving: let dateutil parse if you have it; otherwise skip this branch
                    from dateutil import parser as du_parser  # optional
                    return du_parser.parse(txt, fuzzy=True).astimezone(dt.timezone.utc).replace(tzinfo=None)
                except Exception:
                    pass

    return None
# --- PATCH A: Constants & helpers END ---


from ..models import Store, StoreItem, Price
from ..utils.pdf_parser import parse_text_for_items
from ..utils.normalize import parse_size_and_fat, unit_price_eur
from ..utils.image_ocr import ocr_image_to_text

logger = logging.getLogger(__name__)
load_dotenv()

FB_COOKIE = os.getenv("FB_COOKIE")

if FB_COOKIE:
    logger.info("[fb] FB_COOKIE detected (length=%d)", len(FB_COOKIE))
else:
    logger.warning("[fb] FB_COOKIE missing — Facebook may hide Photos; add it to backend/.env")

FULLSIZE_HINTS = ("view_source", "view_full_size", "view_full", "download", "Shiko madhësi të plotë", "View Full Size")


def _extract_page_slug(page_url: str) -> str:
    parts = urlparse(page_url).path.strip("/").split("/")
    if not parts or parts == ['']: return page_url
    if len(parts) >= 2 and parts[-1].lower() == "photos": return parts[-2]
    return parts[0]

def _key_for_dedupe(u: str) -> str:
    """
    Key for dedupe only: do NOT change path (keeps fb signature valid).
    We only drop 'stp' from the query so that size-hinted variants dedupe together.
    """
    pr = up.urlparse(u)
    q = up.parse_qs(pr.query)
    q.pop("stp", None)
    new_query = up.urlencode({k: v[0] for k, v in q.items()}, doseq=False)
    return pr._replace(query=new_query).geturl()

def _extract_photo_id_from_referer(referer: str) -> Optional[str]:
    """
    Try to extract a stable photo id from the photo permalink.
    Supports /photo.php?fbid=... and /photos/.../<id>/... patterns.
    """
    if not referer:
        return None
    try:
        pr = up.urlparse(referer)
        q = up.parse_qs(pr.query)
        for key in ("fbid", "id"):
            if key in q and q[key]:
                return q[key][0]
        m = re.search(r"/photos/(?:[^/]+/)?(\d+)", pr.path or "")
        if m:
            return m.group(1)
    except Exception:
        pass
    return None

async def crawl_facebook_flyer(
    db: Session,
    slug: str,
    store_name: str,
    fb_page_url: str,
    city: Optional[str] = None,
    scroll_pages: int = 6,
    want_n: int = DEFAULT_WANT_N,
) -> None:
    store = db.query(Store).filter_by(slug=slug).one_or_none()
    if not store:
        store = Store(name=store_name, slug=slug, city=city)
        db.add(store); db.commit(); db.refresh(store)

    logger.info(f"[{slug}] scraping {fb_page_url}")
    image_pairs = await _get_offer_images_from_facebook(
        fb_page_url, scroll_pages=scroll_pages, want_n=want_n
    )

    if not image_pairs:
        logger.warning(f"[{slug}] no flyer images found")
        return

    processed = 0
    fb_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
        "Accept-Language": "sq-AL,sq;q=0.9,en;q=0.8",
    }
    if FB_COOKIE:
        fb_headers["Cookie"] = FB_COOKIE

    async with httpx.AsyncClient(headers=fb_headers, timeout=120, follow_redirects=True, http2=True) as s:
        for url, referer in image_pairs:
            # Require a usable referer (photo permalink) so we can timestamp-filter and dedupe correctly
            if not isinstance(referer, str) or not ("/photo.php" in referer or "/photos/" in referer):
                logger.info(f"[{slug}] skipping cdn-only image (no photo permalink referer)")
                continue

            path = None
            try:
                # Before OCR, cheaply reject obvious non-flyer PNGs unless we later detect product signals
                is_png = url.lower().endswith(".png")

                # --- PATCH C: Recency filter START ---
                is_photo_ref = isinstance(referer, str) and ("/photo.php" in referer or "/photos/" in referer)
                if is_photo_ref:
                    try:
                        ts = await _extract_post_timestamp(s, referer)
                        if ts:
                            age_days = (dt.datetime.utcnow() - ts).days
                            if age_days > MAX_AGE_DAYS:
                                logger.info(f"[{slug}] skip {referer} (age {age_days}d > {MAX_AGE_DAYS})")
                                continue
                    except Exception as _:
                        pass
                # --- PATCH C: Recency filter END ---

                request_headers = fb_headers.copy()
                request_headers["Referer"] = referer  # photo page as referer

                # IMPORTANT: request the EXACT (raw) fbcdn URL
                r = await s.get(url, headers=request_headers)

                if r.status_code == 403:
                    logger.warning("Got 403 for %s, retrying via Playwright…", url)
                    from ._playwright_thread import download_fb_image_sync
                    path = await anyio.to_thread.run_sync(download_fb_image_sync, url, referer, FB_COOKIE)

                    if not path:
                        logger.warning("Playwright fallback failed, trying generic referer with hardened headers...")
                        request_headers.update({
                            "Referer": "https://m.facebook.com/",
                            "Origin": "https://m.facebook.com",
                            "Sec-Fetch-Dest": "image",
                            "Sec-Fetch-Mode": "no-cors",
                            "Sec-Fetch-Site": "same-site",
                            "sec-ch-ua": '"Chromium";v="124", "Not.A/Brand";v="24"',
                            "sec-ch-ua-mobile": "?0",
                            "sec-ch-ua-platform": '"Windows"',
                        })

                        r_retry = await s.get(url, headers=request_headers)  # RAW url
                        if r_retry.status_code == 200:
                            fd, path = tempfile.mkstemp(suffix=".jpg")
                            os.write(fd, r_retry.content); os.close(fd)
                        else:
                            logger.error("[%s] still %d for %s after all fallbacks; skipping.", slug, r_retry.status_code, url)
                            continue
                else:
                    r.raise_for_status()
                    fd, path = tempfile.mkstemp(suffix=".jpg")
                    os.write(fd, r.content); os.close(fd)

                if not path:
                    logger.error("Could not download image at %s after all fallbacks.", url)
                    continue

                text = ocr_image_to_text(path) or ""

                # Aspect-ratio check for wide banners
                try:
                    w, h = Image.open(path).size
                    if w > 1.6 * h and not looks_like_product(text):
                        logger.info(f"[{slug}] very wide banner ({w}x{h}), not product-like; skipping")
                        continue
                except Exception as img_e:
                    logger.warning(f"[{slug}] could not read image dimensions: {img_e}")

                # If it's a PNG banner AND text doesn't look like a product → skip
                if is_png and not looks_like_product(text):
                    logger.info(f"[{slug}] PNG and not product-like; skipping")
                    continue

                # Filter out app-store/download promos explicitly
                if re.search(r'\b(app store|google play|shkarko aplikacionin)\b', text, re.I):
                    logger.info(f"[{slug}] looks like app-badge/download promo; skipping")
                    continue

                # QUICK reject: greetings or no product signals at all
                if looks_like_greeting(text):
                    logger.info(f"[{slug}] looks like greeting; skipping")
                    continue

                items, (vfrom, vto) = parse_text_for_items(text)

                # If OCR didn’t yield parseable items, still try a soft keep only if it still looks like a product
                if not items and not looks_like_product(text):
                    logger.info(f"[{slug}] no items and not product-like; skipping")
                    continue

                logger.info(f"[{slug}] parsed {len(items)} items from one image")

                for it in items:
                    raw, price = it["raw_name"], it["price_eur"]
                    brand = it.get("brand")
                    category = it.get("category")

                    size_ml_g, unit_hint, _ = parse_size_and_fat(raw)
                    ext_id = _extract_photo_id_from_referer(referer)

                    # find-or-create StoreItem (prefer external_id)
                    item = None
                    if ext_id:
                        item = db.query(StoreItem).filter_by(store_id=store.id, external_id=ext_id).one_or_none()
                    if not item:
                        item = db.query(StoreItem).filter_by(store_id=store.id, raw_name=raw).one_or_none()
                    if not item:
                        item = StoreItem(
                            store_id=store.id,
                            raw_name=raw,
                            external_id=ext_id,
                            url=referer or url,   # permalink preferred
                            brand=brand,
                            category=category,
                            category_norm=classify(raw),
                            fat_pct=parse_fat_pct(raw)
                        )
                        db.add(item); db.commit(); db.refresh(item)
                    else:
                        changed = False
                        # Backfill external_id & permalink
                        if ext_id and not getattr(item, "external_id", None):
                            item.external_id = ext_id; changed = True
                        if referer and item.url != referer:
                            item.url = referer; changed = True
                        if brand and not getattr(item, "brand", None):
                            item.brand = brand; changed = True
                        if category and not getattr(item, "category", None):
                            item.category = category; changed = True
                        if changed:
                            db.commit()

                    up = unit_price_eur(price, size_ml_g, unit_hint)
                    price_obj = Price(
                        store_item_id=item.id,
                        store_id=store.id,  # keep store_id filled
                        price_eur=price,
                        unit_price=up,
                        currency="€",
                        promo_flag=True,
                        promo_valid_from=vfrom,
                        promo_valid_to=vto,
                        collected_at=datetime.utcnow()
                    )
                    db.add(price_obj)
                    processed += 1
                db.commit()

            except Exception as e:
                logger.exception(f"[{slug}] failed processing image {url}: {e}")
            finally:
                if path and os.path.exists(path):
                    os.unlink(path)

    logger.info(f"[{slug}] processed {processed} total items")

def _pick_og_image(soup: BeautifulSoup) -> str | None:
    metas = soup.find_all("meta", attrs={"property": "og:image"})
    cands = [m.get("content") for m in metas if m.get("content")]

    def score(u: str) -> tuple[int, int, int]:
        pr = up.urlparse(u)
        q = up.parse_qs(pr.query)
        stp = q.get("stp", [""])[0]
        no_stp = 1 if not stp else 0
        base = pr.path.rsplit('/', 1)[-1]
        prefer_variant = 1 if re.search(r'(?i)[_-][on]\.(?:jpe?g|png)$', base) else 0
        return (no_stp, prefer_variant, len(u))

    if not cands:
        return None
    cands.sort(key=score)
    return cands[-1]

def _normalize_fbcdn(u: str) -> str:
    """
    Legacy: kept for compatibility in other modules.
    Prefer _key_for_dedupe() for dedupe keys.
    """
    pr = up.urlparse(u)
    q = up.parse_qs(pr.query)
    q.pop("stp", None)
    new_query = up.urlencode({k: v[0] for k, v in q.items()}, doseq=False)
    path = pr.path or ""
    path = re.sub(r'(?i)(?:^|[/_-])(?:s|p)\d+x\d+(?=[/_-]|\.|$)', '', path)
    path = re.sub(r'/{2,}', '/', path)
    path = re.sub(r'[_-]{2,}', r'_', path)
    return pr._replace(path=path, query=new_query).geturl()

def _is_thumbnail(u: str) -> bool:
    """
    Strong thumbnail blocker (runs on RAW URL):
    - Immediately block obvious small markers
    - Detect sWxH / pWxH in stp=..., path segments, or the URL
    """
    if not u:
        return True

    pr = up.urlparse(u)
    q = up.parse_qs(pr.query)
    stp = q.get("stp", [""])[0].lower()
    path = (pr.path or "").lower()
    ul = u.lower()

    # Obvious markers frequently used by FB thumbnails
    small_markers = ("_s100x100", "_s206x206", "/p206x206", "/p480x480", "/s320x320", "/c0.0.512.512")
    if any(m in ul for m in small_markers):
        return True

    # “stp=..._sWxH_...” (common on fbcdn query param)
    if re.search(r'(?<!\d)(?:s|p)\d+x\d+(?!\d)', stp):
        return True

    # Path-based “…/sWxH…” or “…/pWxH…”
    if re.search(r'(?i)(?:^|[/_-])(?:s|p)\d+x\d+(?=[/_-]|\.|$)', path):
        return True

    return False

# IMPORTANT: return RAW URLs (no path normalization) so signatures stay valid
async def _fetch_full_from_photo_page(s, href: str) -> str | None:
    if href.startswith("/"): href = "https://m.facebook.com" + href
    href = href.replace("mbasic.facebook.com", "m.facebook.com")
    r = await s.get(href)
    psoup = BeautifulSoup(r.text, "html.parser")
    cand = None
    for a in psoup.find_all("a", href=True):
        h = a["href"]
        if "view_source" in h or "view_full_size" in h or "view_full" in h or "/download/" in h:
            cand = h; break
    if not cand:
        for a in psoup.find_all("a", href=True):
            txt = (a.get_text() or "").strip()
            aria = (a.get("aria-label") or "").strip()
            if any(h.lower() in txt.lower() for h in FULLSIZE_HINTS) or any(h.lower() in aria.lower() for h in FULLSIZE_HINTS):
                cand = a["href"]; break
    if cand:
        if cand.startswith("/"): cand = "https://m.facebook.com" + cand
        cand = cand.replace("mbasic.facebook.com", "m.facebook.com")
        hdrs = s.headers.copy(); hdrs["Referer"] = href
        r2 = await s.get(cand, headers=hdrs, follow_redirects=False)
        if 300 <= r2.status_code < 400 and r2.headers.get("Location"):
            url = r2.headers["Location"]
            if not _is_thumbnail(url):
                return url      # raw
        if r2.status_code == 200:
            ps2 = BeautifulSoup(r2.text, "html.parser")
            img = ps2.find("img", src=True)
            if img and img["src"] and not _is_thumbnail(img["src"]):
                return img["src"]  # raw
    img = _pick_og_image(psoup)
    if img:
        if _is_thumbnail(img): return None
        return img  # raw
    return None

async def _ts_for_pair(s, referer: str) -> Optional[dt.datetime]:
    if not referer:
        return None
    try:
        return await _extract_post_timestamp(s, referer)
    except Exception:
        return None

async def _get_images_from_mbasic(page_slug: str, max_pages: int = 6,
                                  per_page_limit: int = 24,
                                  want_n: int = DEFAULT_WANT_N) -> list[tuple[str, str]]:
    """
    mbasic crawler that:
    - crawls multiple photo surfaces (photos, photos_by, albums->newest album)
    - fetches RAW full-size URLs from photo pages
    - dedupes by _key_for_dedupe ONLY
    - collects > want_n, stamps timestamps, sorts by ts desc, returns top want_n
    """
    results: list[tuple[str, str]] = []
    seen = set()
    fb_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
        "Accept-Language": "sq-AL,sq;q=0.9,en;q=0.8",
        # help defeat edge caching
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }
    if FB_COOKIE:
        fb_headers["Cookie"] = FB_COOKIE

    surfaces = [
        f"https://mbasic.facebook.com/{page_slug}/photos_by",
        f"https://mbasic.facebook.com/{page_slug}/photos",
    ]

    async with httpx.AsyncClient(headers=fb_headers, timeout=45, follow_redirects=True) as s:
        # 1) photos + photos_by
        for base in surfaces:
            next_url = base
            for i in range(max_pages):
                try:
                    r = await _get_with_dns_retry(s, next_url, params={"nocache": str(int(dt.datetime.utcnow().timestamp()))})
                    low = r.text.lower()
                    if ("log in" in low or "sign up" in low) and "photo.php" not in low:
                        break
                    soup = BeautifulSoup(r.text, "html.parser")
                    photo_links = [a.get("href") for a in soup.select(
                        'a[href*="photo.php"], a[href*="/photos/"], a[href*="/photo/?"]') if a.get("href")]

                    for link in photo_links[:per_page_limit]:
                        try:
                            full = await _fetch_full_from_photo_page(s, link)
                        except Exception as e:
                            logger.exception(f"err on {link}: {e}")
                            continue
                        if not full or _is_thumbnail(full):
                            continue
                        key = _key_for_dedupe(full)
                        if key in seen:
                            continue
                        seen.add(key)
                        referer = ("https://m.facebook.com" + link) if link.startswith("/") else link.replace("mbasic.facebook.com","m.facebook.com")
                        results.append((full, referer))
                        if len(results) >= want_n * 5:  # collect generously; sort later
                            break
                    if len(results) >= want_n * 5:
                        break

                    more = soup.find("a", string=lambda t: t and ("Shiko më shumë" in t or "See more" in t))
                    if not more or not more.get("href"):
                        break
                    next_url = "https://mbasic.facebook.com" + more.get("href")
                except Exception as e:
                    logger.exception(f"Failed during page {i+1} fetch from {next_url}: {e}")
                    break

        # 2) newest album pass (many stores put flyers in a dedicated album)
        try:
            alb_r = await _get_with_dns_retry(s, f"https://mbasic.facebook.com/{page_slug}/photos_albums",
                                                params={"nocache": str(int(dt.datetime.utcnow().timestamp()))})
            alb_soup = BeautifulSoup(alb_r.text, "html.parser")
            # take the first 1–2 albums that look like flyers
            cand_albums = []
            for a in alb_soup.select('a[href*="/albums/"]'):
                href = a.get("href") or ""
                title = (a.get_text() or "").lower()
                if any(k in title for k in ("ofert", "akc", "flyer", "broshur", "zbrit")):
                    cand_albums.append(href)
            # if no obvious match, still try the first album
            if not cand_albums:
                aa = alb_soup.select('a[href*="/albums/"]')
                if aa:
                    cand_albums.append(aa[0].get("href"))

            for ahref in cand_albums[:2]:
                if not ahref:
                    continue
                alb_url = "https://mbasic.facebook.com" + ahref if ahref.startswith("/") else ahref
                try:
                    ar = await s.get(alb_url, params={"nocache": str(int(dt.datetime.utcnow().timestamp()))})
                    asoup = BeautifulSoup(ar.text, "html.parser")
                    photo_links = [a.get("href") for a in asoup.select('a[href*="photo.php"], a[href*="/photos/"], a[href*="/photo/?"]') if a.get("href")]
                    for link in photo_links[:per_page_limit]:
                        try:
                            full = await _fetch_full_from_photo_page(s, link)
                        except Exception:
                            continue
                        if not full or _is_thumbnail(full):
                            continue
                        key = _key_for_dedupe(full)
                        if key in seen:
                            continue
                        seen.add(key)
                        referer = ("https://m.facebook.com" + link) if link.startswith("/") else link.replace("mbasic.facebook.com","m.facebook.com")
                        results.append((full, referer))
                        if len(results) >= want_n * 5:
                            break
                except Exception as e:
                    logger.warning(f"[{page_slug}] album scrape failed: {e}")
        except Exception as e:
            logger.warning(f"[{page_slug}] albums page failed: {e}")

        # 3) Stamp timestamps and sort newest → oldest
        pairs_with_ts: list[tuple[Optional[dt.datetime], tuple[str, str]]] = []
        for u, ref in results:
            ts = await _ts_for_pair(s, ref)
            pairs_with_ts.append((ts, (u, ref)))

        # put None timestamps at the end
        pairs_with_ts.sort(key=lambda x: (x[0] is None, x[0] and -x[0].timestamp()))
        # filter by age if ts present
        trimmed: list[tuple[str, str]] = []
        now = dt.datetime.utcnow()
        for ts, pair in pairs_with_ts:
            if ts:
                age_days = (now - ts).days
                if age_days > MAX_AGE_DAYS:
                    continue
            trimmed.append(pair)
            if len(trimmed) >= want_n:
                break

        return trimmed

async def _get_offer_images_from_facebook_playwright(slug: str, scroll_pages: int = 6,
                                                     want_n: int = DEFAULT_WANT_N):
    from ._playwright_thread import collect_fb_images_sync
    return await anyio.to_thread.run_sync(
        collect_fb_images_sync, slug, scroll_pages, FB_COOKIE, want_n  # <-- pass want_n
    )

# --- REPLACED FUNCTION ---
async def _get_offer_images_from_facebook(page_url: str, scroll_pages: int = 6,
                                          want_n: int = DEFAULT_WANT_N) -> list[tuple[str, str]]:
    logger.info(f"[{page_url}] start _get_offer_images_from_facebook (want_n={want_n}, scroll_pages={scroll_pages})")
    pairs: list[tuple[str, str]] = []
    have = set()
    slug = _extract_page_slug(page_url)

    # 1) try mbasic (fast, already deduped per function)
    try:
        logger.info(f"[{slug}] trying mbasic first (want_n={want_n})")
        mbasic_pairs = await _get_images_from_mbasic(slug, max_pages=3, want_n=want_n)
        for u, ref in mbasic_pairs:
            k = _key_for_dedupe(u)
            if k in have:
                continue
            have.add(k); pairs.append((u, ref))
        logger.info(f"[{slug}] mbasic got {len(pairs)}")
    except Exception as e:
        logger.warning(f"[{slug}] mbasic scrape failed: {e}")

    # 2) top up via Playwright (may come unordered → we'll sort below)
    try:
        need = max(0, want_n * 3 - len(pairs))  # collect generously; sort later
        logger.info(f"[{slug}] topping up via Playwright need={need}")
        if need > 0:
            pw_pairs = await _get_offer_images_from_facebook_playwright(
                slug, scroll_pages=scroll_pages, want_n=need)
            for u, ref in pw_pairs:
                k = _key_for_dedupe(u)
                if k in have:
                    continue
                have.add(k); pairs.append((u, ref))
    except Exception as e:
        logger.warning(f"[{slug}] Playwright scrape failed: {e}")

    if not pairs:
        return []

    # --- NEW from Instruction B ---
    # right before timestamp sorting
    pairs = [(u, r) for (u, r) in pairs
             if isinstance(r, str) and ("/photo.php" in r or "/photos/" in r or "/permalink/" in r)]
    if not pairs:
        logger.info(f"[{slug}] nothing with a usable photo permalink referer after filtering")
        return []
    # --- END NEW ---

    # 3) global timestamp sort (newest → oldest), None timestamps last; then trim
    fb_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
        "Accept-Language": "sq-AL,sq;q=0.9,en;q=0.8",
    }
    if FB_COOKIE:
        fb_headers["Cookie"] = FB_COOKIE

    now = dt.datetime.utcnow()
    async with httpx.AsyncClient(headers=fb_headers, timeout=45, follow_redirects=True) as s:
        pairs_with_ts: list[tuple[Optional[dt.datetime], tuple[str, str]]] = []
        for u, ref in pairs:
            # require a usable photo permalink to get a timestamp; cdn-only gets None
            ts = await _ts_for_pair(s, ref) if (isinstance(ref, str) and ("/photo.php" in ref or "/photos/" in ref)) else None
            pairs_with_ts.append((ts, (u, ref)))

    # newest first; None at the end
    pairs_with_ts.sort(key=lambda x: (x[0] is None, -(x[0].timestamp() if x[0] else 0)))

    # age filter + trim to want_n
    trimmed: list[tuple[str, str]] = []
    for ts, pair in pairs_with_ts:
        if ts:
            age_days = (now - ts).days
            if age_days > MAX_AGE_DAYS:
                continue
        trimmed.append(pair)
        if len(trimmed) >= want_n:
            break

    logger.info(f"[{slug}] returning {len(trimmed)} pairs after global ts-sort (from {len(pairs)} candidates)")
    return trimmed
