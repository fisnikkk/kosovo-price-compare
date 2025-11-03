from __future__ import annotations
from typing import Optional
from sqlalchemy.orm import Session
from .facebook_flyer import crawl_facebook_flyer

async def crawl_interex_flyer(db: Session, city: Optional[str] = None):
    return await crawl_facebook_flyer(
        db,
        slug="interex",
        store_name="Interex",
        fb_page_url="https://m.facebook.com/InterexKs/photos",
        city=city,
        scroll_pages=6,
    )
