"""Read product controls from the dedicated Chrome session without navigation."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright
from check_stock import URL

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222", timeout=10000)
    pages = [tab for context in browser.contexts for tab in context.pages if tab.url.split('#')[0] == URL]
    if len(pages) != 1:
        raise RuntimeError("Apri una sola scheda con il prodotto nel Chrome dedicato")
    page = pages[0]
    print("Pagina:", page.title())
    data = page.locator("button, select, input, [role='radio'], [role='option'], label").evaluate_all("""els => els.map(e => ({
        tag: e.tagName, text: e.innerText, aria: e.getAttribute('aria-label'),
        role: e.getAttribute('role'), id: e.id, disabled: e.disabled,
        visible: !!(e.offsetWidth || e.offsetHeight || e.getClientRects().length),
        html: e.outerHTML.slice(0, 1800)
    })).filter(e => /XS|taglia|size|carrello|sacchetto/i.test([e.text,e.aria,e.html].join(' ')))""")
    print(json.dumps(data, ensure_ascii=True, indent=2))
    Path("artifacts").mkdir(exist_ok=True)
    Path("artifacts/controls.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
