import sys
import threading
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import urllib3

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LIB_PATH = PROJECT_ROOT / "lib"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(LIB_PATH) not in sys.path:
    sys.path.insert(0, str(LIB_PATH))

from steamflow.store import SteamPluginStoreMixin


class StoreHarness(SteamPluginStoreMixin):
    urllib3 = urllib3

    def __init__(self, cache_dir, country_code="us"):
        self.app_details_cache_dir = Path(cache_dir)
        self.app_details_cache = {}
        self.search_cache = {}
        self.store_collection_cache = {}
        self.store_user_preferences_cache = {}
        self.secure_settings_dir = Path(cache_dir)
        self.state_lock = threading.RLock()
        self.country_code = country_code
        self.owned_app_ids = set()
        self.fetch_calls = []
        self.logged_exceptions = []
        self.logged_slow_calls = []

    def get_country_code(self):
        return self.country_code

    def should_show_prices(self):
        return True

    def get_steam_language(self):
        return "english"

    def get_blacklisted_app_ids(self):
        return set()

    def get_active_steam_user_steamid64(self):
        return None

    def cleanup_caches_if_needed(self):
        return None

    def _http_get(self, *_args, **_kwargs):
        raise AssertionError("Unexpected HTTP request")

    def log_exception(self, message):
        self.logged_exceptions.append(message)

    def log_slow_call(self, *args):
        self.logged_slow_calls.append(args)

    def fetch_app_details_metadata(self, app_id, timeout=1.5):
        self.fetch_calls.append(str(app_id))
        return {"name": "Portal", "price": {"final_formatted": "$9.99"}}

    def _update_metric_cache_entry(self, cache, key, **payload):
        cache[str(key)] = {"timestamp": time.time(), **payload}


class StoreTests(unittest.TestCase):
    def test_appdetails_cache_is_reused_for_matching_country(self):
        with TemporaryDirectory() as temp_dir:
            plugin = StoreHarness(temp_dir, country_code="uz")
            plugin.app_details_cache["400"] = {
                "timestamp": time.time(),
                "success": True,
                "country_code": "uz",
                "metadata": {"name": "Portal"},
            }

            metadata = plugin.get_app_details_metadata("400")

            self.assertEqual(metadata, {"name": "Portal"})
            self.assertEqual(plugin.fetch_calls, [])

    def test_appdetails_cache_is_refreshed_when_country_changes(self):
        with TemporaryDirectory() as temp_dir:
            plugin = StoreHarness(temp_dir, country_code="uz")
            plugin.app_details_cache["400"] = {
                "timestamp": time.time(),
                "success": True,
                "country_code": "us",
                "metadata": {"name": "Portal", "price": {"final_formatted": "$9.99"}},
            }

            metadata = plugin.get_app_details_metadata("400")

            self.assertEqual(metadata["name"], "Portal")
            self.assertEqual(plugin.fetch_calls, ["400"])
            self.assertEqual(plugin.app_details_cache["400"]["country_code"], "uz")

    def test_search_steam_api_caches_successful_network_result(self):
        with TemporaryDirectory() as temp_dir:
            plugin = StoreHarness(temp_dir, country_code="us")
            games = [{"id": 570, "name": "Dota 2"}]

            with patch("steamflow.store.fetch_store_search_games", return_value=games):
                result = plugin.search_steam_api("dota")

            self.assertEqual(result, {"games": games, "error": None})
            self.assertEqual(plugin.search_cache[("dota", "us")]["games"], games)
            self.assertEqual(plugin.logged_exceptions, [])

    def test_store_collection_uses_fresh_cache_without_network(self):
        with TemporaryDirectory() as temp_dir:
            plugin = StoreHarness(temp_dir, country_code="us")
            games = [{"id": 570, "name": "Dota 2"}]
            plugin.store_collection_cache[("specials", "us", "english")] = {
                "timestamp": time.time(),
                "games": games,
                "error": None,
            }

            result = plugin.get_store_collection_games("specials")

            self.assertEqual(result["games"], games)
            self.assertIsNone(result["error"])
            self.assertFalse(result["stale"])

    def test_store_collection_returns_stale_cache_when_refresh_fails(self):
        with TemporaryDirectory() as temp_dir:
            plugin = StoreHarness(temp_dir, country_code="us")
            games = [{"id": 570, "name": "Dota 2"}]
            plugin.store_collection_cache[("top_sellers", "us", "english")] = {
                "timestamp": time.time() - plugin.CONFIG.cache.store_top_sellers_ttl_seconds - 1,
                "games": games,
                "error": None,
            }

            with patch.object(plugin, "fetch_store_collection_games_by_name", side_effect=RuntimeError("nope")):
                result = plugin.get_store_collection_games("top_sellers")

            self.assertEqual(result["games"], games)
            self.assertTrue(result["stale"])
            self.assertTrue(result["error"])

    def test_store_collection_refresh_populates_sibling_collection_cache(self):
        with TemporaryDirectory() as temp_dir:
            plugin = StoreHarness(temp_dir, country_code="us")
            games_by_collection = {
                "specials": [{"id": 1, "name": "Deal"}],
                "top_sellers": [{"id": 2, "name": "Seller"}],
            }

            with patch.object(
                plugin,
                "fetch_store_collection_games_by_name",
                return_value=games_by_collection,
            ) as fetcher:
                deals = plugin.get_store_collection_games("specials")
                sellers = plugin.get_store_collection_games("top_sellers")

            self.assertEqual(deals["games"], games_by_collection["specials"])
            self.assertEqual(sellers["games"], games_by_collection["top_sellers"])
            self.assertEqual(fetcher.call_count, 1)

    def test_store_collection_fetch_uses_collection_limit_and_hides_owned_games(self):
        with TemporaryDirectory() as temp_dir:
            plugin = StoreHarness(temp_dir, country_code="us")
            plugin.owned_app_ids = {"570"}
            captured = {}

            def fake_fetcher(*_args, **kwargs):
                captured.update(kwargs)
                return {"specials": [], "top_sellers": []}

            with patch("steamflow.store.fetch_featured_collections_games", side_effect=fake_fetcher):
                plugin.fetch_store_collection_games_by_name()

            self.assertEqual(captured["max_results"], 10)
            self.assertIn("570", captured["blacklist"])


if __name__ == "__main__":
    unittest.main()
