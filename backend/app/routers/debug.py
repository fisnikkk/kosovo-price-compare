# backend/app/routers/debug.py
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session, aliased
from sqlalchemy import func

from ..db import SessionLocal
from ..models import StoreItem, Price, Store

router = APIRouter(prefix="/debug", tags=["debug"])
RECENT_DAYS = 14


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/store_counts")
def store_counts(db: Session = Depends(get_db)):
    SI = aliased(StoreItem)
    P = aliased(Price)

    q = (
        db.query(SI.store_id, func.count(P.id))
        .join(P, P.store_item_id == SI.id)
        .filter(P.collected_at >= func.date('now', f'-{RECENT_DAYS} days'))
        .group_by(SI.store_id)
        .order_by(SI.store_id)
    )
    rows = q.all()

    names = {s.id: s.name for s in db.query(Store).all()}
    return [{"store": names.get(sid, sid), "n": n} for sid, n in rows]
