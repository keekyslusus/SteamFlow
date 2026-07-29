import json
import sys
import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LIB_PATH = PROJECT_ROOT / "lib"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(LIB_PATH) not in sys.path:
    sys.path.insert(0, str(LIB_PATH))

from steamflow.steam_deck import SteamPluginSteamDeckMixin


DAY = 24 * 60 * 60
STEAMID64 = "76561198000000000"


class SteamDeckHarness(SteamPluginSteamDeckMixin):
    def __init__(self, cache_file):
        self.steam_deck_cache_file = Path(cache_file)
        self.state_lock = threading.RLock()
        self.steam_deck_cache_loaded = True
        self.steam_deck_account_states = {}
        self.steam_deck_compatibility_cache = {}
        self.steam_deck_compatibility_last_failure = 0
        self.pending_steam_deck_history_refresh = False
        self.api_key = "A" * 32
        self.bound = True
        self.http_calls = []
        self.last_played_games = []
        self.compatibility_categories = {}
        self.logged_exceptions = []

    def get_active_steam_user_steamid64(self):
        return STEAMID64

    def get_owned_api_key(self):
        return self.api_key

    def has_owned_api_key(self):
        return bool(self.api_key)

    def is_owned_api_key_bound_to_active_user(self):
        return self.bound

    def get_country_code(self):
        return "kz"

    def get_steam_language(self):
        return "russian"

    def get_language(self):
        return "en"

    def _http_get(self, url, timeout, headers):
        self.http_calls.append((url, timeout, headers))
        if "ClientGetLastPlayedTimes" in url:
            payload = {"response": {"games": self.last_played_games}}
        else:
            payload = {
                "response": {
                    "store_items": [
                        {
                            "appid": int(app_id),
                            "platforms": {
                                "steam_deck_compat_category": category,
                            },
                        }
                        for app_id, category in self.compatibility_categories.items()
                    ]
                }
            }
        return SimpleNamespace(data=json.dumps(payload).encode("utf-8"))

    def log_exception(self, message):
        self.logged_exceptions.append(message)

    def log_slow_call(self, *_args):
        return None


class SteamDeckMixinTests(unittest.TestCase):
    def test_refresh_marks_recent_deck_user_active_and_rechecks_in_fourteen_days(self):
        with TemporaryDirectory() as temp_dir:
            plugin = SteamDeckHarness(Path(temp_dir) / "deck.json")
            now = 100 * DAY
            plugin.last_played_games = [
                {
                    "appid": 570,
                    "last_deck_playtime": now - DAY,
                    "playtime_deck_forever": 10,
                }
            ]

            self.assertTrue(plugin.refresh_steam_deck_history(now=now))
            state = plugin.get_steam_deck_account_state()

            self.assertTrue(state["ever_detected"])
            self.assertEqual(state["next_check_at"], now + 14 * DAY)
            self.assertTrue(plugin.is_steam_deck_active(now=now, schedule_refresh=False))

    def test_negative_checks_follow_one_three_seven_day_schedule(self):
        with TemporaryDirectory() as temp_dir:
            plugin = SteamDeckHarness(Path(temp_dir) / "deck.json")
            now = 100 * DAY

            plugin.refresh_steam_deck_history(now=now)
            self.assertEqual(
                plugin.get_steam_deck_account_state()["next_check_at"],
                now + DAY,
            )

            plugin.refresh_steam_deck_history(now=now + DAY)
            self.assertEqual(
                plugin.get_steam_deck_account_state()["next_check_at"],
                now + 4 * DAY,
            )

            plugin.refresh_steam_deck_history(now=now + 4 * DAY)
            self.assertEqual(
                plugin.get_steam_deck_account_state()["next_check_at"],
                now + 11 * DAY,
            )

    def test_inactive_user_never_requests_store_compatibility(self):
        with TemporaryDirectory() as temp_dir:
            plugin = SteamDeckHarness(Path(temp_dir) / "deck.json")
            now = 100 * DAY
            plugin.steam_deck_account_states[STEAMID64] = {
                "last_deck_playtime": now - 50 * DAY - 1,
                "next_check_at": now + DAY,
                "ever_detected": True,
            }

            categories = plugin.get_steam_deck_compatibility_categories(["570"], now=now)

            self.assertEqual(categories, {})
            self.assertEqual(plugin.http_calls, [])

    def test_empty_successful_refresh_does_not_erase_known_deck_timestamp(self):
        with TemporaryDirectory() as temp_dir:
            plugin = SteamDeckHarness(Path(temp_dir) / "deck.json")
            now = 100 * DAY
            previous_playtime = now - 40 * DAY
            plugin.steam_deck_account_states[STEAMID64] = {
                "last_deck_playtime": previous_playtime,
                "next_check_at": now,
                "ever_detected": True,
            }

            plugin.refresh_steam_deck_history(now=now)

            self.assertEqual(
                plugin.get_steam_deck_account_state()["last_deck_playtime"],
                previous_playtime,
            )
            self.assertTrue(plugin.is_steam_deck_active(now=now, schedule_refresh=False))

    def test_active_user_fetches_compatibility_once_then_uses_cache(self):
        with TemporaryDirectory() as temp_dir:
            plugin = SteamDeckHarness(Path(temp_dir) / "deck.json")
            now = 100 * DAY
            plugin.steam_deck_account_states[STEAMID64] = {
                "last_deck_playtime": now - DAY,
                "next_check_at": now + DAY,
                "ever_detected": True,
            }
            plugin.compatibility_categories = {"570": 2}

            first = plugin.get_steam_deck_compatibility_categories(["570"], now=now)
            second = plugin.get_steam_deck_compatibility_categories(["570"], now=now + 1)

            self.assertEqual(first, {"570": 2})
            self.assertEqual(second, {"570": 2})
            store_calls = [
                call for call in plugin.http_calls if "IStoreBrowseService" in call[0]
            ]
            self.assertEqual(len(store_calls), 1)

    def test_missing_or_mismatched_api_key_disables_feature_without_requests(self):
        with TemporaryDirectory() as temp_dir:
            plugin = SteamDeckHarness(Path(temp_dir) / "deck.json")
            plugin.bound = False

            self.assertFalse(plugin.is_steam_deck_active(schedule_refresh=False))
            self.assertEqual(
                plugin.get_steam_deck_compatibility_categories(["570"]),
                {},
            )
            self.assertEqual(plugin.http_calls, [])


if __name__ == "__main__":
    unittest.main()
