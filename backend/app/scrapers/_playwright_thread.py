# backend/app/scrapers/_playwright_thread.py

import sys
import asyncio
from playwright.sync_api import sync_playwright, TimeoutError as PTimeout
from typing import List
import re
import os
import tempfile
from datetime import datetime
from ..utils.normalize import canon_store, parse_fat_pct, classify

def _ensure_proactor():
    if sys.platform == "win32":
        try:
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        except Exception:
            pass

def _apply_fb_cookie(context, cookie_header: str | None):
    if not cookie_header:
        return
    cookies = []
    for part in cookie_header.split(";"):
        if "=" in part:
            k, v = part.strip().split("=", 1)
            cookies.append({"name": k.strip(), "value": v.strip(), "domain": ".facebook.com", "path": "/"})
    if cookies:
        context.add_cookies(cookies)

def download_fb_image_sync(url: str, referer: str, cookie_header: str | None) -> str | None:
    """
    Download an image by requesting the EXACT fbcdn URL (unaltered).
    Uses Playwright's request context with hardened headers, then falls back to DOM injection/screenshot.
    """
    _ensure_proactor()

    url_no_qs = url.split("?", 1)[0]

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--lang=sq-AL"])
        context = browser.new_context(
            locale="sq-AL",
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0.0.0 Safari/537.36"),
            accept_downloads=False,
            bypass_csp=True,
            extra_http_headers={
                "Accept-Language": "sq-AL,sq;q=0.9,en;q=0.8",
            },
        )
        _apply_fb_cookie(context, cookie_header)
        page = context.new_page()

        # Normalize referer to m.facebook.com (referer ONLY)
        if "mbasic.facebook.com" in referer:
            referer = referer.replace("mbasic.facebook.com", "m.facebook.com")
        if "www.facebook.com" in referer:
            referer = referer.replace("www.facebook.com", "m.facebook.com")

        try:
            # (A) FIRST: try Playwright's request API with hard headers
            r = context.request.get(
                url,  # IMPORTANT: unaltered fbcdn URL
                headers={
                    "Referer": referer,
                    "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
                    "Origin": "https://m.facebook.com",
                    "Sec-Fetch-Dest": "image",
                    "Sec-Fetch-Mode": "no-cors",
                    "Sec-Fetch-Site": "same-site",
                    'sec-ch-ua': '"Chromium";v="124", "Not.A/Brand";v="24"',
                    'sec-ch-ua-mobile': '?0',
                    'sec-ch-ua-platform': '"Windows"',
                },
            )
            if r.ok:
                fd, path = tempfile.mkstemp(suffix=".jpg")
                os.write(fd, r.body()); os.close(fd)
                return path

            # (B) If that fails, visit referer and inject <img> (CSP-safe)
            page.goto(referer, wait_until="domcontentloaded", timeout=45000)

            captured = {"body": None}
            def _on_response(resp):
                try:
                    want = url_no_qs.rsplit("/", 1)[-1]
                    got = resp.url.split("?", 1)[0].rsplit("/", 1)[-1]
                    if resp.ok and (resp.url.split("?",1)[0] == url_no_qs or got == want):
                        captured["body"] = resp.body()
                except Exception:
                    pass
            page.on("response", _on_response)

            page.evaluate("""
                (u) => {
                    const img = document.createElement('img');
                    img.id = 'kpc_dl_img';
                    img.src = u;
                    img.style.maxWidth = 'none';
                    img.style.maxHeight = 'none';
                    document.body.appendChild(img);
                }
            """, url)

            img = page.locator("#kpc_dl_img")
            try:
                img.wait_for(state="visible", timeout=20000)
                # CSP-safe polling
                for _ in range(80):
                    try:
                        ready = img.evaluate("i => !!i && i.complete && i.naturalWidth>0 && i.naturalHeight>0")
                    except Exception:
                        ready = False
                    if ready:
                        break
                    page.wait_for_timeout(250)
                else:
                    return None
            except PTimeout:
                return None

            if captured["body"]:
                fd, path = tempfile.mkstemp(suffix=".jpg")
                os.write(fd, captured["body"]); os.close(fd)
                return path

            natural = page.evaluate("""
                () => {
                    const i = document.getElementById('kpc_dl_img');
                    return { w: i?.naturalWidth || 0, h: i?.naturalHeight || 0 };
                }
            """)
            if natural["w"] <= 0 or natural["h"] <= 0:
                return None

            page.set_viewport_size({
                "width": min(max(natural["w"], 10), 4096),
                "height": min(max(natural["h"], 10), 4096),
            })
            path = tempfile.mkstemp(suffix=".jpg")[1]
            img.screenshot(path=path)
            return path
        finally:
            browser.close()
    
    # --- FINAL FALLBACK: open the referer page and screenshot the largest img it renders ---
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=["--lang=sq-AL"])
            context = browser.new_context(locale="sq-AL", user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"))
            _apply_fb_cookie(context, cookie_header)
            page = context.new_page()
            page.goto(referer, wait_until="domcontentloaded", timeout=45000)
            try:
                page.wait_for_load_state("networkidle", timeout=8000)
            except PTimeout:
                pass

            info = page.evaluate("""
                () => {
                    const imgs = Array.from(document.images || []);
                    const score = i => {
                        const w = i.naturalWidth || 0, h = i.naturalHeight || 0;
                        const ok = w>150 && h>150;
                        const src = (i.currentSrc || i.src || "").toLowerCase();
                        const cdn = src.includes("fbcdn");
                        return ok ? [cdn ? 1 : 0, w*h] : [-1, 0];
                    };
                    let best = null, bestScore = [-1,0];
                    for (const i of imgs) {
                        const s = score(i);
                        if (s[0] > bestScore[0] || (s[0] === bestScore[0] && s[1] > bestScore[1])) {
                            best = i; bestScore = s;
                        }
                    }
                    return best ? { id: (best.id || (best.id = "kpc_best_img")), w: best.naturalWidth, h: best.naturalHeight } : null;
                }
            """)

            if info and info["w"] > 0 and info["h"] > 0:
                img2 = page.locator(f"#{info['id']}")
                try:
                    img2.wait_for(state="visible", timeout=8000)
                except PTimeout:
                    pass

                page.set_viewport_size({
                    "width": min(max(int(info["w"]), 10), 4096),
                    "height": min(max(int(info["h"]), 10), 4096),
                })
                path = tempfile.mkstemp(suffix=".jpg")[1]
                img2.screenshot(path=path)
                return path
    except Exception:
        pass
    finally:
        if 'browser' in locals() and browser.is_connected():
            browser.close()

    return None

# ---------- Resolve a full-size URL from a single photo href (returns RAW URL) ----------
def _resolve_full_from_href(page, href: str) -> str | None:
    """
    Open the photo page and return a best-guess full-size fbcdn URL.
    IMPORTANT: returns the EXACT discovered URL (not normalized).
    """
    from .facebook_flyer import _is_thumbnail  # only for checking

    referer = href if href.startswith("http") else "https://m.facebook.com" + href
    referer = (referer
                .replace("www.facebook.com", "m.facebook.com")
                .replace("mbasic.facebook.com", "m.facebook.com"))

    page.goto(referer, wait_until="domcontentloaded", timeout=45000)
    try:
        page.wait_for_load_state("networkidle", timeout=8000)
    except PTimeout:
        pass

    # 1) Prefer explicit "view full size" style links
    for sel in ['a[href*="view_full_size"]',
                'a[href*="view_source"]',
                'a[href*="/download/"]']:
        loc = page.locator(sel)
        if loc.count():
            # follow and capture the final URL (redirect Location or request URL)
            with page.expect_response(lambda r: "fbcdn.net" in r.url and r.status in (200, 302, 301), timeout=8000) as rinfo:
                try:
                    loc.first.click(timeout=2000)
                except Exception:
                    continue
            resp = rinfo.value
            url = resp.headers.get("location") or resp.url
            if url and not _is_thumbnail(url):
                return url  # RAW

    # 2) Fallback: pick the largest fbcdn <img> rendered on the page (return RAW src)
    data = page.evaluate("""
        () => {
            const imgs = Array.from(document.images || []);
            let bestSrc = null, bestArea = 0;
            for (const i of imgs) {
                const src = (i.currentSrc || i.src || "");
                if (!src.toLowerCase().includes("fbcdn")) continue;
                const w = i.naturalWidth || 0, h = i.naturalHeight || 0;
                const area = w*h;
                if (area > bestArea) { bestSrc = src; bestArea = area; }
            }
            return bestSrc;
        }
    """)
    if data:
        if not _is_thumbnail(data):
            return data  # RAW

    return None

def _ts_from_photo_page_quick(page, href: str) -> int | None:
    """
    Open a single photo permalink quickly and try to extract a UNIX epoch (UTC seconds).
    Covers multiple DOM patterns on m.facebook.com.
    """
    url = href if href.startswith("http") else "https://m.facebook.com" + href
    url = url.replace("www.facebook.com","m.facebook.com").replace("mbasic.facebook.com","m.facebook.com")

    try:
        page.goto(url, wait_until="domcontentloaded", timeout=20000)
        try:
            page.wait_for_load_state("networkidle", timeout=6000)
        except PTimeout:
            pass
    except PTimeout:
        return None

    # Try several patterns; return first good 10-digit epoch
    js = page.evaluate("""
      () => {
        const pickInt = (v) => {
          if (!v) return null;
          const n = parseInt(v, 10);
          return (Number.isFinite(n) && (''+n).length === 10) ? n : null;
        };

        // 1) Simple attributes commonly present on m-site
        for (const sel of ['abbr[data-utime]', 'time[data-utime]']) {
          const el = document.querySelector(sel);
          const v = el && (el.getAttribute('data-utime') || el.dataset.utime);
          const n = pickInt(v);
          if (n) return n;
        }

        // 2) time[datetime] with seconds
        const t = document.querySelector('time[datetime]');
        if (t) {
          try {
            const d = Date.parse(t.getAttribute('datetime'));
            if (Number.isFinite(d)) return Math.floor(d/1000);
          } catch {}
        }

        // 3) JSON blobs FB sprinkles in the DOM
        const html = document.documentElement.innerHTML;
        const m = html.match(/(?:"publish_time"|"creation_time"|"utime")\\s*:\\s*(\\d{10})/);
        if (m) {
          const n = pickInt(m[1]);
          if (n) return n;
        }

        // 4) aria-label/date strings sometimes carry ISO date
        //    (cheap try; ignore localized strings)
        const timeNode = document.querySelector('a[aria-label] time, time[aria-label]');
        if (timeNode && timeNode.getAttribute('aria-label')) {
          try {
            const d = Date.parse(timeNode.getAttribute('aria-label'));
            if (Number.isFinite(d)) return Math.floor(d/1000);
          } catch {}
        }

        return null;
      }
    """)
    return js if isinstance(js, int) else None

# --- NEW HELPERS ---
def _accept_cookies_fast(page):
    # broaden the net: text, common css hooks, and “only essential” variants
    labels = [
        "Lejo të gjitha", "Lejo të gjitha cookies", "Prano të gjitha", "Accept all",
        "Allow all", "Only allow essential", "Vetëm të domosdoshmet", "Only essential"
    ]
    for label in labels:
        try:
            page.get_by_role("button", name=re.compile(label, re.I)).click(timeout=1200)
            page.wait_for_timeout(250)
            return
        except Exception:
            pass
    # CSS fallbacks FB uses in some locales/layouts
    for sel in [
        'div[role="dialog"] button',       # cookie banner dialog buttons
        '[data-cookiebanner] button',      # explicit cookie banner
        'button[aria-label*="cookies" i]', # generic cookie button
    ]:
        try:
            if page.locator(sel).count():
                page.locator(sel).first.click(timeout=1200)
                page.wait_for_timeout(250)
                return
        except Exception:
            pass

def _is_login_wall(page):
    u = (page.url or "").lower()
    if "login" in u or "checkpoint" in u:
        return True
    # crude but effective extra checks
    try:
        if page.locator('form[action*="login"]').count() > 0:
            return True
    except Exception:
        pass
    return False

def _has_grid_content(page):
    try:
        cnt = page.evaluate("""
            () => document.querySelectorAll(
              'img[src*="fbcdn"], a[href*="/photo"], a[href*="/photos/"]'
            ).length
        """)
        return int(cnt or 0) > 0
    except Exception:
        return False

def _prime_and_scroll(page, scroll_pages):
    # robust scroll that works whether window or inner scroller is active
    last_h = 0
    for _ in range(scroll_pages):
        try:
            page.evaluate("window.scrollBy(0, Math.max(1000, window.innerHeight))")
        except Exception:
            pass
        try:
            page.mouse.wheel(0, 2000)
        except Exception:
            pass
        page.wait_for_timeout(600)
        try:
            h = page.evaluate("document.scrollingElement.scrollHeight")
        except Exception:
            h = 0
        if h == last_h:
            # try one more “End” to nudge lazy loads
            try:
                page.keyboard.press("End")
            except Exception:
                pass
            page.wait_for_timeout(400)
            try:
                h2 = page.evaluate("document.scrollingElement.scrollHeight")
            except Exception:
                h2 = 0
            if h2 == last_h:
                break
        last_h = h

def collect_fb_images_sync(slug: str, scroll_pages: int = 6,
                           cookie_header: str | None = None,
                           want_n: int = 5):
    _ensure_proactor()
    from .facebook_flyer import _key_for_dedupe, _is_thumbnail

    pairs: list[tuple[str, str]] = []
    seen = set()
    with sync_playwright() as p:
        # --- MODIFIED from Instruction C ---
        browser = p.chromium.launch(
            headless=True,
            args=["--lang=sq-AL", "--headless=new", "--disable-gpu", "--no-sandbox"]
        )
        # --- END MODIFIED ---
        context = browser.new_context(locale="sq-AL")
        _apply_fb_cookie(context, cookie_header)
        page = context.new_page()
        ts_page = context.new_page()
        import time
        MAX_AGE_DAYS = int(os.getenv("FB_MAX_AGE_DAYS", "10"))
        now_epoch = int(time.time())
        cutoff_epoch = now_epoch - MAX_AGE_DAYS * 86400
        
        try:
            mobile_candidates = [
                f"https://m.facebook.com/{slug}/photos",        # try this first
                f"https://m.facebook.com/{slug}/photos_by",
                f"https://m.facebook.com/{slug}/photos_stream",
            ]
            
            page_loaded = False
            for url_try in mobile_candidates:
                try:
                    page.goto(url_try, wait_until="domcontentloaded", timeout=45000)
                except PTimeout:
                    continue

                _accept_cookies_fast(page)
                if _is_login_wall(page):
                    continue

                _prime_and_scroll(page, max(2, min(4, scroll_pages)))
                if not _has_grid_content(page):
                    _accept_cookies_fast(page)
                    _prime_and_scroll(page, 2)

                if _has_grid_content(page):
                    page_loaded = True
                    print(f"[fb/pw:{slug}] using source: {page.url}")
                    # --- NEW from Instruction A ---
                    # --- force m-dot layout if we accidentally landed on www ---
                    if "://www.facebook.com/" in page.url:
                        murl = page.url.replace("://www.facebook.com/", "://m.facebook.com/")
                        try:
                            page.goto(murl, wait_until="domcontentloaded", timeout=45000)
                            _accept_cookies_fast(page)
                            _prime_and_scroll(page, 2)
                        except Exception:
                            pass
                    # --- END NEW ---
                    break
            
            if not page_loaded:
                print(f"[fb/pw:{slug}] returning 0 pairs (no grid content on any candidate)")
                return pairs

            _prime_and_scroll(page, scroll_pages)
            
            pairs_js = page.evaluate("""
                () => {
                    const out = [];
                    const imgs = Array.from(document.images || []);
                    const isFbCdn = (u) => (u || '').toLowerCase().includes('fbcdn');
                    for (const img of imgs) {
                        const src = img.currentSrc || img.getAttribute('src') || '';
                        if (!isFbCdn(src)) continue;

                        let a = img.closest && img.closest('a[href]');
                        let href = a ? (a.getAttribute('href') || '') : '';
                        if (!href && img.parentElement && img.parentElement.closest) {
                            const pa = img.parentElement.closest('a[href]');
                            if (pa) href = pa.getAttribute('href') || '';
                        }

                        const r = img.getBoundingClientRect();
                        out.push({
                            src,
                            href,
                            w: img.naturalWidth || 0,
                            h: img.naturalHeight || 0,
                            y: r.top || 0
                        });
                    }
                    out.sort((a,b) => a.y - b.y);
                    return out;
                }
            """)

            from urllib.parse import urlparse
            
            for rec in pairs_js:
                href = (rec.get("href") or "").strip()
                
                # --- NEW from Instruction A: require a photo/permalink href ---
                if not href or ("/photo" not in href and "/photos/" not in href and "/permalink/" not in href):
                    continue  # don't produce cdn-only pairs without a proper referer
                # --- END NEW ---

                src  = (rec.get("src")  or "").strip()
                w    = int(rec.get("w") or 0)
                h    = int(rec.get("h") or 0)
                if not src or _is_thumbnail(src):
                    continue

                pr = urlparse(src)
                host = (pr.netloc or "").lower()
                path = (pr.path or "").lower()

                if not host.startswith("scontent.") or "fbcdn.net" not in host or "/rsrc.php" in path:
                    continue
                if not (path.endswith((".jpg", ".jpeg", ".png"))):
                    continue
                if w * h < 300_000 or (w < 750 and h < 750):
                    continue

                # --- MODIFIED from Instruction A ---
                referer = href if href.startswith("http") else "https://m.facebook.com" + href
                referer = referer.replace("www.facebook.com", "m.facebook.com")
                # --- END MODIFIED ---

                k = _key_for_dedupe(src)
                if k in seen:
                    continue
                seen.add(k)
                pairs.append((src, referer))

            if len(pairs) < want_n:
                # --- MODIFIED from Instruction A ---
                hrefs = page.evaluate("""
                    () => Array.from(
                            document.querySelectorAll(
                                'a[href*="/photo"], a[href*="/photos/"], a[href*="/permalink/"], ' +
                                'a[href^="/photo/"], a[href*="photo/?fbid="], a[href*="multi_permalinks"]'
                            )
                        )
                        .map(a => ({href: a.getAttribute('href') || '', y: a.getBoundingClientRect().top}))
                        .filter(x => x.href)
                        .sort((a,b) => a.y - b.y)
                        .map(x => x.href)
                        .slice(0, 80)
                """)
                # --- END MODIFIED ---
                fresh_pairs = []
                unknown_pairs = []
                for href in hrefs:
                    if len(fresh_pairs) >= want_n:
                        break
                    try:
                        full = _resolve_full_from_href(page, href)
                    except Exception:
                        full = None
                    if not full or _is_thumbnail(full):
                        continue
                    
                    pr = urlparse(full)
                    if not (pr.netloc or "").lower().startswith("scontent."): continue
                    if not (pr.path or "").lower().endswith((".jpg", ".jpeg", ".png")): continue

                    k = _key_for_dedupe(full)
                    if k in seen: 
                        continue

                    ts = _ts_from_photo_page_quick(ts_page, href)
                    if ts is not None and ts < cutoff_epoch:
                        continue

                    pair = (full, href if href.startswith("http") else "https://m.facebook.com" + href)
                    seen.add(k)

                    if ts is None:
                        unknown_pairs.append((ts, pair))
                    else:
                        fresh_pairs.append((ts, pair))
                
                fresh_pairs.sort(key=lambda x: -x[0])
                ordered = [p for _ts, p in fresh_pairs]
                if len(ordered) < want_n:
                    ordered.extend([p for _ts, p in unknown_pairs])

                pairs.extend(ordered[:max(0, want_n - len(pairs))])
            
            # --- NEW from Instruction E ---
            valid = sum(1 for _, ref in pairs if ("/photo.php" in ref or "/photos/" in ref or "/permalink/" in ref))
            print(f"[fb/pw:{slug}] collected {len(pairs)} total, {valid} with photo permalinks")
            # --- END NEW ---

            pairs_with_ts = []
            for (src, ref) in pairs:
                if "/photo.php" in ref or "/photos/" in ref:
                    try:
                        ts = _ts_from_photo_page_quick(ts_page, ref)
                    except Exception:
                        ts = None
                else:
                    ts = None
                pairs_with_ts.append((ts, (src, ref)))

            fresh = []
            unknown = []
            for ts, pair in pairs_with_ts:
                if ts is None:
                    unknown.append((ts, pair))
                elif ts >= cutoff_epoch:
                    fresh.append((ts, pair))

            fresh.sort(key=lambda x: -x[0])
            ordered_pairs = [p for _ts, p in fresh] + [p for _ts, p in unknown]
            
            pairs = ordered_pairs[:want_n]
            
            def _dbg(ts):
                import datetime as dt
                return dt.datetime.utcfromtimestamp(ts).isoformat() + "Z"

            debug_lines = []
            fresh_pairs_for_log = [item for item in pairs_with_ts if item[0] is not None and item[0] >= cutoff_epoch]
            fresh_pairs_for_log.sort(key=lambda x: -x[0])
            unknown_pairs_for_log = [item for item in pairs_with_ts if item[0] is None]

            for ts, pair in fresh_pairs_for_log[:want_n]:
                debug_lines.append(f"KEEP fresh ts={ts} ({_dbg(ts)}) ref={pair[1]}")
            for _ts, pair in unknown_pairs_for_log[:max(0, want_n - len(fresh_pairs_for_log))]:
                debug_lines.append(f"KEEP unknown ref={pair[1]}")
            print("\n".join(debug_lines))
            print(f"[fb/pw:{slug}] returning {len(pairs)} pairs after ts-filter (cutoff={cutoff_epoch})")

        finally:
            try:
                ts_page.close()
            except Exception:
                pass
            browser.close()
    return pairs

def _dedupe_sync(seq: List[str]) -> List[str]:
    seen = set(); out=[]
    for x in seq:
        if x not in seen:
            out.append(x); seen.add(x)
    return out

def _harvest_page_for_pdfs_sync(page, base_url: str) -> List[str]:
    hrefs = page.eval_on_selector_all("a[href]", "els => els.map(e => e.getAttribute('href'))")
    pdfs = [h for h in hrefs if h and '.pdf' in h.lower()]
    return _dedupe_sync(pdfs)

def collect_etc_pdfs_sync(listing_url: str) -> List[str]:
    _ensure_proactor()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")
        page = ctx.new_page()
        page.goto(listing_url, wait_until="domcontentloaded", timeout=30000)
        try:
            page.wait_for_load_state("networkidle", timeout=5000)
        except PTimeout:
            pass
        pdfs = _harvest_page_for_pdfs_sync(page, listing_url)
        browser.close()
        return pdfs

# ---------------------- Viva Fresh: hardened crawler ----------------------

def _vf_accept_and_pick_city(page):
    # Cookie banners (various wordings)
    for txt in ["Pranoj", "Lejo", "Dakordohem", "Accept", "I agree", "OK", "Continue"]:
        try:
            el = page.get_by_role("button", name=re.compile(txt, re.I))
            if el.count():
                el.first.click(timeout=1200)
                page.wait_for_timeout(250)
                break
        except Exception:
            pass
    # City picker (chips/buttons)
    for txt in ["Prishtinë", "Prishtina", "Qendër", "Pristina"]:
        try:
            el = page.get_by_text(txt, exact=False)
            if el.count():
                el.first.click(timeout=1500)
                page.wait_for_timeout(350)
                break
        except Exception:
            pass

def _vf_scroll_all(page, max_steps=80):
    last_h = 0
    for _ in range(max_steps):
        try:
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        except Exception:
            pass
        page.wait_for_timeout(250)
        try:
            h = page.evaluate("document.body.scrollHeight")
        except Exception:
            h = 0
        if h == last_h:
            break
        last_h = h

def _vf_parse_price(txt: str) -> float | None:
    # Albanian formatting "1,29 €" -> 1.29; also "1.29€"
    if not txt:
        return None
    t = (txt or "").replace("€", "").replace("\xa0", " ").strip()
    t = t.replace(",", ".")
    m = re.search(r"(\d+(?:\.\d{1,2})?)", t)
    try:
        return float(m.group(1)) if m else None
    except Exception:
        return None

def _vf_discover_subcats(page, base: str) -> list[int]:
    """
    If their lvl2 IDs change, discover dairy-ish subcats by name.
    Falls back to your old ID list when nothing is found.
    """
    DAIRY_HINTS = ["qumësht", "djath", "kosi", "bulmet", "vaj krem", "mish i përpunuar"]
    try:
        page.goto(base + "categories/", wait_until="load", timeout=45000)
        _vf_accept_and_pick_city(page)
        # Click "Bulmet" / Dairy category first if present
        for hint in DAIRY_HINTS:
            try:
                node = page.get_by_text(re.compile(hint, re.I), exact=False)
                if node.count():
                    node.first.click(timeout=1500)
                    page.wait_for_timeout(300)
                    break
            except Exception:
                pass
        # Pull lvl2 numbers from links like ?lvl2=13
        links = page.eval_on_selector_all("a[href*='lvl2=']", "els => els.map(e => e.getAttribute('href'))")
        ids = []
        for h in links or []:
            m = re.search(r"lvl2=(\d+)", h or "")
            if m:
                try:
                    ids.append(int(m.group(1)))
                except Exception:
                    pass
        ids = sorted(set(ids))[:20]
        return ids
    except Exception:
        return []

def crawl_vivafresh_sync(db, city: str = "Prishtina") -> int:
    """
    Scrapes Viva Fresh categories and stores items/prices.
    Environment overrides:
      - VIVAFRESH_BASE (default https://online.vivafresh.shop/)
      - VIVAFRESH_LVL2_IDS (comma sep, e.g. 13,14,15)
    """
    _ensure_proactor()
    from ..models import Store, StoreItem, Price
    from ..utils.normalize import parse_size_and_fat, unit_price_eur

    BASE = os.getenv("VIVAFRESH_BASE", "https://online.vivafresh.shop/")
    default_ids = [13, 14, 15, 16, 17, 18, 19]
    env_ids = os.getenv("VIVAFRESH_LVL2_IDS")
    if env_ids:
        try:
            DAIRY_SUBCATEGORIES = [int(x) for x in re.findall(r"\d+", env_ids)]
        except Exception:
            DAIRY_SUBCATEGORIES = default_ids
    else:
        DAIRY_SUBCATEGORIES = default_ids

    store = db.query(Store).filter_by(slug="vivafresh").one_or_none()
    if not store:
        store = Store(name="Viva Fresh", slug="vivafresh", city=city)
        db.add(store); db.commit(); db.refresh(store)

    processed = 0

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            locale="sq-AL",
            user_agent=("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/125.0 Safari/537.36 kpc/1.1"),
            bypass_csp=True,
            extra_http_headers={
                "Accept-Language": "sq-AL,sq;q=0.9,en;q=0.8",
                "sec-ch-ua": '"Chromium";v="125", "Not.A/Brand";v="24"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"Linux"',
            },
        )
        page = context.new_page()

        page.goto(BASE, wait_until="load", timeout=60000)
        _vf_accept_and_pick_city(page)

        # Try each lvl2 page
        for lvl2 in DAIRY_SUBCATEGORIES:
            url = f"{BASE}categories/?lvl2={lvl2}"
            try:
                page.goto(url, wait_until="load", timeout=60000)
                try:
                    page.wait_for_load_state("networkidle", timeout=15000)
                except PTimeout:
                    pass
                _vf_accept_and_pick_city(page)
                # don’t hard fail if selectors don’t appear—just continue
                try:
                    page.wait_for_selector(".product-card, .product-box, .product-item", timeout=12000)
                except PTimeout:
                    pass
            except PTimeout:
                continue

            _vf_scroll_all(page, max_steps=80)
            cards = page.query_selector_all(".product-card, .product-box, .product-item")
            
            for c in cards:
                # Name
                name = None
                for sel in [".product-title", ".title", ".name", "h3", "a[title]"]:
                    el = c.query_selector(sel)
                    if el and (txt := (el.inner_text() or "").strip()):
                        name = txt
                        break
                if not name:
                    continue

                # Price
                price_eur = None
                for sel in [".current-price", ".new-price", ".price", ".product-price", "[class*='price']"]:
                    el = c.query_selector(sel)
                    if el and (txt := (el.inner_text() or "").strip()):
                        val = _vf_parse_price(txt)
                        if val is not None:
                            price_eur = val
                            break
                if price_eur is None:
                    continue

                # URL (optional)
                urlp = None
                if a := c.query_selector("a[href]"):
                    href = a.get_attribute("href") or ""
                    urlp = href if href.startswith("http") else BASE.rstrip("/") + href

                # Normalize & store
                size_ml_g, unit_hint, _fat = parse_size_and_fat(name)
                uprice = unit_price_eur(price_eur, size_ml_g, unit_hint)

                item = db.query(StoreItem).filter_by(store_id=store.id, url=urlp).one_or_none()
                if not item:
                    ext_id = (urlp or name)[:64]
                    item = StoreItem(store_id=store.id, external_id=ext_id, raw_name=name, url=urlp, category_norm = classify(name),fat_pct = parse_fat_pct(name))
                    db.add(item); db.flush()

                db.add(Price(
                    store_item_id=item.id,
                    store_id=store.id,  # <-- ✅ This line was added
                    price_eur=price_eur,
                    unit_price=uprice,
                    collected_at=datetime.utcnow()
                ))
                processed += 1

        # If nothing processed (IDs outdated), auto-discover and try once
        if processed == 0:
            discovered = _vf_discover_subcats(page, BASE)
            if not discovered:
                discovered = default_ids  # fallback again just in case
            for lvl2 in discovered:
                try:
                    page.goto(f"{BASE}categories/?lvl2={lvl2}", wait_until="load", timeout=60000)
                except PTimeout:
                    continue
                _vf_accept_and_pick_city(page)
                try:
                    page.wait_for_load_state("networkidle", timeout=8000)
                except PTimeout:
                    pass
                _vf_scroll_all(page, max_steps=80)
                cards = page.query_selector_all(".product-card, .product-box, .product-item")
                for c in cards:
                    name = None
                    for sel in [".product-title", ".title", ".name", "h3", "a[title]"]:
                        el = c.query_selector(sel)
                        if el and (txt := (el.inner_text() or "").strip()):
                            name = txt; break
                    if not name: 
                        continue
                    price_eur = None
                    for sel in [".current-price", ".new-price", ".price", ".product-price", "[class*='price']"]:
                        el = c.query_selector(sel)
                        if el and (pt := (el.inner_text() or "").strip()):
                            val = _vf_parse_price(pt)
                            if val is not None: 
                                price_eur = val; break
                    if price_eur is None: 
                        continue
                    urlp = None
                    if a := c.query_selector("a[href]"):
                        href = a.get_attribute("href") or ""
                        urlp = href if href.startswith("http") else BASE.rstrip("/") + href
                    size_ml_g, unit_hint, _fat = parse_size_and_fat(name)
                    uprice = unit_price_eur(price_eur, size_ml_g, unit_hint)
                    item = db.query(StoreItem).filter_by(store_id=store.id, url=urlp).one_or_none()
                    if not item:
                        item = StoreItem(store_id=store.id, external_id=(urlp or name)[:64], raw_name=name, url=urlp, category_norm = classify(name), fat_pct = parse_fat_pct(name))
                        db.add(item); db.flush()
                    db.add(Price(
                        store_item_id=item.id,
                        store_id=store.id,  # <-- ✅ This line was added
                        price_eur=price_eur,
                        unit_price=uprice,
                        collected_at=datetime.utcnow()
                    ))
                    processed += 1

        db.commit()
        browser.close()

    print(f"[vivafresh] processed {processed} items")
    return processed