# backend/app/scrapers/vivafresh_runner.py
import asyncio
from app.db import SessionLocal
from app.scrapers.vivafresh import crawl_vivafresh

def main():
    db = SessionLocal()
    try:
        asyncio.run(crawl_vivafresh(db, "Prishtina"))
    finally:
        db.close()

if __name__ == "__main__":
    main()
