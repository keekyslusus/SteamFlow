import json
import sys
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LIB_PATH = PROJECT_ROOT / "lib"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(LIB_PATH) not in sys.path:
    sys.path.insert(0, str(LIB_PATH))

from tests._pyflowlauncher_stub import install_pyflowlauncher_stub

install_pyflowlauncher_stub()

from steamflow.contextmenu import SteamContextMenuPlugin
from steamflow.feature_health import record_feature_failure
import main


class ContextMenuHarness(SteamContextMenuPlugin):
    def __init__(self, plugin_dir):
        self.plugin_dir = Path(plugin_dir)
        self._steam_path = None
        self.buy_icon = "buy"
        self.default_icon = "default"
        self.community_icon = "community"
        self.csrin_icon = "csrin"
        self.deals_icon = "deals"
        self.download_icon = "download"
        self.discussions_icon = "discussions"
        self.guides_icon = "guides"
        self.location_icon = "location"
        self.properties_icon = "properties"
        self.refund_icon = "refund"
        self.screenshot_icon = "screenshot"
        self.settings_icon = "settings"
        self.steamdb_icon = "steamdb"
        self.top_sellers_icon = "top-sellers"
        self.trash_icon = "trash"
        self.wishlist_icon = "wishlist"
        self.wishlist_add_icon = "wishlist-add"
        self.wishlist_remove_icon = "wishlist-remove"
        self.fetch_calls = []
        self.items = []
        self.started_mutation_workers = []
        self._settings = {"language": "English"}

    def add_item(self, **kwargs):
        self.items.append(kwargs)

    def fetch_app_details_metadata(self, app_id):
        self.fetch_calls.append(str(app_id))
        return {"type": "game", "is_free": False}

    def start_steam_wishlist_mutation_worker(self, steamid64, app_id, action):
        self.started_mutation_workers.append((steamid64, app_id, action))


