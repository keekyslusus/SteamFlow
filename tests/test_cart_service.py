import json
import io
import sys
import urllib.error
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LIB_PATH = PROJECT_ROOT / "lib"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(LIB_PATH) not in sys.path:
    sys.path.insert(0, str(LIB_PATH))

from steamflow.cart_service import (
    add_package_to_shopping_cart,
    add_resolved_package_to_cart_once,
    create_shopping_cart,
    extract_cart_result_details,
    extract_gidshoppingcart,
    is_cart_auth_error,
    open_steam_cart,
    perform_add_to_cart,
    start_steam_cart_worker_process,
)


class CartServiceTests(unittest.TestCase):
    def test_extract_gidshoppingcart_prefers_json_payload_then_protobuf(self):
        self.assertEqual(extract_gidshoppingcart({"response": {"gidshoppingcart": "123"}}, b""), "123")
        self.assertEqual(extract_gidshoppingcart({}, b"\x08\x95\x9a\xef\x3a"), "123456789")

    def test_create_shopping_cart_raises_when_gid_is_missing(self):
        with self.assertRaisesRegex(RuntimeError, "shopping cart id"):
            create_shopping_cart(
                "token",
                "76561198000000000",
                form_request=lambda *_args, **_kwargs: ({}, b""),
            )

    def test_add_package_to_shopping_cart_rejects_result_details(self):
        self.assertEqual(extract_cart_result_details({"response": {"result_details": [8]}}), [8])
        with self.assertRaisesRegex(RuntimeError, "rejected"):
            add_package_to_shopping_cart(
                "token",
                "123",
                456,
                789,
                form_request=lambda *_args, **_kwargs: ({"response": {"result_details": [8]}}, b""),
            )

    def test_add_resolved_package_to_cart_once_calls_create_add_and_merge(self):
        calls = []
        package = {"packageid": 456, "amount_cents": 789}

        returned_package = add_resolved_package_to_cart_once(
            "token",
            "steamid",
            "app",
            package,
            cart_creator=lambda access_token, steamid64: calls.append(("create", access_token, steamid64)) or "cartid",
            package_adder=lambda access_token, cartid, packageid, amount: calls.append(("add", access_token, cartid, packageid, amount)),
            cart_merger=lambda access_token, cartid: calls.append(("merge", access_token, cartid)),
        )

        self.assertIs(returned_package, package)
        self.assertEqual(
            calls,
            [
                ("create", "token", "steamid"),
                ("add", "token", "cartid", 456, 789),
                ("merge", "token", "cartid"),
            ],
        )

    def test_is_cart_auth_error_detects_http_and_explicit_token_errors(self):
        auth_error = urllib.error.HTTPError("https://steam", 401, "Unauthorized", {}, io.BytesIO())

        try:
            self.assertTrue(is_cart_auth_error(auth_error))
        finally:
            auth_error.close()
        self.assertTrue(is_cart_auth_error(RuntimeError("invalid token for cart request")))
        self.assertFalse(is_cart_auth_error(RuntimeError("network timeout after merge")))

    def test_perform_add_to_cart_refreshes_token_after_confirmed_auth_error(self):
        calls = []
        deleted_tokens = []

        def package_adder(token, steamid64, app_id, package, logger=None):
            calls.append((token, steamid64, app_id, package))
            if token == "cached-token":
                raise urllib.error.HTTPError("https://steam", 401, "Unauthorized", {}, io.BytesIO())
            return package

        result = perform_add_to_cart(
            "secure",
            "steamid",
            "app",
            package_resolver=lambda app_id: {"packageid": 456, "amount_cents": 789},
            token_loader=lambda secure_dir, steamid64: "cached-token",
            token_refresher=lambda secure_dir, steamid64, logger=None: "fresh-token",
            token_deleter=lambda secure_dir, steamid64: deleted_tokens.append((secure_dir, steamid64)),
            package_adder=package_adder,
        )

        self.assertEqual(result, {"packageid": 456, "amount_cents": 789})
        self.assertEqual([call[0] for call in calls], ["cached-token", "fresh-token"])
        self.assertEqual(deleted_tokens, [("secure", "steamid")])

    def test_perform_add_to_cart_does_not_retry_ambiguous_cart_error(self):
        calls = []
        deleted_tokens = []

        def package_adder(token, steamid64, app_id, package, logger=None):
            calls.append((token, steamid64, app_id, package))
            raise RuntimeError("network timeout after merge")

        with self.assertRaisesRegex(RuntimeError, "network timeout"):
            perform_add_to_cart(
                "secure",
                "steamid",
                "app",
                package_resolver=lambda app_id: {"packageid": 456, "amount_cents": 789},
                token_loader=lambda secure_dir, steamid64: "cached-token",
                token_refresher=lambda secure_dir, steamid64, logger=None: "fresh-token",
                token_deleter=lambda secure_dir, steamid64: deleted_tokens.append((secure_dir, steamid64)),
                package_adder=package_adder,
            )

        self.assertEqual([call[0] for call in calls], ["cached-token"])
        self.assertEqual(deleted_tokens, [])

    def test_start_steam_cart_worker_process_builds_hidden_worker_command(self):
        with TemporaryDirectory() as temp_dir:
            plugin_dir = Path(temp_dir)
            worker_script = plugin_dir / "steam_cart_worker.py"
            worker_script.write_text("", encoding="utf-8")
            secure_dir = plugin_dir / "secure"
            calls = []

            start_steam_cart_worker_process(
                plugin_dir,
                secure_dir,
                "steamid",
                "app",
                python_executable="python",
                popen=lambda *args, **kwargs: calls.append((args, kwargs)),
                platform="linux",
            )

        command = calls[0][0][0]
        kwargs = calls[0][1]
        self.assertEqual(command, ["python", str(worker_script), str(secure_dir), "steamid", "app"])
        self.assertTrue(kwargs["start_new_session"])

    def test_open_steam_cart_uses_steam_cart_uri(self):
        opened = []

        open_steam_cart(startfile=opened.append)

        self.assertEqual(opened, ["steam://openurl/https://store.steampowered.com/cart"])


if __name__ == "__main__":
    unittest.main()
