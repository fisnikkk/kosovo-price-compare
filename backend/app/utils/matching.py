from rapidfuzz import fuzz, process
from sqlalchemy.orm import Session
from ..models import Product, StoreItem, Mapping

def score_item_against_product(item_name: str, prod: Product) -> float:
    # Base fuzzy on names
    s1 = fuzz.token_set_ratio(item_name, prod.canonical_name) / 100.0
    # brand boost
    brand_boost = 0.15 if (prod.brand and prod.brand.lower() in item_name.lower()) else 0.0
    # category weak boost (assumes category word present)
    cat_boost = 0.10 if prod.category.lower() in item_name.lower() else 0.0
    # size proximity bonus/penalty
    size_bonus = 0.0
    from ..utils.normalize import parse_size_and_fat
    item_size, _, item_fat = parse_size_and_fat(item_name)
    if prod.size_ml_g and item_size:
        diff = abs(prod.size_ml_g - item_size) / max(prod.size_ml_g, 1)
        size_bonus = 0.15 if diff <= 0.1 else (0.05 if diff <= 0.2 else -0.1)
    fat_bonus = 0.0
    if prod.fat_pct and item_fat:
        fdiff = abs(prod.fat_pct - item_fat)
        fat_bonus = 0.1 if fdiff <= 0.3 else (0.05 if fdiff <= 0.7 else -0.1)

    return max(0.0, min(1.0, s1 + brand_boost + cat_boost + size_bonus + fat_bonus))

def ensure_mapping(db: Session, product: Product, item: StoreItem, score: float, threshold: float = 0.7):
    existing = db.query(Mapping).filter_by(product_id=product.id, store_item_id=item.id).one_or_none()
    if score >= threshold:
        if not existing:
            db.add(Mapping(product_id=product.id, store_item_id=item.id, match_score=score))
    else:
        # Do nothing; could log for manual review
        pass
