# backend/app/settings.py
import os
from dotenv import load_dotenv
load_dotenv()
FB_COOKIE = os.getenv("FB_COOKIE")
TESSERACT_CMD = os.getenv("TESSERACT_CMD")
POPPLER_PATH = os.getenv("POPPLER_PATH")
