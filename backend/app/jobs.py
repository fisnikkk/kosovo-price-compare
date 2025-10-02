# app/jobs.py
from __future__ import annotations

import logging
import os
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.orm import Session

from .db import SessionLocal, Base, engine
from .models import Product, StoreItem
from .scrapers.maxi import crawl_maxi
from .scrapers.vivafresh import crawl_vivafresh
from .scrapers.interex_flyer import crawl_interex_flyer
from .scrapers.spar_wolt import crawl_spar_wolt           # optional (dynamic, may be flaky)
from .scrapers.spar_flyer import crawl_spar_flyer         # new (PDF flyer, robust)
from .scrapers.etc_flyer import crawl_etc_flyer
from .config import SCRAPE_CITY
from .utils.matching import score_item_against_product, ensure_mapping

logger = logging.getLogger(__name__)

# --------- Runtime toggles (set in env or .env.example) ----------
RUN_MAXI         = os.getenv("RUN_MAXI", "1") == "1"
RUN_VIVAFRESH    = os.getenv("RUN_VIVAFRESH", "1") == "1"
RUN_INTEREX      = os.getenv("RUN_INTEREX", "1") == "1"
RUN_SPAR_WOLT    = os.getenv("RUN_SPAR_WOLT", "0") == "1"   # default OFF
RUN_SPAR_FLYER   = os.getenv("RUN_SPAR_FLYER", "1") == "1"  # default ON
RUN_ETC_FLYER  = os.getenv("RUN_ETC_FLYER", "1") == "1"  # default ON


# --------- Initial product seeds (canonical SKUs) ----------
ESSENTIALS = [
    {"canonical_name":"Milk 1L 2.8%", "category":"milk", "unit":"l", "brand":None, "size_ml_g":1000, "fat_pct":2.8},
    {"canonical_name":"Milk 1L 3.5%", "category":"milk", "unit":"l", "brand":None, "size_ml_g":1000, "fat_pct":3.5},
    {"canonical_name":"Feta / White Cheese 400g", "category":"cheese", "unit":"kg", "brand":None, "size_ml_g":400, "fat_pct":None},
    {"canonical_name":"Yogurt 1kg tub", "category":"yogurt", "unit":"kg", "brand":None, "size_ml_g":1000, "fat_pct":None},
    {"canonical_name":"Butter 250g", "category":"butter", "unit":"kg", "brand":None, "size_ml_g":250, "fat_pct":None},
    {"canonical_name":"Potatoes per kg", "category":"vegetable", "unit":"kg", "brand":None, "size_ml_g":1000, "fat_pct":None},
]

def seed_products(db: Session) -> None:
    for e in ESSENTIALS:
        exists = db.query(Product).filter_by(canonical_name=e["canonical_name"]).one_or_none()
        if not exists:
            db.add(Product(**e))
    db.commit()

# --------- Main scrape orchestration ----------
async def run_all_scrapers():
    db = SessionLocal()
    try:
        Base.metadata.create_all(engine)
        seed_products(db)

        if RUN_MAXI:
            try:
                await crawl_maxi(db, SCRAPE_CITY)
            except Exception:
                logger.exception("[maxi] failed")

        if RUN_VIVAFRESH:
            try:
                await crawl_vivafresh(db, SCRAPE_CITY)
            except Exception:
                logger.exception("[vivafresh] failed")

        if RUN_INTEREX:
            try:
                await crawl_interex_flyer(db, SCRAPE_CITY)
            except Exception:
                logger.exception("[interex] failed")

        if RUN_SPAR_FLYER:
            try:
                await crawl_spar_flyer(db, SCRAPE_CITY)
            except Exception:
                logger.exception("[spar-flyer] failed")

        if RUN_SPAR_WOLT:
            try:
                await crawl_spar_wolt(db, SCRAPE_CITY)
            except Exception:
                logger.exception("[spar-wolt] failed")
        
        if RUN_ETC_FLYER:
            try:
                await crawl_etc_flyer(db, SCRAPE_CITY)
            except Exception:
                logger.exception("[etc-flyer] failed")


        # ----- Auto-match scraped StoreItems to canonical Products -----
        prods = db.query(Product).all()
        items = db.query(StoreItem).all()

        for it in items:
            for p in prods:
                score = score_item_against_product(it.raw_name, p)
                ensure_mapping(db, p, it, score, threshold=0.7)

        db.commit()

    finally:
        db.close()

# --------- Scheduler ----------
def start_scheduler():
    sch = AsyncIOScheduler()
    # Full run nightly
    sch.add_job(run_all_scrapers, "cron", hour=3, minute=15)
    # Quick refresh every 2 hours (same pipeline for simplicity)
    sch.add_job(run_all_scrapers, "cron", hour="*/2", minute=5)
    sch.start()
