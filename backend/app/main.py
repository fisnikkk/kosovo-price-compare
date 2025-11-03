# backend/app/main.py
import logging
logging.basicConfig(level=logging.INFO)

import sys
import os
import asyncio
from dotenv import load_dotenv

# Fix for Poppler by adding its path to the environment PATH
load_dotenv()
pp = (os.getenv("POPPLER_PATH") or "").strip().strip('"')
if pp and os.path.isdir(pp):
    os.environ["PATH"] = pp + os.pathsep + os.environ.get("PATH", "")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .db import Base, engine
from .jobs import start_scheduler, run_all_scrapers
from .routers import products, compare, debug  # ✅ import all routers here

log = logging.getLogger(__name__)

# ✅ Create the app first
app = FastAPI(title="Kosovo Price Compare API")

# ✅ Then include routers
app.include_router(products.router)
app.include_router(compare.router)
app.include_router(debug.router)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

Base.metadata.create_all(engine)

# Root health check
@app.get("/")
def root():
    return {"ok": True, "service": "kpc-api", "instance": "desktop-copy"}

# Manual trigger
@app.post("/admin/run")
async def admin_run():
    asyncio.create_task(run_all_scrapers())
    return {"started": True}

# Startup event
@app.on_event("startup")
async def on_startup():
    log.info("Starting initial scraping task…")
    asyncio.create_task(run_all_scrapers())
    start_scheduler()
