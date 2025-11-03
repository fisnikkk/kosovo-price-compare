import os, asyncio, logging
from dotenv import load_dotenv
from app.scrapers._playwright_thread import collect_fb_images_sync

logging.basicConfig(level=logging.INFO)
load_dotenv()
FB_COOKIE = os.getenv("FB_COOKIE")

def main():
    for slug in ["InterexKs", "AlbiMarket"]:
        try:
            pairs = collect_fb_images_sync(slug=slug, scroll_pages=4, cookie_header=FB_COOKIE, want_n=12)
            print(f"{slug}: got {len(pairs)} images")
            for u, ref in pairs[:5]:
                print(" -", u[:120], " | ref:", ref[:80])
        except Exception as e:
            print(f"{slug} error:", e)

if __name__ == "__main__":
    main()
