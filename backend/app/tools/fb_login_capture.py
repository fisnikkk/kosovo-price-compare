# backend/app/tools/fb_login_capture.py
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PTimeout

# Write the state to backend/fb_storage_state.json (two levels up: tools -> app -> backend)
STATE_PATH = Path(__file__).resolve().parent.parent.parent / "fb_storage_state.json"
def _safe_goto(page, url: str) -> bool:
    """Navigate with resilient settings and a small retry."""
    for attempt in range(2):
        try:
            # Earlier readiness signal + longer timeout helps on flaky networks
            page.goto(url, wait_until="commit", timeout=60000)
            try:
                page.wait_for_load_state("domcontentloaded", timeout=15000)
            except PTimeout:
                pass
            return True
        except Exception as e:
            print(f"[fb_login_capture] goto failed ({attempt+1}) for {url}: {e}")
            try:
                page.wait_for_timeout(1500)
            except Exception:
                pass
    return False

with sync_playwright() as p:
    # Headful & tolerant to cert issues; language helps with cookie banners
    b = p.chromium.launch(
        headless=False,
        args=[
            "--lang=en-US",
            "--ignore-certificate-errors",  # tolerate odd cert chains
            "--disable-gpu",
            "--no-sandbox",
        ],
    )

    ctx = b.new_context(
        ignore_https_errors=True,   # also tolerate cert hiccups at context level
        user_agent=(
            "Mozilla/5.0 (Linux; Android 13; SM-G981B) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/141.0.0.0 Mobile Safari/537.36"
        ),
        viewport={"width": 412, "height": 916},
        device_scale_factor=3.5,
        is_mobile=True,
        has_touch=True,
        extra_http_headers={
            "sec-ch-ua": '"Chromium";v="141", "Not.A/Brand";v="99"',
            "sec-ch-ua-mobile": "?1",
            "sec-ch-ua-platform": '"Android"',
            "sec-ch-ua-model": '"SM-G981B"',
            "Accept-Language": "en-US,en;q=0.9",
        },
    )

    page = ctx.new_page()
    page.set_default_navigation_timeout(120000)  # be generous for the first loads

    # Try home first (FB often redirects to login if not authed)
    ok = _safe_goto(page, "https://m.facebook.com/?locale=en_US")
    if not ok:
        # Fallback to explicit login and then back to m. (mbasic often loads even on flakier networks)
        ok = _safe_goto(page, "https://mbasic.facebook.com/login")
        if ok:
            _safe_goto(page, "https://m.facebook.com/?locale=en_US")
        else:
            # As a final attempt, try m.facebook login URL
            _safe_goto(page, "https://m.facebook.com/login")

    print("\nLog in in the window, then press ENTER here...")
    try:
        input()
    except EOFError:
        pass

    ctx.storage_state(path=str(STATE_PATH))
    print(f"Saved storage_state to: {STATE_PATH}")
    b.close()
