import json
import sys
import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LIB_PATH = PROJECT_ROOT / "lib"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(LIB_PATH) not in sys.path:
    sys.path.insert(0, str(LIB_PATH))

from tests._flox_stub import install_flox_stub

install_flox_stub(include_clipboard=True)

from steamflow.storage import SteamPluginStorageMixin
from steamflow.ui_commands import SteamPluginUICommandsMixin
from steamflow.wishlist import SteamPluginWishlistMixin


class WishlistHarness(SteamPluginWishlistMixin, SteamPluginStorageMixin, SteamPluginUICommandsMixin):
    OWNED_ICON = "owned-icon"
    WISHLIST_CACHE_TTL_SECONDS = 15 * 60
    WISHLIST_COLD_DETAIL_FETCH_LIMIT = 8
    MAX_WISHLIST_RESULTS = 15

    def __init__(self, temp_dir):
        self.state_lock = threading.RLock()
        self.user_keyword = "steam"
        self.id = "A7F3C4E16B8D4B5AB2D7139EEC8FA0B4"
        self.app_settings = {"PluginSettings": {"Plugins": {}}}
        self.wishlist_cache_file = Path(temp_dir) / "cache_wishlist.json"
        self.wishlist_cache_loaded = False
        self.wishlist_items = []
        self.wishlist_last_attempt = 0
        self.wishlist_last_sync = 0
        self.wishlist_steamid64 = None
        self.pending_wishlist_refresh = False
        self.active_steamid64 = "76561198000000000"
        self.owned_api_key_present = True
        self.key_bound_to_active_user = True
        self.fetch_calls = []
        self.scheduled_refreshes = []
        self.started_workers = []
        self.metadata_by_app_id = {}

    def _read_json_file(self, path, error_message):
        with open(path, "r", encoding="utf-8") as file_obj:
            return json.load(file_obj)

    def _write_json_file(self, path, payload, error_message, indent=None):
        with open(path, "w", encoding="utf-8") as file_obj:
            json.dump(payload, file_obj, indent=indent)
        return True

    def normalize_steam_web_api_key(self, value):
        return "A" * 32

    def has_owned_api_key(self):
        return self.owned_api_key_present

    def is_owned_api_key_bound_to_active_user(self):
        return self.key_bound_to_active_user

    def get_owned_api_key(self):
        return "A" * 32

    def get_active_steam_user_steamid64(self):
        return self.active_steamid64

    def fetch_wishlist_items_from_api(self, api_key, steamid64, timeout=3):
        self.fetch_calls.append((api_key, steamid64, timeout))
        return [
            {"appid": "20", "date_added": 200, "priority": 0},
            {"appid": "10", "date_added": 100, "priority": 0},
        ]

    def schedule_wishlist_refresh(self, force=False):
        self.scheduled_refreshes.append(force)

    def start_wishlist_hydration_worker(self, wishlist_items):
        self.started_workers.append([item["appid"] for item in wishlist_items])

    def build_result(self, title, subtitle, icon_path=None, action=None, context_data=None, **extra_fields):
        result = {
            "Title": title,
            "SubTitle": subtitle,
            "IcoPath": icon_path,
            "action": action,
            "ContextData": context_data,
        }
        result.update(extra_fields)
        return result

    def build_action(self, method, *parameters):
        return {"method": method, "parameters": list(parameters)}

    def build_plugin_query(self, *parts):
        plugin_settings = self.app_settings.get("PluginSettings", {}).get("Plugins", {}).get(self.id, {})
        keywords = plugin_settings.get("UserKeywords") or plugin_settings.get("ActionKeywords") or []
        if isinstance(keywords, list) and keywords:
            keyword = str(keywords[0] or "").strip() or str(self.user_keyword or "steam").strip()
        else:
            keyword = str(self.user_keyword or "steam").strip()
        suffix = " ".join(str(part).strip() for part in parts if str(part).strip())
        return f"{keyword} {suffix}".strip()

    def build_context_data(
        self,
        app_id=None,
        name=None,
        install_path=None,
        is_owned=None,
        refund_state=None,
        playtime_minutes=None,
        has_current_account_local_data=None,
    ):
        return {"app_id": app_id, "name": name}

    def get_app_details_metadata(self, app_id, allow_network_on_miss=True):
        return self.metadata_by_app_id.get(str(app_id))

    def process_game_data(self, game_data, allow_cold_metric_fetch=True):
        return {
            "Title": f"\U0001F6D2 {game_data['name']}",
            "SubTitle": "Open in Steam store",
            "IcoPath": "icon",
            "AppID": str(game_data["id"]),
        }

    def log_exception(self, message):
        return None


