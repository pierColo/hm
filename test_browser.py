"""Browser integration tests against a local fixture, with no SMTP calls."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
import unittest

from check_stock import check_stock


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
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


if __name__ == "__main__":
    unittest.main()
