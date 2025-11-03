from sqlalchemy.orm import Session
from ..models import Product, StoreItem, Mapping

# Defensive matching gates to improve accuracy
AL_TOKENS = {
    "milk": {"qumesht", "qumësht", "qumeshti", "qumështi", "milk", "mleko", "latte"},
    "yogurt": {"jogurt", "jogurti", "kos", "kefir", "ajran", "ayran", "yogurt"},
    "butter": {"gjalp", "gjalpë", "butter", "margarine"},
    "cheese": {"djath", "djathë", "feta", "white cheese", "sir", "kackavall", "kačkavalj"},
}

NEGATIVE_BY_CATEGORY = {
    "milk": AL_TOKENS["yogurt"] | {"kefir", "ajke", "cream"},
    "yogurt": AL_TOKENS["milk"],
    "butter": {"margarine"},
}

def normalize(s: str) -> str:
    return s.lower()

def has_any(s: str, words: set[str]) -> bool:
    s = normalize(s)
    return any(w in s for w in words)

def score_item_against_product(item_name: str, product: Product) -> float:
    name = normalize(item_name)
    cat = product.category

    # Hard blocks to avoid milk<->yogurt cross hits
    if cat in NEGATIVE_BY_CATEGORY and has_any(name, NEGATIVE_BY_CATEGORY[cat]):
        return 0.0

    # Require at least one positive token for the category
    if cat in AL_TOKENS and not has_any(name, AL_TOKENS[cat]):
        return 0.0

    score = 0.0

    # Brand hint
    if product.brand and product.brand.lower() in name:
        score += 0.3

    # Size hints (ml/g or “1l”)
    if product.size_ml_g:
        ml = product.size_ml_g
        candidates = {f"{ml}g", f"{ml} gr", f"{ml}gr", f"{ml}ml"}
        if 1000 <= ml <= 1200:
            candidates |= {"1l", "1 l"}
        if has_any(name, candidates):
            score += 0.35

    # Fat %
    if product.fat_pct:
        fat = str(product.fat_pct).replace(".", ",")
        if f"{fat}%" in name or f"{product.fat_pct}%" in name:
            score += 0.25

    # Category tokens add a small baseline
    if cat in AL_TOKENS and has_any(name, AL_TOKENS[cat]):
        score += 0.2

    return min(score, 1.0)

def ensure_mapping(db: Session, product: Product, item: StoreItem, score: float, threshold: float = 0.7):
    existing = db.query(Mapping).filter_by(product_id=product.id, store_item_id=item.id).one_or_none()
    if score >= threshold:
        if not existing:
            db.add(Mapping(product_id=product.id, store_item_id=item.id, match_score=score))
        # Optional: Update score if it has changed significantly
        # elif existing.match_score != score:
        #     existing.match_score = score
    else:
        # If score drops below threshold, you might want to remove an existing mapping
        # if existing:
        #     db.delete(existing)
        pass
