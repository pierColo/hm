import unittest
from unittest.mock import patch

from check_stock import RECIPIENT, candidate_available, send_email


class StockTests(unittest.TestCase):
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
        smtp = smtp_class.return_value.__enter__.return_value
        smtp.login.assert_called_once_with("sender@gmail.com", "abcdefghijklmnop")
        message = smtp.send_message.call_args.args[0]
        self.assertEqual(message["To"], RECIPIENT)
        self.assertIn("1333421001", message.get_content())

    @patch.dict("os.environ", {}, clear=True)
    def test_missing_credentials_fail(self):
        with self.assertRaises(RuntimeError):
            send_email()


if __name__ == "__main__":
    unittest.main()
