# backend/app/utils/normalize.py
import re

def parse_size_and_fat(text: str):
    t = text.lower().replace(",", ".")
    size, unit, fat = None, None, None
    m = re.search(r'(\d+(?:\.\d+)?)\s?(l|ml|kg|g)\b', t)
    if m:
        val = float(m.group(1))
        unit = m.group(2)
        if unit in ("l", "kg"):
            size = int(val * 1000)
        else:
            size = int(val)
    f = re.search(r'(\d+(?:\.\d+)?)\s?%', t)
    if f:
        fat = float(f.group(1))
    return size, unit, fat

def unit_price_eur(price_eur: float, size_ml_g: int | None, unit_hint: str | None):
    """
    Returns €/kg for solids or €/l for liquids.
    If unit_hint is 'kg' or 'g' -> €/kg
       unit_hint is 'l' or 'ml' -> €/l
    """
    if not size_ml_g or size_ml_g <= 0:
        return None
    per = (size_ml_g / 1000.0)
    if per == 0:
        return None
    return round(price_eur / per, 2)

# --- 👇 ADDITIONS FROM THE REPORT ---

# For Problem 1 (Store Name Normalization)
STORE_CANON = {
    'albi market': 'Albi',
    'albimarket': 'Albi',
    'interexks': 'Interex',
    'interex': 'Interex',
    'viva fresh': 'Viva Fresh',
    'vivafresh': 'Viva Fresh',
    'maxi': 'Maxi',
    'spar kosova': 'SPAR',
}

def canon_store(s: str) -> str:
    """Normalizes a raw store name to a canonical one."""
    return STORE_CANON.get(s.strip().lower(), s.strip())

# For Problem 2 (Classification)
def parse_fat_pct(text: str) -> float | None:
    """Extracts fat percentage from a string."""
    m = re.search(r'(\d+(?:[.,]\d+)?)\s*%', text)
    if not m: return None
    try:
        # Handles both 2.8 and 2,8
        return float(m.group(1).replace(',', '.'))
    except Exception:
        return None

def classify(name: str) -> str:
    """Classifies a product name into a simple category."""
    n = name.lower()
    if any(k in n for k in ['jogurt','yogurt','joghurt','kos']):
        return 'yogurt'
    if any(k in n for k in ['qumesht','milk','mleko']):
        return 'milk'
    if any(k in n for k in ['gjalp','butter','margarine']):
        return 'butter'
    if any(k in n for k in ['djath','kackavall','sir','cheese','feta']):
        return 'cheese'
    if any(k in n for k in ['patate','krompir','potato']):
        return 'potato'
    return 'other'
# --- END ADDITIONS ---
