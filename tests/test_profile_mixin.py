import sys
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LIB_PATH = PROJECT_ROOT / "lib"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(LIB_PATH) not in sys.path:
    sys.path.insert(0, str(LIB_PATH))

from steamflow.profile import SteamPluginProfileMixin


class TimeoutError(Exception):
    pass


class HTTPError(Exception):
    pass


class ProfileHarness(SteamPluginProfileMixin):
    def __init__(self):
        self.state_lock = threading.RLock()
        self.detect_owned_games = True
        self.api_key_bound = True
        self.active_steamid64 = "76561198000000000"
        self.api_key = "A" * 32
        self.fetch_result = ({"570"}, {"570": 11290})
        self.fetch_error = None
        self.cleared_cache = False
        self.saved_cache = False
        self.logged_exceptions = []
        self.slow_calls = []
        self.owned_games_last_attempt = 0
        self.owned_games_last_sync = 0
        self.owned_games_public_profile = None
        self.owned_games_steamid64 = None
        self.owned_app_ids = set()
        self.owned_game_playtimes = {}
        self.owned_games_cache_loaded = False
        self.urllib3 = SimpleNamespace(exceptions=SimpleNamespace(TimeoutError=TimeoutError, HTTPError=HTTPError))

    def should_detect_owned_games(self):
        return self.detect_owned_games

    def is_owned_api_key_bound_to_active_user(self):
        return self.api_key_bound

    def get_active_steam_user_steamid64(self):
        return self.active_steamid64

    def get_owned_api_key(self):
        return self.api_key

    def clear_owned_games_cache(self):
        self.cleared_cache = True

    def fetch_owned_app_ids_from_api(self, api_key, steamid64, timeout=3):
        if self.fetch_error is not None:
            raise self.fetch_error
        return self.fetch_result

    def save_owned_games_cache(self):
        self.saved_cache = True

    def log_exception(self, message):
        self.logged_exceptions.append(message)

    def log_slow_call(self, name, elapsed_ms, details):
        self.slow_calls.append((name, elapsed_ms, details))


class ProfileMixinTests(unittest.TestCase):
    def test_refresh_owned_games_cache_updates_state_on_success(self):
        plugin = ProfileHarness()

        plugin.refresh_owned_games_cache()

        self.assertTrue(plugin.saved_cache)
        self.assertTrue(plugin.owned_games_cache_loaded)
        self.assertEqual(plugin.owned_games_steamid64, "76561198000000000")
        self.assertEqual(plugin.owned_app_ids, {"570"})
        self.assertEqual(plugin.owned_game_playtimes, {"570": 11290})
        self.assertEqual(plugin.logged_exceptions, [])
        self.assertIn("success=True", plugin.slow_calls[-1][2])

    def test_refresh_owned_games_cache_ignores_expected_network_errors(self):
        plugin = ProfileHarness()
        plugin.fetch_error = TimeoutError("slow")

        plugin.refresh_owned_games_cache()

        self.assertFalse(plugin.saved_cache)
        self.assertEqual(plugin.logged_exceptions, [])
        self.assertEqual(plugin.owned_games_steamid64, "76561198000000000")
        self.assertIn("success=False", plugin.slow_calls[-1][2])

    def test_refresh_owned_games_cache_logs_unexpected_errors(self):
        plugin = ProfileHarness()
        plugin.fetch_error = RuntimeError("boom")

        plugin.refresh_owned_games_cache()

        self.assertFalse(plugin.saved_cache)
        self.assertEqual(plugin.logged_exceptions, ["Failed to refresh owned Steam games"])

    def test_refresh_owned_games_cache_clears_cache_when_active_user_is_missing(self):
        plugin = ProfileHarness()
        plugin.active_steamid64 = None

        plugin.refresh_owned_games_cache()

        self.assertTrue(plugin.cleared_cache)
        self.assertFalse(plugin.saved_cache)


if __name__ == "__main__":
    unittest.main()
