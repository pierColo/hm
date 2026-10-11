"""Read-only probe: compare default and full Chromium on H&M."""
import argparse
import platform
from pathlib import Path
from playwright.sync_api import sync_playwright

URL = "https://www2.hm.com/it_it/productpage.1333421001.html"
parser = argparse.ArgumentParser()
parser.add_argument("--headed", action="store_true")
args = parser.parse_args()

with sync_playwright() as p:
    for mode in ("default", "full"):
        options = {} if mode == "default" else {"channel": "chromium", "args": ["--disable-blink-features=AutomationControlled"]}
        browser = p.chromium.launch(headless=not args.headed, **options)
        system = "Windows NT 10.0; Win64; x64" if platform.system() == "Windows" else "X11; Linux x86_64"
        ua = f"Mozilla/5.0 ({system}) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{browser.version} Safari/537.36"
        context = browser.new_context(locale="it-IT", timezone_id="Europe/Rome", viewport={"width": 1366, "height": 900}, **({"user_agent": ua} if mode == "full" else {}))
        page = context.new_page()
        try:
            if mode == "full":
                home = page.goto("https://www2.hm.com/it_it/index.html", wait_until="domcontentloaded", timeout=45000)
                print(mode, "home", home.status, flush=True)
                page.wait_for_timeout(3000)
            response = page.goto(URL, wait_until="domcontentloaded", timeout=45000)
            print(mode, "product", response.status, "title", page.title(), flush=True)
            page.wait_for_timeout(12000)
            body = page.locator("body").inner_text(timeout=5000)
            print(mode, "after-js", "title", page.title(), "body", body[:800], flush=True)
            Path("artifacts").mkdir(exist_ok=True)
            Path(f"artifacts/probe-{mode}.html").write_text(page.content(), encoding="utf-8")
            page.screenshot(path=f"artifacts/probe-{mode}.png", full_page=True)
        except Exception as exc:
            print(mode, type(exc).__name__, str(exc)[:300], flush=True)
        finally:
            browser.close()
