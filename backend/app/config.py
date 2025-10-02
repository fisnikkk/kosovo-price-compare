import os
from dotenv import load_dotenv
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./kpc.db")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
API_HOST = os.getenv("API_HOST", "127.0.0.1")
API_PORT = int(os.getenv("API_PORT", "8000"))
SCRAPE_CITY = os.getenv("SCRAPE_CITY", "Prishtina")
