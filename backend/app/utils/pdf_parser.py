from __future__ import annotations
import os, re
from dotenv import load_dotenv
from typing import List, Dict, Tuple, Optional
from datetime import datetime
from .image_ocr import ocr_image_to_text
from .taxonomy import detect_brand, detect_category  # <-- NEW

load_dotenv()

# match €1,89 / 1.89€ / 1 89 € / 9€ / 9 eur / euro 1 29, etc.
PRICE_RE = re.compile(
    r"(?:(?:€|eur|euro)\s*)?"                # optional currency before
    r"(\d{1,3}(?:[.,\s]\d{2})?|\d{1,3})"     # 1.89 / 1 89 / 9
    r"\s*(?:€|eur|euro)?",                   # optional currency after
    re.I
)
DATE_RE  = re.compile(r"(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})")

def _parse_date(s: str) -> Optional[datetime]:
    """Parses a date string with various common formats."""
    for fmt in ("%d.%m.%Y", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%y", "%d/%m/%y", "%d-%m-%y"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            pass
    return None

def _dedupe(items: List[Dict]) -> List[Dict]:
    """Removes duplicate items based on name and price."""
    seen = {}
    for it in items:
        key = (it["raw_name"], round(it["price_eur"], 2))
        seen[key] = it
    return list(seen.values())

def parse_text_for_items(text: str) -> Tuple[List[Dict], Tuple[Optional[datetime], Optional[datetime]]]:
    """Parses raw text to extract product items and validity dates (now with brand+category)."""
    items: List[Dict] = []
    vfrom = vto = None

    dates = DATE_RE.findall(text)
    if len(dates) >= 2:
        d1 = _parse_date(dates[0]); d2 = _parse_date(dates[1])
        if d1 and d2:
            vfrom, vto = (min(d1, d2), max(d1, d2))

    for line in text.splitlines():
        line_c = " ".join(line.split())
        if not line_c:
            continue

        m = PRICE_RE.search(line_c)
        if not m:
            continue

        try:
            # turn "1 29" or "1,29" into "1.29"
            price_str = re.sub(r"[,\s]", ".", m.group(1)).strip(".")
            price = float(price_str)
        except Exception:
            continue

        # remove the matched price (with currency) from the name
        name = PRICE_RE.sub("", line_c).strip(" :-•–—")
        if len(name) < 3:
            continue

        items.append({
            "raw_name": name,
            "price_eur": price,
            "brand": detect_brand(name),        # <-- NEW
            "category": detect_category(name),  # <-- NEW
        })

    return _dedupe(items), (vfrom, vto)

def parse_generic_flyer(pdf_path: str) -> Tuple[List[Dict], Tuple[Optional[datetime], Optional[datetime]]]:
    """
    Parses a PDF flyer by converting it to images and running OCR.
    Validates Poppler path at runtime.
    """
    POPPLER_PATH = (os.getenv("POPPLER_PATH") or "").strip().strip('"')
    if not POPPLER_PATH or not os.path.exists(os.path.join(POPPLER_PATH, "pdfinfo.exe")):
        raise RuntimeError(
            f"POPPLER_PATH invalid: {POPPLER_PATH!r}. Expected pdfinfo.exe inside this folder."
        )

    # Import here so missing Poppler won't crash the whole app at import-time
    from pdf2image import convert_from_path

    pages = convert_from_path(pdf_path, dpi=200, poppler_path=POPPLER_PATH)
    text = "\n".join(ocr_image_to_text(img) for img in pages)
    return parse_text_for_items(text)
