"""Check the Italian H&M size selector and notify via Gmail SMTP."""

import argparse
import logging
import os
import re
import smtplib
import ssl
import shutil
import subprocess
from email.message import EmailMessage
from pathlib import Path

URL = "https://www2.hm.com/it_it/productpage.1333421001.html"
RECIPIENT = "gienni.doria@gmail.com"
SIZE = re.compile(r"^XS(?:\s|$)", re.I)
UNAVAILABLE = re.compile(r"esaurit|non disponibile|avvisami|sold out|out of stock", re.I)
ADD = re.compile(r"aggiungi (?:al|nel) (?:carrello|sacchetto)|add to (?:bag|cart)", re.I)


def candidate_available(text: str, disabled: bool) -> bool:
    return bool(SIZE.match(text.strip())) and not disabled and not UNAVAILABLE.search(text)


def check_stock(url: str = URL, *, headed: bool = False, channel: str | None = None,
                profile: str | None = None, cdp_url: str | None = None) -> bool:
    # Import lazily so notification logic can be tested without a browser.
    from playwright.sync_api import sync_playwright

    if cdp_url:
        logging.info("Connessione al Chrome già aperto su %s...", cdp_url)
    else:
        logging.info("Avvio %s (%s), profilo: %s", channel or "Chromium",
                     "con interfaccia" if headed else "senza interfaccia", profile or "temporaneo")
    with sync_playwright() as p:
        browser = None
        if cdp_url:
            browser = p.chromium.connect_over_cdp(cdp_url, timeout=15000)
            if not browser.contexts:
                raise RuntimeError("Chrome non contiene una sessione aperta")
            context = browser.contexts[0]
            matches = [tab for tab in context.pages if tab.url.split('#')[0] == url]
            if len(matches) != 1:
                raise RuntimeError("Apri una sola scheda con il link del prodotto nel Chrome dedicato prima del controllo")
            page = matches[0]
        elif profile:
            context = p.chromium.launch_persistent_context(
                str(Path(profile).resolve()), channel=channel, headless=not headed,
                locale="it-IT", timezone_id="Europe/Rome",
                timeout=30000,
            )
        else:
            browser = p.chromium.launch(headless=not headed, channel=channel, timeout=30000)
            context = browser.new_context(locale="it-IT")
        if not cdp_url:
            page = context.pages[0] if context.pages else context.new_page()
        page.set_default_timeout(15000)
        try:
            if cdp_url:
                logging.info("Uso la scheda prodotto già aperta, senza ricaricarla.")
                page.wait_for_load_state("domcontentloaded", timeout=15000)
            else:
                logging.info("Browser avviato. Caricamento prodotto (massimo 60 secondi)...")
                response = page.goto(url, wait_until="domcontentloaded", timeout=60000)
                logging.info("Risposta HTTP: %s", response.status if response else "nessuna risposta")
                if response is None or response.status >= 400:
                    raise RuntimeError(f"H&M HTTP {response.status if response else 'nessuna risposta'}")
            # Cookie consent may obscure the product controls.
            consent = page.get_by_role("button", name=re.compile(r"^(accetta tutti|accetta tutti i cookie|accept all)$", re.I))
            try:
                consent.first.click(timeout=5000)
            except Exception:
                pass
            if page.title().strip().lower() == "access denied":
                raise RuntimeError("H&M antibot: Access Denied dopo il caricamento JavaScript")
            # Some layouts keep sizes inside a dropdown.
            logging.info("Pagina: %s. Ricerca selettore taglie (massimo 45 secondi)...", page.title())
            opener = page.get_by_role("button", name=re.compile(r"^(seleziona (?:la |una )?taglia|select size)", re.I))
            opener.or_(page.get_by_role("button", name=SIZE)).or_(page.get_by_role("radio", name=SIZE)).or_(page.get_by_role("option", name=SIZE)).first.wait_for(state="visible", timeout=45000)
            if opener.count() and opener.first.is_visible():
                logging.info("Apertura selettore taglie...")
                opener.first.click()
            # Only interactive size controls count. A plain XS mention is insufficient.
            controls = page.locator("button, [role='radio'], [role='option'], label")
            xs = controls.filter(has_text=SIZE)
            logging.info("Ricerca controllo XS (massimo 45 secondi)...")
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
            logging.info("Controllo XS trovato: %r, disabilitato: %s", text, disabled)
            if not candidate_available(text, disabled):
                return False
            control.click()
            logging.info("XS selezionata. Verifica pulsante acquisto...")
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
        except Exception as exc:
            Path("artifacts").mkdir(exist_ok=True)
            blocked = False
            try:
                blocked = page.title().strip().lower() == "access denied"
                Path("artifacts/page.html").write_text(page.content(), encoding="utf-8")
                page.screenshot(path="artifacts/check.png", full_page=True, timeout=5000)
                logging.error("Diagnostica salvata in artifacts/page.html e artifacts/check.png")
            except Exception as diagnostic_error:
                logging.warning("Diagnostica incompleta: %s", diagnostic_error)
            if blocked:
                raise RuntimeError("H&M antibot: Access Denied; disponibilità non verificabile") from exc
            raise
        finally:
            if not cdp_url:
                context.close()
                if browser:
                    browser.close()


