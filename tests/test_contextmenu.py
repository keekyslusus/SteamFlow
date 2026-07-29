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
        self.chat_icon = "chat"
        self.default_icon = "default"
        self.community_icon = "community"
        self.csrin_icon = "csrin"
        self.deals_icon = "deals"
        self.download_icon = "download"
        self.discussions_icon = "discussions"
        self.guides_icon = "guides"
        self.friends_icon = "friends"
        self.join_party_icon = "join-party"
        self.location_icon = "location"
        self.properties_icon = "properties"
        self.refund_icon = "refund"
        self.screenshot_icon = "screenshot"
        self.settings_icon = "settings"
        self.steamdb_icon = "steamdb"
        self.top_sellers_icon = "top-sellers"
        self.trade_icon = "trade"
        self.trash_icon = "trash"
        self.wishlist_icon = "wishlist"
        self.wishlist_add_icon = "wishlist-add"
        self.wishlist_remove_icon = "wishlist-remove"
        self.fetch_calls = []
        self.items = []
        self.started_mutation_workers = []
        self.join_candidates_by_app = {}
        self.join_candidate_calls = []
        self._settings = {"language": "English"}

    def add_item(self, **kwargs):
        self.items.append(kwargs)

    def fetch_app_details_metadata(self, app_id):
        self.fetch_calls.append(str(app_id))
        return {"type": "game", "is_free": False}

    def start_steam_wishlist_mutation_worker(self, steamid64, app_id, action):
        self.started_mutation_workers.append((steamid64, app_id, action))

    def get_joinable_friends_for_app(
        self,
        app_id,
        only_steamid64=None,
        force_refresh=False,
    ):
        self.join_candidate_calls.append(
            (str(app_id), only_steamid64, force_refresh)
        )
        candidates = list(self.join_candidates_by_app.get(str(app_id), []))
        if only_steamid64:
            candidates = [
                candidate
                for candidate in candidates
                if candidate["steamid64"] == str(only_steamid64)
            ]
        return candidates