class ContextMenuRefundTests(unittest.TestCase):
    def test_existing_refund_state_short_circuits_everything(self):
        with TemporaryDirectory() as temp_dir:
            plugin = ContextMenuHarness(temp_dir)

            refund_state = plugin.derive_refund_state(
                {"app_id": "1451940", "install_path": "C:/Games/Needy", "refund_state": "likely"}
            )

            self.assertEqual(refund_state, "likely")
            self.assertEqual(plugin.fetch_calls, [])

    def test_store_result_never_fetches_refund_metadata(self):
        with TemporaryDirectory() as temp_dir:
            plugin = ContextMenuHarness(temp_dir)

            refund_state = plugin.derive_refund_state({"app_id": "1451940", "playtime_minutes": 54})

            self.assertEqual(refund_state, "")
            self.assertEqual(plugin.fetch_calls, [])

    def test_games_over_two_hours_never_fetch_refund_metadata(self):
        with TemporaryDirectory() as temp_dir:
            plugin = ContextMenuHarness(temp_dir)

            refund_state = plugin.derive_refund_state(
                {"app_id": "1451940", "install_path": "C:/Games/Needy", "playtime_minutes": 200}
            )

            self.assertEqual(refund_state, "")
            self.assertEqual(plugin.fetch_calls, [])

    def test_missing_current_account_data_blocks_refund_derivation(self):
        with TemporaryDirectory() as temp_dir:
            plugin = ContextMenuHarness(temp_dir)

            refund_state = plugin.derive_refund_state(
                {
                    "app_id": "1451940",
                    "install_path": "C:/Games/Needy",
                    "playtime_minutes": 54,
                    "has_current_account_local_data": False,
                }
            )

            self.assertEqual(refund_state, "")
            self.assertEqual(plugin.fetch_calls, [])

    def test_local_game_uses_cached_app_details_without_network(self):
        with TemporaryDirectory() as temp_dir:
            cache_path = Path(temp_dir) / "cache_app_details" / "us" / "1451940.json"
            cache_path.parent.mkdir(parents=True)
            cache_path.write_text(
                json.dumps({"timestamp": time.time(), "success": True, "metadata": {"type": "game", "is_free": False}}),
                encoding="utf-8",
            )
            plugin = ContextMenuHarness(temp_dir)

            refund_state = plugin.derive_refund_state(
                {"app_id": "1451940", "install_path": "C:/Games/Needy", "playtime_minutes": 54}
            )

            self.assertEqual(refund_state, "likely")
            self.assertEqual(plugin.fetch_calls, [])

    def test_local_game_fetches_and_persists_app_details_on_cache_miss(self):
        with TemporaryDirectory() as temp_dir:
            plugin = ContextMenuHarness(temp_dir)

            refund_state = plugin.derive_refund_state(
                {"app_id": "1451940", "install_path": "C:/Games/Needy", "playtime_minutes": 54}
            )

            self.assertEqual(refund_state, "likely")
            self.assertEqual(plugin.fetch_calls, ["1451940"])
            cache_data = json.loads((Path(temp_dir) / "cache_app_details" / "us" / "1451940.json").read_text(encoding="utf-8"))
            self.assertTrue(cache_data["success"])

    def test_store_context_menu_adds_cart_entry(self):
        with TemporaryDirectory() as temp_dir:
            plugin = ContextMenuHarness(temp_dir)

            plugin.context_menu(
                {
                    "app_id": "1462040",
                    "name": "FINAL FANTASY VII REMAKE INTERGRADE",
                    "result_source": "store",
                    "store_type": "game",
                    "is_free": False,
                    "steamid64": "76561198000000000",
                }
            )

            cart_items = [item for item in plugin.items if item["title"] == "Store: Add to Steam Cart"]
            self.assertEqual(len(cart_items), 1)
            self.assertEqual(cart_items[0]["method"], "add_to_steam_cart")
            self.assertEqual(cart_items[0]["parameters"], ["1462040", "76561198000000000"])

    def test_store_context_menu_uses_configured_language(self):
        with TemporaryDirectory() as temp_dir:
            plugin = ContextMenuHarness(temp_dir)
            plugin._settings = {"language": "Russian"}

            plugin.context_menu(
                {
                    "app_id": "1462040",
                    "name": "FINAL FANTASY VII REMAKE INTERGRADE",
                    "result_source": "store",
                    "store_type": "game",
                    "is_free": False,
                    "steamid64": "76561198000000000",
                }
            )

            titles = [item["title"] for item in plugin.items]
            self.assertIn("Магазин: добавить в корзину Steam", titles)
            self.assertIn("Магазин: открыть в Steam", titles)

    def test_steam_client_context_menu_uses_configured_language(self):
        with TemporaryDirectory() as temp_dir:
            plugin = ContextMenuHarness(temp_dir)
            plugin._settings = {"language": "Russian"}

            plugin.context_menu({"menu": "steam_client", "name": "Steam"})

            titles = [item["title"] for item in plugin.items]
            self.assertIn("Steam: открыть библиотеку", titles)
            self.assertIn("Магазин: открыть список желаемого", titles)

    def test_local_context_menu_does_not_add_cart_entry(self):
        with TemporaryDirectory() as temp_dir:
            plugin = ContextMenuHarness(temp_dir)

            plugin.context_menu(
                {
                    "app_id": "1451940",
                    "name": "NEEDY GIRL OVERDOSE",
                    "install_path": "C:/Games/Needy",
                }
            )

            titles = [item["title"] for item in plugin.items]
            self.assertNotIn("Store: Add to Steam Cart", titles)

    def test_store_context_menu_adds_wishlist_entry_for_eligible_game(self):
        with TemporaryDirectory() as temp_dir:
            plugin = ContextMenuHarness(temp_dir)

            plugin.context_menu(
                {
                    "app_id": "1462040",
                    "name": "FINAL FANTASY VII REMAKE INTERGRADE",
                    "result_source": "store",
                    "store_type": "game",
                    "is_free": False,
                    "is_wishlisted": False,
                    "steamid64": "76561198000000000",
                }
            )

            wishlist_items = [item for item in plugin.items if item["title"] == "Store: Add to Wishlist"]
            self.assertEqual(len(wishlist_items), 1)
            self.assertEqual(wishlist_items[0]["method"], "add_to_steam_wishlist")
            self.assertEqual(wishlist_items[0]["parameters"], ["1462040", "76561198000000000"])
            self.assertEqual(wishlist_items[0]["icon"], "wishlist-add")

    def test_store_context_menu_allows_wishlist_entry_for_coming_soon_game(self):
        with TemporaryDirectory() as temp_dir:
            plugin = ContextMenuHarness(temp_dir)

            plugin.context_menu(
                {
                    "app_id": "1462040",
                    "name": "FINAL FANTASY VII REMAKE INTERGRADE",
                    "result_source": "store",
                    "store_type": "game",
                    "coming_soon": True,
                    "is_free": False,
                    "is_wishlisted": False,
                    "steamid64": "76561198000000000",
                }
            )

            titles = [item["title"] for item in plugin.items]
            self.assertIn("Store: Add to Wishlist", titles)

    def test_store_context_menu_hides_wishlist_entry_for_owned_and_wishlisted_games(self):
        cases = [
            {"is_owned": True, "is_free": False, "is_wishlisted": False},
            {"is_owned": False, "is_free": False, "is_wishlisted": True},
        ]
        for data in cases:
            with self.subTest(data=data), TemporaryDirectory() as temp_dir:
                plugin = ContextMenuHarness(temp_dir)

                plugin.context_menu(
                    {
                        "app_id": "1462040",
                        "name": "FINAL FANTASY VII REMAKE INTERGRADE",
                        "result_source": "store",
                        "store_type": "game",
                        **data,
                    }
                )

                titles = [item["title"] for item in plugin.items]
                self.assertNotIn("Store: Add to Wishlist", titles)

    def test_store_context_menu_allows_wishlist_entry_for_free_game(self):
        with TemporaryDirectory() as temp_dir:
            plugin = ContextMenuHarness(temp_dir)

            plugin.context_menu(
                {
                    "app_id": "570",
                    "name": "Dota 2",
                    "result_source": "store",
                    "store_type": "game",
                    "is_free": True,
                    "is_wishlisted": False,
                    "steamid64": "76561198000000000",
                }
            )

            titles = [item["title"] for item in plugin.items]
            self.assertIn("Store: Add to Wishlist", titles)
            self.assertNotIn("Store: Add to Steam Cart", titles)

    def test_store_collection_context_menu_adds_cart_and_wishlist_entries(self):
        with TemporaryDirectory() as temp_dir:
            plugin = ContextMenuHarness(temp_dir)

            plugin.context_menu(
                {
                    "app_id": "1462040",
                    "name": "FINAL FANTASY VII REMAKE INTERGRADE",
                    "result_source": "top_sellers",
                    "store_type": "game",
                    "is_free": False,
                    "is_wishlisted": False,
                    "steamid64": "76561198000000000",
                }
            )

            titles = [item["title"] for item in plugin.items]
            self.assertIn("Store: Add to Wishlist", titles)
            self.assertIn("Store: Add to Steam Cart", titles)

    def test_store_context_menu_hides_wishlist_entries_when_api_key_is_unavailable(self):
        with TemporaryDirectory() as temp_dir:
            plugin = ContextMenuHarness(temp_dir)

            plugin.context_menu(
                {
                    "app_id": "1462040",
                    "name": "FINAL FANTASY VII REMAKE INTERGRADE",
                    "result_source": "top_sellers",
                    "store_type": "game",
                    "is_free": False,
                    "is_wishlisted": False,
                    "steamid64": "76561198000000000",
                    "wishlist_actions_enabled": False,
                }
            )

            titles = [item["title"] for item in plugin.items]
            self.assertNotIn("Store: Add to Wishlist", titles)
            self.assertIn("Store: Add to Steam Cart", titles)

    def test_wishlist_context_menu_hides_remove_when_api_key_is_unavailable(self):
        with TemporaryDirectory() as temp_dir:
            plugin = ContextMenuHarness(temp_dir)

            plugin.context_menu(
                {
                    "app_id": "1462040",
                    "name": "FINAL FANTASY VII REMAKE INTERGRADE",
                    "result_source": "wishlist",
                    "store_type": "game",
                    "is_free": False,
                    "steamid64": "76561198000000000",
                    "wishlist_actions_enabled": False,
                }
            )

            titles = [item["title"] for item in plugin.items]
            self.assertNotIn("Store: Remove from Wishlist", titles)
            self.assertIn("Store: Add to Steam Cart", titles)

    def test_wishlist_context_menu_adds_remove_wishlist_entry(self):
        with TemporaryDirectory() as temp_dir:
            plugin = ContextMenuHarness(temp_dir)

            plugin.context_menu(
                {
                    "app_id": "1462040",
                    "name": "FINAL FANTASY VII REMAKE INTERGRADE",
                    "result_source": "wishlist",
                    "store_type": "game",
                    "is_free": False,
                    "steamid64": "76561198000000000",
                }
            )

            titles = [item["title"] for item in plugin.items]
            self.assertIn("Store: Remove from Wishlist", titles)
            self.assertNotIn("Store: Add to Wishlist", titles)
            remove_item = next(item for item in plugin.items if item["title"] == "Store: Remove from Wishlist")
            self.assertEqual(remove_item["icon"], "wishlist-remove")

    def test_lightweight_wishlist_action_starts_mutation_worker(self):
        with TemporaryDirectory() as temp_dir:
            plugin = ContextMenuHarness(temp_dir)

            message = plugin.add_to_steam_wishlist("1462040", "76561198000000000")

            self.assertEqual(message, "Adding App ID 1462040 to Steam wishlist")
            self.assertEqual(
                plugin.started_mutation_workers,
                [("76561198000000000", "1462040", "add")],
            )

    def test_wishlist_actions_use_full_plugin_for_cache_aware_toasts(self):
        original_argv = sys.argv[:]
        try:
            sys.argv = ["main.py", json.dumps({"method": "add_to_steam_wishlist"})]

            plugin_class = main.get_plugin_class()

            self.assertNotEqual(plugin_class.__name__, "SteamContextMenuPlugin")
        finally:
            sys.argv = original_argv

    def test_store_context_menu_hides_cart_entry_when_cart_feature_disabled(self):
        with TemporaryDirectory() as temp_dir:
            plugin = ContextMenuHarness(temp_dir)
            cache_file = Path(temp_dir) / "cache_feature_health.json"
            for offset in range(3):
                record_feature_failure(cache_file, "steam_cart", f"rejected {offset}", reason="cart_rejected")

            plugin.context_menu(
                {
                    "app_id": "1462040",
                    "name": "FINAL FANTASY VII REMAKE INTERGRADE",
                    "result_source": "store",
                    "store_type": "game",
                    "is_free": False,
                    "steamid64": "76561198000000000",
                }
            )

            titles = [item["title"] for item in plugin.items]
            self.assertNotIn("Store: Add to Steam Cart", titles)

    def test_store_context_menu_hides_cart_entry_when_token_feature_disabled(self):
        with TemporaryDirectory() as temp_dir:
            plugin = ContextMenuHarness(temp_dir)
            cache_file = Path(temp_dir) / "cache_feature_health.json"
            for offset in range(3):
                record_feature_failure(cache_file, "steam_session_token", f"missing {offset}", reason="token_not_found")

            plugin.context_menu(
                {
                    "app_id": "1462040",
                    "name": "FINAL FANTASY VII REMAKE INTERGRADE",
                    "result_source": "store",
                    "store_type": "game",
                    "is_free": False,
                    "steamid64": "76561198000000000",
                }
            )

            titles = [item["title"] for item in plugin.items]
            self.assertNotIn("Store: Add to Steam Cart", titles)

    def test_store_context_menu_hides_wishlist_entry_when_wishlist_feature_disabled(self):
        with TemporaryDirectory() as temp_dir:
            plugin = ContextMenuHarness(temp_dir)
            cache_file = Path(temp_dir) / "cache_feature_health.json"
            for offset in range(3):
                record_feature_failure(cache_file, "steam_wishlist", f"rejected {offset}", reason="wishlist_rejected")

            plugin.context_menu(
                {
                    "app_id": "1462040",
                    "name": "FINAL FANTASY VII REMAKE INTERGRADE",
                    "result_source": "store",
                    "store_type": "game",
                    "is_free": False,
                    "steamid64": "76561198000000000",
                }
            )

            titles = [item["title"] for item in plugin.items]
            self.assertNotIn("Store: Add to Wishlist", titles)


if __name__ == "__main__":
    unittest.main()