def init_session(profile: str, *, debug: bool = False) -> None:
    """Open ordinary Chrome so the user can initialize a separate profile."""
    candidates = [shutil.which("google-chrome"), shutil.which("chrome")]
    for root in (os.environ.get("PROGRAMFILES"), os.environ.get("PROGRAMFILES(X86)"), os.environ.get("LOCALAPPDATA")):
        if root:
            candidates.append(str(Path(root) / "Google/Chrome/Application/chrome.exe"))
    executable = next((path for path in candidates if path and Path(path).is_file()), None)
    if not executable:
        raise RuntimeError("Chrome non trovato: installa Google Chrome prima di inizializzare la sessione")
    directory = Path(profile).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    command = [executable, f"--user-data-dir={directory}", "--no-first-run"]
    if debug:
        command.extend(["--remote-debugging-address=127.0.0.1", "--remote-debugging-port=9222"])
    subprocess.Popen([*command, URL])
    print("Apri il prodotto e verifica che compaiano le taglie nel Chrome appena aperto.")
    print("Lascia aperta la scheda prodotto e lancia il controllo con --cdp." if debug else
          "Poi chiudi tutte le finestre di questo profilo prima di lanciare il controllo.")
    print("Nessuna email inviata. Profilo:", directory)


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
    parser.add_argument("--headed", action="store_true", help="Esegue Chromium con interfaccia (su Linux usare xvfb-run)")
    parser.add_argument("--browser", choices=["chromium", "chrome"], default="chromium")
    parser.add_argument("--profile", help="Cartella di un profilo dedicato, ad esempio .hm-chrome")
    parser.add_argument("--init-session", action="store_true", help="Apre Chrome normale per inizializzare manualmente il profilo, senza controllo o email")
    parser.add_argument("--cdp", action="store_true", help="Si collega a Chrome aperto normalmente sulla porta locale 9222, senza ricaricare il prodotto")
    args = parser.parse_args()
    if args.init_session:
        if not args.profile or args.browser != "chrome":
            parser.error("--init-session richiede --browser chrome e --profile")
        init_session(args.profile, debug=args.cdp)
        return
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    logging.info("Controllo avviato. Invio email: %s", "disattivato (dry-run)" if args.dry_run else "solo se XS disponibile")
    available = check_stock(headed=args.headed, channel="chrome" if args.browser == "chrome" else None,
                            profile=args.profile, cdp_url="http://127.0.0.1:9222" if args.cdp else None)
    logging.info("XS: %s", "disponibile" if available else "esaurita")
    if available and not args.dry_run:
        send_email()
        logging.info("Email inviata a %s", RECIPIENT)


if __name__ == "__main__":
    main()
