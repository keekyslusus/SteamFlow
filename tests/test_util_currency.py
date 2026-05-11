import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from steamflow import util_currency


class CurrencyFormatTests(unittest.TestCase):
    def test_formats_representative_steam_prices(self):
        cases = [
            (123456, "us", "$1,234.56"),
            (123456, "eu", "1.234,56 €"),
            (123400, "jp", "¥123,400"),
            (4949900, "id", "Rp 49 499"),
            (240000, "kz", "2 400 ₸"),
        ]

        for price_int, country_code, expected in cases:
            with self.subTest(country_code=country_code):
                self.assertEqual(util_currency.format_price(price_int, country_code), expected)

    def test_free_and_unknown_country_fallback(self):
        self.assertEqual(util_currency.format_price(0, "us"), "Free")
        self.assertEqual(util_currency.format_price(999, "unknown"), "$9.99")


if __name__ == "__main__":
    unittest.main()
