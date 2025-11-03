# app/scrapers/vivafresh.py
from __future__ import annotations
from sqlalchemy.orm import Session
import anyio

async def crawl_vivafresh(db: Session, city: str = "Prishtina") -> int:
    from ._playwright_thread import crawl_vivafresh_sync
    return await anyio.to_thread.run_sync(crawl_vivafresh_sync, db, city)