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
