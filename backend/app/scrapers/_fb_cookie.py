# backend/app/scrapers/_fb_cookie.py

import os, re
from dotenv import load_dotenv

load_dotenv()

def get_fb_cookie_header() -> str:
    """Gets the raw Facebook cookie string from environment variables."""
    raw = os.getenv("FB_COOKIE", "") or ""
    return raw.strip().strip('"').strip("'")

def _find_cookie_token(key: str, cookie: str) -> str | None:
    """Helper to find a specific key's value in a cookie string."""
    m = re.search(rf"(?:^|;\s*){re.escape(key)}=([^;]+)", cookie)
    return m.group(1) if m else None

def cookie_device_hints(cookie: str) -> dict:
    """
    Extract DPR and WD=WxH from a cookie string to match the device that issued it.
    Fallbacks are sane mobile defaults.
    """
    d = {"width": 412, "height": 915, "dpr": 3.0}  # Defaults
    
    # Parse width and height from the 'wd' token
    wd = _find_cookie_token("wd", cookie)
    if wd and "x" in wd:
        try:
            w, h = wd.split("x", 1)
            d["width"] = int(float(w))
            d["height"] = int(float(h))
        except Exception:
            pass
            
    # Parse device pixel ratio from the 'dpr' token
    v = _find_cookie_token("dpr", cookie)
    if v:
        try:
            d["dpr"] = float(v)
        except Exception:
            pass
            
    return d