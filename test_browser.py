"""Browser integration tests against a local fixture, with no SMTP calls."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
import unittest
from tempfile import TemporaryDirectory
from pathlib import Path
import subprocess
import time
import json
from urllib.request import urlopen

from check_stock import check_stock


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        if self.path == "/blocked":
            self.wfile.write(b"<title>Access Denied</title><h1>Access Denied</h1><button>Accetta tutti</button>")
            return
        if self.path.startswith("/hm-"):
            sold_out = self.path == "/hm-sold-out"
            status = "esaurita. Seleziona per ricevere una notifica se torna disponibile" if sold_out else "disponibile. Seleziona la taglia"
            marker = "out-of-stock" if sold_out else "in-stock"
            self.wfile.write((
                '<button>Accetta tutti</button>'
                f'<div role="radio" aria-checked="false" aria-label="Taglia XS: {status}" '
                'onclick="this.setAttribute(\'aria-checked\',\'true\')">'
                f'<div data-testid="002-{marker}">&nbsp;&nbsp;XS&nbsp;&nbsp;</div></div>'
                '<button>Aggiungi al carrello</button>'
                '<button style="display:none">Aggiungi al carrello</button>'
            ).encode())
            return
        disabled = "disabled" if self.path == "/sold-out" else ""
        self.wfile.write((
            '<button>Accetta tutti</button>'
            f'<button {disabled} onclick="document.querySelector(\'#cart\').disabled=false">XS</button>'
            '<button id="cart" disabled>Aggiungi al carrello</button>'
        ).encode())


class BrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def test_selected_xs_enables_purchase(self):
        self.assertTrue(check_stock(self.url + "/available"))

    def test_disabled_xs_is_unavailable(self):
        self.assertFalse(check_stock(self.url + "/sold-out"))

    def test_hm_radio_label_reports_sold_out_even_when_clickable(self):
        self.assertFalse(check_stock(self.url + "/hm-sold-out"))

    def test_hm_radio_with_nonbreaking_spaces_and_hidden_cart(self):
        self.assertTrue(check_stock(self.url + "/hm-available"))

    def test_persistent_profile_can_be_reopened(self):
        with TemporaryDirectory() as profile:
            self.assertTrue(check_stock(self.url + "/available", profile=profile))
            self.assertFalse(check_stock(self.url + "/sold-out", profile=profile))

    def test_http_200_block_is_an_error(self):
        with self.assertRaisesRegex(RuntimeError, "H&M antibot"):
            check_stock(self.url + "/blocked")

    def test_attach_to_existing_chrome_keeps_it_open(self):
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            executable = p.chromium.executable_path
        with TemporaryDirectory() as profile:
            url = self.url + "/available"
            process = subprocess.Popen([
                executable, "--headless=new", "--no-sandbox", "--no-first-run",
                "--remote-debugging-address=127.0.0.1", "--remote-debugging-port=0",
                f"--user-data-dir={profile}", url,
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                deadline = time.monotonic() + 15
                endpoint = None
                ready = False
                while time.monotonic() < deadline:
                    port_file = Path(profile) / "DevToolsActivePort"
                    if port_file.exists():
                        port = port_file.read_text().splitlines()[0]
                        endpoint = f"http://127.0.0.1:{port}"
                        with urlopen(endpoint + "/json/list", timeout=2) as response:
                            ready = any(tab.get("url") == url for tab in json.load(response))
                        if ready:
                            break
                    time.sleep(0.1)
                self.assertTrue(ready, "Chrome did not expose the fixture tab")
                self.assertTrue(check_stock(url, cdp_url=endpoint))
                self.assertIsNone(process.poll(), "The attached browser was closed")
                with urlopen(endpoint + "/json/list", timeout=2) as response:
                    self.assertTrue(any(tab.get("url") == url for tab in json.load(response)))
            finally:
                process.terminate()
                process.wait(timeout=10)


if __name__ == "__main__":
    unittest.main()
