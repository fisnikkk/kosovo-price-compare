# app/utils/fb_login_capture.py
import os, json, asyncio
from pathlib import Path
from playwright.async_api import async_playwright

PROFILE_DIR = "data/fb_profile"
STATE = "data/fb_state.json"

async def main():
    os.makedirs("data", exist_ok=True)

    async with async_playwright() as pw:
        # Persistent profile behaves like normal Chrome; fewer reload quirks
        ctx = await pw.chromium.launch_persistent_context(
            user_data_dir=PROFILE_DIR,
            headless=False,
            args=["--lang=en-US"],
            viewport={"width": 412, "height": 915},
            device_scale_factor=2,
            is_mobile=True, has_touch=True,
            locale="en-US",
            user_agent=("Mozilla/5.0 (Linux; Android 12; Pixel 5) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0.0.0 Mobile Safari/537.36"),
            # make it calmer
            no_viewport=False,
            accept_downloads=False,
            java_script_enabled=True,
            service_workers="block",
        )

        # Block deep-links / app prompts that can bounce the page
        await ctx.route(
            "**/*",
            lambda route: route.abort() if any(
                s in route.request.url.lower() for s in
                ("open_app", "app_link", "fb://", "intent://")
            ) else route.continue_()
        )

        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        await page.goto("https://m.facebook.com/?locale=en_US", wait_until="domcontentloaded")

        print(
            "\n>>> In the Chromium window:\n"
            "  1) Log in if prompted.\n"
            "  2) Open https://m.facebook.com/InterexKs/  (Photos tab).\n"
            "  3) Click an album (e.g., “Interex's Photos”).\n"
            "  4) Click ANY single photo so the URL is /photo.php?...\n"
            "When the single photo is open and fully loaded, PRESS ENTER here to save.\n"
        )
        input()

        state = await ctx.storage_state()
        Path(STATE).write_text(json.dumps(state), encoding="utf-8")
        print(f"[fb_login_capture] Saved storage state -> {STATE}")

        input("Press ENTER to close the browser…")
        await ctx.close()

if __name__ == "__main__":
    asyncio.run(main())
