"""Check the Italian H&M size selector and notify via Gmail SMTP."""

import argparse
import logging
import os
import re
import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path

URL = "https://www2.hm.com/it_it/productpage.1333421001.html"
RECIPIENT = "gienni.doria@gmail.com"
SIZE = re.compile(r"^XS(?:\s|$)", re.I)
UNAVAILABLE = re.compile(r"esaurit|non disponibile|avvisami|sold out|out of stock", re.I)
ADD = re.compile(r"aggiungi (?:al|nel) (?:carrello|sacchetto)|add to (?:bag|cart)", re.I)


def candidate_available(text: str, disabled: bool) -> bool:
    return bool(SIZE.match(text.strip())) and not disabled and not UNAVAILABLE.search(text)


def check_stock(url: str = URL) -> bool:
    # Import lazily so notification logic can be tested without a browser.
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(locale="it-IT")
        page = context.new_page()
        page.set_default_timeout(15000)
        try:
            response = page.goto(url, wait_until="domcontentloaded", timeout=60000)
            if response is None or response.status >= 400:
                raise RuntimeError(f"H&M HTTP {response.status if response else 'nessuna risposta'}")
            # Cookie consent may obscure the product controls.
            consent = page.get_by_role("button", name=re.compile(r"^(accetta tutti|accetta tutti i cookie|accept all)$", re.I))
            try:
                consent.first.click(timeout=5000)
            except Exception:
                pass
            # Some layouts keep sizes inside a dropdown.
            opener = page.get_by_role("button", name=re.compile(r"^(seleziona (?:la |una )?taglia|select size)", re.I))
            opener.or_(page.get_by_role("button", name=SIZE)).or_(page.get_by_role("radio", name=SIZE)).or_(page.get_by_role("option", name=SIZE)).first.wait_for(state="visible", timeout=45000)
            if opener.count() and opener.first.is_visible():
                opener.first.click()
            # Only interactive size controls count. A plain XS mention is insufficient.
            controls = page.locator("button, [role='radio'], [role='option'], label")
            xs = controls.filter(has_text=SIZE)
            xs.first.wait_for(state="visible", timeout=45000)
            matches = []
            for control in xs.all():
                if not control.is_visible():
                    continue
                text = control.inner_text().strip()
                if not SIZE.match(text):
                    continue
                disabled = control.is_disabled() or control.get_attribute("aria-disabled") == "true"
                matches.append((control, text, disabled))
            if not matches:
                raise RuntimeError("Selettore XS non riconosciuto: impossibile determinare la disponibilità")
            if len(matches) != 1:
                raise RuntimeError("Più selettori XS visibili: controllo ambiguo")
            control, text, disabled = matches[0]
            if not candidate_available(text, disabled):
                return False
            control.click()
            # Selecting XS must enable purchase. Never click the cart button.
            add = page.get_by_role("button", name=ADD)
            add.first.wait_for(state="visible", timeout=10000)
            if add.count() != 1:
                raise RuntimeError("Pulsante acquisto ambiguo")
            # Wait for the UI to settle after the size selection.
            try:
                from playwright.sync_api import expect
                expect(add).to_be_enabled(timeout=10000)
            except AssertionError:
                if page.get_by_role("button", name=re.compile("avvisami", re.I)).count():
                    return False
                raise RuntimeError("XS selezionata ma acquisto non confermato")
            return True
        except Exception:
            Path("artifacts").mkdir(exist_ok=True)
            page.screenshot(path="artifacts/check.png", full_page=True)
            Path("artifacts/page.html").write_text(page.content(), encoding="utf-8")
            raise
        finally:
            context.close()
            browser.close()


def send_email() -> None:
    username = os.environ.get("GMAIL_USERNAME", "").strip()
    password = os.environ.get("GMAIL_APP_PASSWORD", "").replace(" ", "")
    if not username or not password:
        raise RuntimeError("Configura i secret GMAIL_USERNAME e GMAIL_APP_PASSWORD")
    message = EmailMessage()
    message["From"] = username
    message["To"] = RECIPIENT
    message["Subject"] = "H&M: taglia XS disponibile"
    message.set_content(
        "La taglia XS risulta acquistabile per l'impermeabile H&M monitorato.\n\n"
        f"{URL}\n\nLa disponibilità può cambiare prima dell'acquisto.\n"
    )
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ssl.create_default_context(), timeout=30) as smtp:
        smtp.login(username, password)
        smtp.send_message(message)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Controlla senza inviare email")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    available = check_stock()
    logging.info("XS: %s", "disponibile" if available else "esaurita")
    if available and not args.dry_run:
        send_email()
        logging.info("Email inviata a %s", RECIPIENT)


if __name__ == "__main__":
    main()
