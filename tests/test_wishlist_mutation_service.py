import sys
import urllib.error
import unittest
from unittest.mock import patch
from pathlib import Path
from tempfile import TemporaryDirectory

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LIB_PATH = PROJECT_ROOT / "lib"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(LIB_PATH) not in sys.path:
    sys.path.insert(0, str(LIB_PATH))

from steamflow.wishlist_mutation_service import (
    ADD_TO_WISHLIST_URL,
    REMOVE_FROM_WISHLIST_URL,
    perform_wishlist_mutation,
    refresh_wishlist_token,
    start_steam_wishlist_mutation_worker_process,
    wishlist_mutation_url,
)


class WishlistMutationServiceTests(unittest.TestCase):
    def test_wishlist_mutation_url_resolves_supported_actions(self):
        self.assertEqual(wishlist_mutation_url("add"), ADD_TO_WISHLIST_URL)
        self.assertEqual(wishlist_mutation_url("remove"), REMOVE_FROM_WISHLIST_URL)
        with self.assertRaises(ValueError):
            wishlist_mutation_url("bad")

    def test_perform_wishlist_mutation_uses_cached_webapi_token(self):
        calls = []

        result = perform_wishlist_mutation(
            "secure",
            "76561198000000000",
            "570",
            "add",
            token_loader=lambda secure_dir, steamid64: "cached-token",
            token_refresher=lambda *_args, **_kwargs: "fresh-token",
            form_request=lambda url, token, app_id, token_field="webapi_token": (
                calls.append((url, token, app_id, token_field)) or ({"ok": True}, b"{}")
            ),
        )

        self.assertEqual(result, {"ok": True})
        self.assertEqual(calls, [(ADD_TO_WISHLIST_URL, "cached-token", "570", "access_token")])

    def test_perform_wishlist_mutation_falls_back_to_legacy_fields_before_refreshing_token(self):
        calls = []
        refreshed = []

        def form_request(url, token, app_id, token_field="webapi_token"):
            calls.append((token, token_field))
            if token_field == "access_token":
                raise urllib.error.HTTPError(url, 401, "Unauthorized", {}, None)
            return {"ok": True}, b"{}"

        result = perform_wishlist_mutation(
            "secure",
            "76561198000000000",
            "570",
            "add",
            token_loader=lambda secure_dir, steamid64: "cached-token",
            token_refresher=lambda *_args, **_kwargs: refreshed.append(True) or "fresh-token",
            form_request=form_request,
        )

        self.assertEqual(result, {"ok": True})
        self.assertEqual(calls, [("cached-token", "access_token"), ("cached-token", "webapi_token")])
        self.assertEqual(refreshed, [])

    def test_refresh_wishlist_token_uses_htmlcache_webapi_token_without_clientcomm_validation(self):
        calls = []

        class Provider:
            def __init__(self, secure_settings_dir, steamid64, logger=None):
                calls.append((secure_settings_dir, steamid64, logger))

            def refresh_from_steam_htmlcache(self, refresh_wait_seconds=0):
                calls.append(("refresh", refresh_wait_seconds))
                return "html-escaped-webapi-token"

        with patch("steamflow.wishlist_mutation_service.SteamSessionTokenProvider", Provider):
            token = refresh_wishlist_token("secure", "76561198000000000", logger="logger", refresh_wait_seconds=1)

        self.assertEqual(token, "html-escaped-webapi-token")
        self.assertEqual(calls[0], ("secure", "76561198000000000", "logger"))
        self.assertEqual(calls[1], ("refresh", 1))

    def test_worker_process_builds_expected_command(self):
        with TemporaryDirectory() as temp_dir:
            plugin_dir = Path(temp_dir)
            worker_script = plugin_dir / "steam_wishlist_mutation_worker.py"
            worker_script.write_text("", encoding="utf-8")
            calls = []

            start_steam_wishlist_mutation_worker_process(
                plugin_dir,
                Path(temp_dir) / "secure",
                "76561198000000000",
                "570",
                "remove",
                python_executable="python",
                popen=lambda *args, **kwargs: calls.append((args, kwargs)),
                platform="linux",
            )

            command = calls[0][0][0]
            self.assertEqual(
                command,
                [
                    "python",
                    str(worker_script),
                    str(Path(temp_dir) / "secure"),
                    "76561198000000000",
                    "570",
                    "remove",
                ],
            )
            self.assertTrue(calls[0][1]["start_new_session"])


if __name__ == "__main__":
    unittest.main()