class WishlistTests(unittest.TestCase):
    def test_wishlist_query_alias_matches_expected_command(self):
        harness = WishlistHarness(".")

        self.assertTrue(harness.is_wishlist_query("wishlist"))
        self.assertTrue(harness.is_wishlist_query("wish list"))
        self.assertTrue(harness.is_wishlist_query("wishlist foo"))
        self.assertEqual(harness.get_wishlist_query_text("wishlist final fantasy"), "final fantasy")

    def test_load_wishlist_cache_restores_items(self):
        with TemporaryDirectory() as temp_dir:
            cache_path = Path(temp_dir) / "cache_wishlist.json"
            cache_path.write_text(
                json.dumps(
                    {
                        "timestamp": 123,
                        "steamid64": "76561198000000000",
                        "items": [{"appid": 20, "date_added": 200, "priority": 0}],
                    }
                ),
                encoding="utf-8",
            )
            harness = WishlistHarness(temp_dir)

            harness.load_wishlist_cache()

            self.assertTrue(harness.wishlist_cache_loaded)
            self.assertEqual(harness.wishlist_items[0]["appid"], "20")

    def test_build_wishlist_results_sorts_by_date_added_desc(self):
        with TemporaryDirectory() as temp_dir:
            harness = WishlistHarness(temp_dir)
            harness.metadata_by_app_id = {
                "10": {"name": "Older", "type": "game", "is_free": False, "platforms": {}, "has_price": False, "price": None},
                "20": {"name": "Newer", "type": "game", "is_free": False, "platforms": {}, "has_price": False, "price": None},
            }

            results = harness.build_wishlist_results()

            self.assertEqual(results[0]["Title"], "\U0001F6D2 Newer")
            self.assertEqual(results[1]["Title"], "\U0001F6D2 Older")

    def test_build_wishlist_results_adds_status_row_and_hides_placeholder_items(self):
        with TemporaryDirectory() as temp_dir:
            harness = WishlistHarness(temp_dir)
            harness.metadata_by_app_id = {
                "20": {"name": "Newer", "type": "game", "is_free": False, "platforms": {}, "has_price": False, "price": None},
            }

            results = harness.build_wishlist_results()

            self.assertEqual(results[0]["Title"], "Syncing Steam Wishlist")
            self.assertEqual(
                results[0]["action"],
                {"method": "open_my_steam_wishlist", "parameters": []},
            )
            self.assertEqual(results[1]["Title"], "\U0001F6D2 Newer")
            self.assertEqual(harness.started_workers, [["10"]])

    def test_build_wishlist_results_filters_loaded_titles_by_query(self):
        with TemporaryDirectory() as temp_dir:
            harness = WishlistHarness(temp_dir)
            harness.metadata_by_app_id = {
                "10": {"name": "Final Fantasy", "type": "game", "is_free": False, "platforms": {}, "has_price": False, "price": None},
                "20": {"name": "Portal", "type": "game", "is_free": False, "platforms": {}, "has_price": False, "price": None},
            }

            results = harness.build_wishlist_results("final")

            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]["Title"], "\U0001F6D2 Final Fantasy")

    def test_build_wishlist_results_returns_search_status_when_matches_are_still_loading(self):
        with TemporaryDirectory() as temp_dir:
            harness = WishlistHarness(temp_dir)

            results = harness.build_wishlist_results("final")

            self.assertEqual(results[0]["Title"], "Syncing Steam Wishlist For 'final'")

    def test_build_wishlist_results_uses_unavailable_result_without_api_key(self):
        with TemporaryDirectory() as temp_dir:
            harness = WishlistHarness(temp_dir)
            harness.owned_api_key_present = False

            results = harness.build_wishlist_results()

            self.assertEqual(results[0]["Title"], "Steam Wishlist Unavailable")
            self.assertIn("steam api", results[0]["SubTitle"].lower())
            self.assertEqual(
                results[0]["action"],
                {
                    "method": "change_query",
                    "parameters": ["steam api", True],
                    "dontHideAfterAction": True,
                },
            )

    def test_build_wishlist_results_uses_current_user_keyword_for_api_redirect(self):
        with TemporaryDirectory() as temp_dir:
            harness = WishlistHarness(temp_dir)
            harness.user_keyword = "st"
            harness.owned_api_key_present = False

            results = harness.build_wishlist_results()

            self.assertIn("`st api`", results[0]["SubTitle"])
            self.assertEqual(
                results[0]["action"],
                {
                    "method": "change_query",
                    "parameters": ["st api", True],
                    "dontHideAfterAction": True,
                },
            )

    def test_build_wishlist_results_prefers_action_keywords_from_flow_settings(self):
        with TemporaryDirectory() as temp_dir:
            harness = WishlistHarness(temp_dir)
            harness.user_keyword = "steam"
            harness.app_settings["PluginSettings"]["Plugins"][harness.id] = {"ActionKeywords": ["st"]}
            harness.owned_api_key_present = False

            results = harness.build_wishlist_results()

            self.assertIn("`st api`", results[0]["SubTitle"])
            self.assertEqual(results[0]["action"]["parameters"], ["st api", True])

    def test_build_wishlist_unavailable_result_without_active_account_has_no_redirect(self):
        with TemporaryDirectory() as temp_dir:
            harness = WishlistHarness(temp_dir)

            result = harness.build_wishlist_unavailable_result("No active Steam account found")

            self.assertIsNone(result["action"])

    def test_cached_wishlist_is_returned_and_stale_cache_schedules_refresh(self):
        with TemporaryDirectory() as temp_dir:
            harness = WishlistHarness(temp_dir)
            harness.wishlist_cache_loaded = True
            harness.wishlist_items = [{"appid": "10", "date_added": 100, "priority": 0}]
            harness.wishlist_steamid64 = harness.active_steamid64
            harness.wishlist_last_sync = 1

            items, error = harness.get_wishlist_items()

            self.assertIsNone(error)
            self.assertEqual(items[0]["appid"], "10")
            self.assertEqual(harness.scheduled_refreshes, [False])


if __name__ == "__main__":
    unittest.main()
