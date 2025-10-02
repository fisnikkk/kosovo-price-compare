# backend/app/main.py
import sys
import asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Use the selector loop on Windows (Playwright & schedulers are happier with it)
if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from .db import Base, engine
from .routers import products, compare
# from .jobs import start_scheduler, run_all_scrapers  # enable later

app = FastAPI(title="Kosovo Price Compare API")

# CORS for emulator/browser in dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten later
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# create tables and mount routers
Base.metadata.create_all(engine)
app.include_router(products.router)
app.include_router(compare.router)

@app.get("/")
def root():
    return {"ok": True, "service": "kpc-api"}

# Enable these later after you confirm the API boots:
# @app.on_event("startup")
# async def on_startup():
#     asyncio.create_task(run_all_scrapers())
#     start_scheduler()
