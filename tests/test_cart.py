import base64
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LIB_PATH = PROJECT_ROOT / "lib"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(LIB_PATH) not in sys.path:
    sys.path.insert(0, str(LIB_PATH))

from steamflow.cart import (
    STEAM_CART_COUNTRY_CODE,
    STEAM_CART_CURRENCY_CODE,
    SteamPluginCartMixin,
    build_add_packages_request,
    build_create_shopping_cart_request,
    parse_create_shopping_cart_response,
    select_cart_package_from_app_details,
)


class CartHarness(SteamPluginCartMixin):
    def __init__(self, secure_settings_dir):
        self.plugin_dir = PROJECT_ROOT
        self.secure_settings_dir = Path(secure_settings_dir)
        self.settings_path = str(self.secure_settings_dir / "Settings.json")
        self.active_steamid64 = "76561198000000000"
        self.logged_exceptions = []
        self.enabled_features = {}

    def get_active_steam_user_steamid64(self):
        return self.active_steamid64

    def log_exception(self, message):
        self.logged_exceptions.append(message)

    def feature_enabled(self, name):
        return self.enabled_features.get(str(name), True)


class CartProtobufTests(unittest.TestCase):
    def test_create_shopping_cart_request_uses_fixed64_steamid(self):
        encoded = build_create_shopping_cart_request("72623859790382856")

        self.assertEqual(base64.b64decode(encoded), b"\x09\x08\x07\x06\x05\x04\x03\x02\x01")

    def test_parse_create_shopping_cart_response_reads_gidshoppingcart(self):
        response = b"\x08\x95\x9a\xef\x3a"

        self.assertEqual(parse_create_shopping_cart_response(response), "123456789")

    def test_add_packages_request_contains_package_price_and_country(self):
        encoded = build_add_packages_request(
            gidshoppingcart=123,
            packageid=514802,
            amount_cents=1999,
            browserid=456,
        )
        raw = base64.b64decode(encoded)

        self.assertIn(b"\x08{", raw)
        self.assertIn(b"\x10\xc8\x03", raw)
        self.assertIn(b"\x08\xf2\xb5\x1f", raw)
        self.assertIn(b"\x08\xcf\x0f", raw)
        self.assertIn(b"\x10\x01", raw)
        self.assertIn(b"\x2a\x02US", raw)


class CartPackageSelectionTests(unittest.TestCase):
    def test_select_cart_package_prefers_default_package_group_sub(self):
        package = select_cart_package_from_app_details(
            {
                "is_free": False,
                "price_overview": {"final": 2999, "currency": "USD"},
                "packages": [999999],
                "package_groups": [
                    {
                        "name": "default",
                        "subs": [
                            {
                                "packageid": 514802,
                                "price_in_cents_with_discount": 1999,
                            }
                        ],
                    }
                ],
            }
        )

        self.assertEqual(
            package,
            {
                "packageid": 514802,
                "amount_cents": 1999,
                "currency_code": STEAM_CART_CURRENCY_CODE,
                "store_country_code": STEAM_CART_COUNTRY_CODE,
            },
        )

    def test_select_cart_package_rejects_free_apps(self):
        with self.assertRaises(ValueError):
            select_cart_package_from_app_details({"is_free": True})


class CartActionTests(unittest.TestCase):
    def test_add_to_steam_cart_starts_worker(self):
        with TemporaryDirectory() as temp_dir:
            harness = CartHarness(temp_dir)

            with patch.object(subprocess, "Popen") as mocked_popen:
                result = harness.add_to_steam_cart("1462040")

        self.assertEqual(result, "Adding App ID 1462040 to Steam cart")
        popen_args = mocked_popen.call_args[0][0]
        self.assertEqual(popen_args[1], str(PROJECT_ROOT / "steam_cart_worker.py"))
        self.assertEqual(popen_args[-2:], ["76561198000000000", "1462040"])

    def test_add_to_steam_cart_accepts_context_steamid(self):
        with TemporaryDirectory() as temp_dir:
            harness = CartHarness(temp_dir)
            harness.active_steamid64 = ""

            with patch.object(subprocess, "Popen") as mocked_popen:
                result = harness.add_to_steam_cart("1462040", "76561198000000001")

        self.assertEqual(result, "Adding App ID 1462040 to Steam cart")
        popen_args = mocked_popen.call_args[0][0]
        self.assertEqual(popen_args[-2:], ["76561198000000001", "1462040"])

    def test_add_to_steam_cart_returns_unavailable_when_cart_feature_disabled(self):
        with TemporaryDirectory() as temp_dir:
            harness = CartHarness(temp_dir)
            harness.enabled_features["steam_cart"] = False

            with patch.object(subprocess, "Popen") as mocked_popen:
                result = harness.add_to_steam_cart("1462040")

        self.assertEqual(result, "Steam cart integration is temporarily unavailable")
        mocked_popen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
