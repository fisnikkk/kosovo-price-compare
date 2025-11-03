import re

# --- NEW, TIGHTER BRAND DETECTION LOGIC ---

# Minimal brand lexicon; extend freely
BRANDS = {
    "Fructal", "Relax", "Rugove", "Abi", "Sharri", "Alpsko", "Magic",
    "Bylmet", "Coca-Cola", "Pepsi", "Sprite", "Fanta", "Ariel", "Persil",
    "Somat", "Finish", "Palmolive", "Violeta", "Plazma", "Barilla", "Jacobs",
    "Grand", "Doncafe", "Lavazza", "Nescafe", "Bambi"
}

# Words we must NOT call a brand (generic product words + OCR noise)
GENERIC_WORDS = {
    "kos", "jogurt", "jogurti", "jogurtit", "leng", "lëng", "mish", "biskota",
    "fasule", "shampo", "kafe", "ajvar", "rrush", "patate", "detergjent",
    "pastrues", "akullore", "qumesht", "qumësht", "embelsire", "ëmbëlsirë"
}

def _normalize(s: str) -> str:
    s = s.lower()
    # strip punctuation and duplicated spaces
    s = re.sub(r"[^a-z0-9çëšžđáéíóúäëöü\- ]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def detect_brand(name: str) -> str | None:
    n = _normalize(name)
    tokens = set(n.split())
    # direct brand match (case-insensitive)
    for b in BRANDS:
        if _normalize(b) in n:
            return b
    # if first token looks proper, consider it—but only if not generic
    first = n.split(" ")[0] if n else ""
    if first and first not in GENERIC_WORDS and first[0].isalpha() and len(first) > 2:
        # prefer capitalized version if exists in original
        for w in name.split():
            if w.lower() == first:
                return w
    return None

# --- NEW, TIGHTER CATEGORY DETECTION LOGIC ---

def detect_category(name: str) -> str | None:
    n = _normalize(name)

    # quick negative guards
    if "akullore" in n or "tartuf" in n:
        return "Embelsire"  # or None if you don’t want this category yet

    # ordered rules — first match wins
    rules = [
        ("Leng",       ["lëng", "leng", "juice", "sok"]),
        ("Mish",       ["mish", "suxhuk", "suxhuku", "salami", "sallam", "pepperoni"]),
        ("Biskota",    ["biskota", "keks", "biscuit", "plazma"]),
        ("Fasule",     ["fasule", "fasul", "groshë", "grose"]),
        ("Shampo",     ["shampo", "shampanjë"]),  # tune if “shampanjë” is champagne :)
        ("Kafe",       ["kafe", "nescafe", "jacobs", "lavazza", "grand", "doncafe"]),
        ("Ajvar",      ["ajvar"]),
        ("Rrush",      ["rrush", "stafidhe", "rrush i thatë"]),
        ("Patate",     ["patate", "kartof"]),
        ("Detergjent per enë", ["enë", "ene", "larje enesh", "finish", "somat", "tableta për enë"]),
        ("Pastrues",   ["pastrues", "cleaner", "dezenfektues", "dezinfektues"]),
        # Dairy guard: yogurt/kos
        ("Kos",        ["kos", "jogurt"]),
    ]

    for cat, kws in rules:
        if any(k in n for k in kws):
            # extra guard: don't call “Leng” if ice-cream is present
            if cat == "Leng" and ("akullore" in n or "tartuf" in n):
                continue
            return cat

    return None
