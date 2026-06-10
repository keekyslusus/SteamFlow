import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LIB_PATH = PROJECT_ROOT / "lib"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(LIB_PATH) not in sys.path:
    sys.path.insert(0, str(LIB_PATH))

from steamflow.util_currency import format_price, normalize_country_code


class CurrencyTests(unittest.TestCase):
    def test_normalize_country_code_preserves_iso_country_for_steam(self):
        self.assertEqual(normalize_country_code(" UZ "), "uz")
        self.assertEqual(normalize_country_code("DE"), "de")
        self.assertEqual(normalize_country_code("GB"), "gb")

    def test_normalize_country_code_migrates_legacy_values(self):
        self.assertEqual(normalize_country_code("uk"), "gb")
        self.assertIsNone(normalize_country_code("eu", default=None))

    def test_normalize_country_code_rejects_invalid_values(self):
        self.assertEqual(normalize_country_code("USA"), "us")
        self.assertEqual(normalize_country_code("12"), "us")

    def test_format_price_prefers_steam_formatted_value(self):
        self.assertEqual(
            format_price({"final": 599, "currency": "USD", "final_formatted": "$5.99"}),
            "$5.99",
        )

    def test_format_price_uses_plain_fallback_for_incomplete_response(self):
        self.assertEqual(format_price({"final": 599, "currency": "usd"}), "5.99 USD")
        self.assertEqual(format_price({"final": 599}), "5.99")


if __name__ == "__main__":
    unittest.main()
