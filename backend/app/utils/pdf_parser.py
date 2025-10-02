from __future__ import annotations
import re
from typing import List, Dict, Tuple, Optional
from datetime import datetime

import pdfplumber
from pdf2image import convert_from_path
import pytesseract

PRICE_RE = re.compile(r"(\d+[.,]\d{1,2})\s*€?")
DATE_RE  = re.compile(r"(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})")

def _parse_date(s: str) -> Optional[datetime]:
    for fmt in ("%d.%m.%Y", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%y", "%d/%m/%y", "%d-%m-%y"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            pass
    return None

def _dedupe(items: List[Dict]) -> List[Dict]:
    uniq = {}
    for it in items:
        key = (it["raw_name"], round(it["price_eur"], 2))
        uniq[key] = it
    return list(uniq.values())

def _extract_items_from_text(text: str) -> Tuple[List[Dict], Tuple[Optional[datetime], Optional[datetime]]]:
    items: List[Dict] = []
    vfrom: Optional[datetime] = None
    vto: Optional[datetime] = None

    # try to capture validity range anywhere in the text
    dates = DATE_RE.findall(text)
    if len(dates) >= 2:
        d1 = _parse_date(dates[0]); d2 = _parse_date(dates[1])
        if d1 and d2:
            vfrom, vto = (min(d1, d2), max(d1, d2))

    for line in text.splitlines():
        line_c = " ".join(line.split())
        if not line_c:
            continue
        m = PRICE_RE.search(line_c.replace(",", "."))
        if not m:
            continue
        try:
            price = float(m.group(1).replace(",", "."))
        except:
            continue
        name = PRICE_RE.sub("", line_c).strip(" :-•–—")
        if len(name) < 3:
            continue
        items.append({"raw_name": name, "price_eur": price})

    return _dedupe(items), (vfrom, vto)

def _text_from_pdf_plumber(path: str) -> str:
    out = []
    with pdfplumber.open(path) as pdf:
        for p in pdf.pages:
            out.append(p.extract_text() or "")
    return "\n".join(out)

def _text_from_pdf_ocr(path: str) -> str:
    # Poppler renders -> images; Tesseract OCR
    pages = convert_from_path(path, dpi=200)
    chunks = []
    for img in pages:
        # Try Albanian + English; fall back to eng
        try:
            txt = pytesseract.image_to_string(img, lang="sqi+eng")
        except:
            txt = pytesseract.image_to_string(img, lang="eng")
        chunks.append(txt or "")
    return "\n".join(chunks)

def parse_generic_flyer(path: str) -> Tuple[List[Dict], Tuple[Optional[datetime], Optional[datetime]]]:
    """
    Try text extraction first; if empty/too few items, OCR fallback.
    """
    # 1) text path
    text = _text_from_pdf_plumber(path)
    items, validity = _extract_items_from_text(text)

    # 2) OCR fallback if needed
    if len(items) < 5:
        ocr_text = _text_from_pdf_ocr(path)
        items2, validity2 = _extract_items_from_text(ocr_text)
        if len(items2) > len(items):
            items, validity = items2, validity2

    return items, validity