class ContextMenuRefundTests(unittest.TestCase):
    def test_friend_context_menu_has_chat_profile_and_current_game(self):
        with TemporaryDirectory() as temp_dir:
            plugin = ContextMenuHarness(temp_dir)

            plugin.context_menu(
                {
                    "menu": "friend",
                    "steamid64": "76561199268740725",
                    "name": "Alice",
                    "gameid": "570",
                    "game_name": "Dota 2",
                }
            )

            self.assertEqual(
                [item["method"] for item in plugin.items],
                [
                    "open_steam_friend_chat",
                    "open_steam_friend_profile",
                    "open_steam_friend_trade_offer",
                    "open_steam_friend_game",
                ],
            )
            self.assertEqual(plugin.items[0]["parameters"], ["76561199268740725"])
            self.assertEqual(plugin.items[0]["icon"], "chat")
            self.assertEqual(plugin.items[2]["icon"], "trade")
            self.assertEqual(plugin.items[3]["subtitle"], "Open the Steam store page for Dota 2")

    def test_friend_context_menu_prepends_join_when_session_is_joinable(self):
        with TemporaryDirectory() as temp_dir:
            plugin = ContextMenuHarness(temp_dir)
            plugin.join_candidates_by_app["570"] = [
                {
                    "steamid64": "76561199268740725",
                    "name": "Alice",
                    "app_id": "570",
                }
            ]

            plugin.context_menu(
                {
                    "menu": "friend",
                    "steamid64": "76561199268740725",
                    "name": "Alice",
                    "gameid": "570",
                    "game_name": "Dota 2",
                }
            )

            self.assertEqual(plugin.items[0]["method"], "join_steam_friend_game")
            self.assertEqual(plugin.items[0]["title"], "Friend: Join Alice's Game")
            self.assertEqual(
                plugin.items[0]["parameters"],
                ["76561199268740725", "570"],
            )
            self.assertEqual(plugin.items[0]["icon"], "join-party")

    def test_home_game_context_menu_lists_each_joinable_friend(self):
        with TemporaryDirectory() as temp_dir:
            plugin = ContextMenuHarness(temp_dir)
            plugin.join_candidates_by_app["570"] = [
                {
                    "steamid64": "76561199268740725",
                    "name": "Alice",
                    "app_id": "570",
                },
                {
                    "steamid64": "76561198000000000",
                    "name": "Bob",
                    "app_id": "570",
                },
            ]

            plugin.context_menu(
                {
                    "app_id": "570",
                    "name": "Dota 2",
                    "install_path": "C:/Games/Dota 2",
                    "is_owned": True,
                    "friends_playing_count": 2,
                }
            )

            join_items = [
                item
                for item in plugin.items
                if item["method"] == "join_steam_friend_game"
            ]
            self.assertEqual(
                [item["title"] for item in join_items],
                ["Friend: Join Alice's Game", "Friend: Join Bob's Game"],
            )

    def test_home_game_context_menu_skips_join_when_no_friend_is_playing(self):
        with TemporaryDirectory() as temp_dir:
            plugin = ContextMenuHarness(temp_dir)

            plugin.context_menu(
                {
                    "app_id": "570",
                    "name": "Dota 2",
                    "install_path": "C:/Games/Dota 2",
                    "is_owned": True,
                    "friends_playing_count": 0,
                }
            )

            self.assertEqual(plugin.join_candidate_calls, [])
            self.assertNotIn(
                "join_steam_friend_game",
                [item["method"] for item in plugin.items],
            )

    def test_home_free_game_context_menu_uses_current_account_local_data(self):
        with TemporaryDirectory() as temp_dir:
            plugin = ContextMenuHarness(temp_dir)
            plugin.join_candidates_by_app["570"] = [
                {
                    "steamid64": "76561199268740725",
                    "name": "Alice",
                    "app_id": "570",
                }
            ]

            plugin.context_menu(
                {
                    "app_id": "570",
                    "name": "Dota 2",
                    "install_path": "C:/Games/Dota 2",
                    "is_owned": False,
                    "has_current_account_local_data": True,
                    "friends_playing_count": 1,
                }
            )

            self.assertEqual(plugin.join_candidate_calls, [("570", None, False)])
            self.assertEqual(plugin.items[0]["method"], "join_steam_friend_game")

    def test_home_game_context_menu_skips_join_check_without_install(self):
        with TemporaryDirectory() as temp_dir:
            plugin = ContextMenuHarness(temp_dir)

            plugin.context_menu(
                {
                    "app_id": "570",
                    "name": "Dota 2",
                    "install_path": None,
                    "is_owned": True,
                }
            )

            self.assertEqual(plugin.join_candidate_calls, [])
            self.assertNotIn(
                "join_steam_friend_game",
                [item["method"] for item in plugin.items],
            )

    def test_home_installed_game_delegates_ownership_verification(self):
        with TemporaryDirectory() as temp_dir:
            plugin = ContextMenuHarness(temp_dir)

            plugin.context_menu(
                {
                    "app_id": "1782210",
                    "name": "Crab Game",
                    "install_path": "C:/Games/Crab Game",
                    "is_owned": False,
                    "has_current_account_local_data": False,
                    "friends_playing_count": 1,
                }
            )

            self.assertEqual(
                plugin.join_candidate_calls,
                [("1782210", None, False)],
            )

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
            self.assertEqual(
                cart_items[0]["parameters"],
                [
                    "1462040",
                    "76561198000000000",
                    "FINAL FANTASY VII REMAKE INTERGRADE",
                ],
            )

    def test_store_additional_content_context_menu_hides_community_links(self):
        cases = [
            ("12345", "Bonus Content", "dlc"),
            ("3514130", "NieR:Automata Original Soundtrack", "music"),
            ("67890", "Legacy Soundtrack Type", "soundtrack"),
        ]
        for app_id, name, store_type in cases:
            with self.subTest(store_type=store_type), TemporaryDirectory() as temp_dir:
                plugin = ContextMenuHarness(temp_dir)

                plugin.context_menu(
                    {
                        "app_id": app_id,
                        "name": name,
                        "result_source": "store",
                        "store_type": store_type,
                    }
                )

                titles = [item["title"] for item in plugin.items]
                self.assertNotIn("Community: Open Guides", titles)
                self.assertNotIn("Community: Open Discussions", titles)
                self.assertIn("Store: Open in Steam", titles)

    def test_store_context_menu_ignores_disabled_language_setting(self):
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
            self.assertIn("Store: Add to Steam Cart", titles)
            self.assertIn("Store: Open in Steam", titles)

    def test_steam_client_context_menu_ignores_disabled_language_setting(self):
        with TemporaryDirectory() as temp_dir:
            plugin = ContextMenuHarness(temp_dir)
            plugin._settings = {"language": "Russian"}

            plugin.context_menu({"menu": "steam_client", "name": "Steam"})

            titles = [item["title"] for item in plugin.items]
            self.assertIn("Steam: Open Library", titles)
            self.assertIn("Store: Open Wishlist", titles)

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
            self.assertEqual(
                wishlist_items[0]["parameters"],
                [
                    "1462040",
                    "76561198000000000",
                    "FINAL FANTASY VII REMAKE INTERGRADE",
                ],
            )
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

    def test_join_action_uses_lightweight_context_plugin(self):
        original_argv = sys.argv[:]
        try:
            sys.argv = ["main.py", json.dumps({"method": "join_steam_friend_game"})]

            plugin_class = main.get_plugin_class()

            self.assertEqual(plugin_class.__name__, "SteamContextMenuPlugin")
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
