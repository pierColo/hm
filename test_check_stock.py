import unittest
import os
import smtplib
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from check_stock import RECIPIENT, candidate_available, send_email, main, load_local_env


class StockTests(unittest.TestCase):
    @patch.dict("os.environ", {}, clear=True)
    def test_dotenv_supports_bom_and_literal_password(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text('GMAIL_USERNAME=sender@gmail.com\nGMAIL_APP_PASSWORD="literal${TOKEN}"\n', encoding="utf-8-sig")
            load_local_env(path)
            self.assertEqual(os.environ["GMAIL_USERNAME"], "sender@gmail.com")
            self.assertEqual(os.environ["GMAIL_APP_PASSWORD"], "literal${TOKEN}")

    @patch.dict("os.environ", {"GMAIL_USERNAME": "secret@gmail.com", "GMAIL_APP_PASSWORD": "secret"}, clear=True)
    def test_dotenv_does_not_override_environment(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text("GMAIL_USERNAME=file@gmail.com\nGMAIL_APP_PASSWORD=file-password\n", encoding="utf-8")
            load_local_env(path)
            self.assertEqual(os.environ["GMAIL_USERNAME"], "secret@gmail.com")
            self.assertEqual(os.environ["GMAIL_APP_PASSWORD"], "secret")

    def test_size_must_be_available(self):
        self.assertTrue(candidate_available("XS", False))
        for text, disabled in [("XS", True), ("XS Esaurita", False), ("XS Avvisami", False), ("XXS", False), ("Disponibile XS", False)]:
            with self.subTest(text=text, disabled=disabled):
                self.assertFalse(candidate_available(text, disabled))

    @patch.dict("os.environ", {"GMAIL_USERNAME": "sender@gmail.com", "GMAIL_APP_PASSWORD": "abcd efgh ijkl mnop"})
    @patch("check_stock.smtplib.SMTP_SSL")
    def test_email_destination_and_tls(self, smtp_class):
        send_email()
        self.assertEqual(smtp_class.call_args.args, ("smtp.gmail.com", 465))
        smtp = smtp_class.return_value
        smtp.login.assert_called_once_with("sender@gmail.com", "abcdefghijklmnop")
        message = smtp.send_message.call_args.args[0]
        self.assertEqual(message["To"], RECIPIENT)
        self.assertIn("1333421001", message.get_content())

    @patch.dict("os.environ", {"GMAIL_USERNAME": "sender@gmail.com", "GMAIL_APP_PASSWORD": "app-password"})
    @patch("check_stock.smtplib.SMTP_SSL")
    def test_test_email_clearly_reports_unavailable(self, smtp_class):
        send_email(test=True)
        smtp = smtp_class.return_value
        message = smtp.send_message.call_args.args[0]
        self.assertEqual(message["To"], RECIPIENT)
        self.assertEqual(message["Subject"], "TEST H&M: taglia XS esaurita")
        self.assertIn("XS risulta esaurita", message.get_content())
        self.assertNotIn("acquistabile", message.get_content())

    @patch.dict("os.environ", {"GMAIL_USERNAME": "sender@gmail.com", "GMAIL_APP_PASSWORD": "app-password"})
    @patch("check_stock.smtplib.SMTP")
    @patch("check_stock.smtplib.SMTP_SSL")
    def test_disconnected_login_uses_starttls_before_single_send(self, ssl_smtp, plain_smtp):
        ssl_smtp.return_value.login.side_effect = smtplib.SMTPServerDisconnected("closed")
        send_email(test=True)
        ssl_smtp.return_value.send_message.assert_not_called()
        ssl_smtp.return_value.close.assert_called_once()
        self.assertEqual(plain_smtp.call_args.args, ("smtp.gmail.com", 587))
        smtp = plain_smtp.return_value
        smtp.starttls.assert_called_once()
        self.assertEqual(smtp.ehlo.call_count, 2)
        smtp.login.assert_called_once_with("sender@gmail.com", "app-password")
        smtp.send_message.assert_called_once()

    @patch.dict("os.environ", {"GMAIL_USERNAME": "sender@gmail.com", "GMAIL_APP_PASSWORD": "app-password"})
    @patch("check_stock.smtplib.SMTP")
    @patch("check_stock.smtplib.SMTP_SSL")
    def test_authentication_rejection_does_not_retry(self, ssl_smtp, plain_smtp):
        ssl_smtp.return_value.login.side_effect = smtplib.SMTPAuthenticationError(535, b"Bad credentials")
        with self.assertRaisesRegex(RuntimeError, "rifiutato le credenziali"):
            send_email()
        plain_smtp.assert_not_called()

    @patch.dict("os.environ", {"GMAIL_USERNAME": "sender@gmail.com", "GMAIL_APP_PASSWORD": "app-password"})
    @patch("check_stock.smtplib.SMTP")
    @patch("check_stock.smtplib.SMTP_SSL")
    def test_disconnect_during_send_does_not_retry_delivery(self, ssl_smtp, plain_smtp):
        ssl_smtp.return_value.send_message.side_effect = smtplib.SMTPServerDisconnected("closed")
        with self.assertRaises(smtplib.SMTPServerDisconnected):
            send_email()
        ssl_smtp.return_value.send_message.assert_called_once()
        plain_smtp.assert_not_called()

    @patch("check_stock.send_email")
    @patch("check_stock.check_stock", return_value=False)
    def test_test_email_only_sent_when_explicitly_requested(self, check, send):
        with patch("sys.argv", ["check_stock.py", "--test-email"]):
            main()
        send.assert_called_once_with(test=True)
        send.reset_mock()
        with patch("sys.argv", ["check_stock.py"]):
            main()
        send.assert_not_called()

    @patch("check_stock.send_email")
    @patch("check_stock.check_stock")
    def test_dry_run_prevents_all_email(self, check, send):
        for available in (True, False):
            check.return_value = available
            with patch("sys.argv", ["check_stock.py", "--test-email", "--dry-run"]):
                main()
        send.assert_not_called()

    @patch("check_stock.send_email")
    @patch("check_stock.check_stock", side_effect=RuntimeError("H&M HTTP 403"))
    def test_failed_check_does_not_send_unavailable_test(self, check, send):
        with patch("sys.argv", ["check_stock.py", "--test-email"]):
            with self.assertRaises(RuntimeError):
                main()
        send.assert_not_called()

    @patch.dict("os.environ", {}, clear=True)
    def test_missing_credentials_fail(self):
        with self.assertRaises(RuntimeError):
            send_email()


if __name__ == "__main__":
    unittest.main()
