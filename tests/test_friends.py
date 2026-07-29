import sys
import time
import unittest
from unittest.mock import patch
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LIB_PATH = PROJECT_ROOT / "lib"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(LIB_PATH) not in sys.path:
    sys.path.insert(0, str(LIB_PATH))

from steamflow.constants import STEAMFLOW_CONFIG
from steamflow.friends import SteamPluginFriendsMixin
from steamflow.friends_ui_service import build_friends_playing_suffix
from steamflow.localization import Localizer
from steamflow.ui_query import SteamPluginUIQueryMixin


class DummyLock:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class FriendsHarness(SteamPluginFriendsMixin):
    FRIENDS_ICON = "friends-icon"
    ONLINE_ICON = "online-icon"
    OFFLINE_ICON = "offline-icon"
    INVISIBLE_ICON = "away-icon"
    DEFAULT_ICON = "default-icon"

    def __init__(self, cache_file):
        self.friends_cache_file = Path(cache_file)
        self.friend_favorites_cache_file = Path(cache_file).with_name(
            "friend_favorites.json"
        )
        self.secure_settings_dir = Path(cache_file).parent
        self.state_lock = DummyLock()
        self.friends_cache_loaded = True
        self.friends_items = []
        self.friends_last_attempt = 0
        self.friends_last_sync = time.time()
        self.friends_steamid64 = "owner"
        self.friends_last_error = ""
        self.friend_favorites_cache_loaded = True
        self.friend_favorites_by_steamid = {
            "owner": {"timestamp": time.time(), "accountids": set()}
        }
        self.has_key = True
        self.bound = True
        self.started_friends_refresh_workers = 0
        self.feature_failures = []
        self.feature_successes = []

    def get_active_steam_user_steamid64(self):
        return "owner"

    def has_owned_api_key(self):
        return self.has_key

    def is_owned_api_key_bound_to_active_user(self):
        return self.bound

    def get_owned_api_key(self):
        return "key"

    def build_action(self, method, *parameters):
        return {"method": method, "parameters": list(parameters)}

    def build_change_query_action(self, query, requery=True, keep_open=True):
        return {
            "method": "change_query",
            "parameters": [query, requery],
            "dontHideAfterAction": keep_open,
        }

    def build_plugin_query(self, *parts):
        return "steam " + " ".join(str(part).strip() for part in parts if str(part).strip())

    def build_result(self, title, subtitle, icon_path=None, action=None, context_data=None, **extra):
        result = {
            "Title": title,
            "SubTitle": subtitle,
            "IcoPath": icon_path,
            "JsonRPCAction": action,
            "ContextData": context_data,
        }
        result.update(extra)
        return result

    def _read_json_file(self, *_args):
        return None

    def _write_json_file(self, *_args, **_kwargs):
        return True

    def _http_get(self, *_args, **_kwargs):
        raise AssertionError("Network should not be used for a fresh cache")

    def feature_enabled(self, _name):
        return True

    def record_feature_failure(self, name, error=None, reason="unknown", now=None):
        self.feature_failures.append((name, str(error or ""), reason, now))

    def record_feature_success(self, name, now=None):
        self.feature_successes.append((name, now))

    def log_exception(self, _message):
        return None

    def start_friends_refresh_worker(self):
        self.started_friends_refresh_workers += 1
        return object()


class FriendsMixinTests(unittest.TestCase):
    def test_cached_results_use_avatar_chat_action_and_friend_context(self):
        with TemporaryDirectory() as temp_dir:
            harness = FriendsHarness(Path(temp_dir) / "friends.json")
            harness.friends_items = [
                {
                    "steamid64": "76561199268740725",
                    "personaname": "Alice",
                    "personastate": 1,
                    "avatarmedium": "https://cdn/avatar.jpg",
                    "gameid": "394360",
                    "gameextrainfo": "Hearts of Iron IV",
                }
            ]

            result = harness.build_friends_results("ali")[0]

            self.assertEqual(result["Title"], "Alice")
            self.assertEqual(result["IcoPath"], "https://cdn/avatar.jpg")
            self.assertEqual(
                result["JsonRPCAction"],
                {"method": "open_steam_friend_chat", "parameters": ["76561199268740725"]},
            )
            self.assertEqual(result["ContextData"]["menu"], "friend")
            self.assertEqual(result["ContextData"]["game_name"], "Hearts of Iron IV")

    def test_offline_friend_shows_last_seen_but_online_friend_does_not(self):
        with TemporaryDirectory() as temp_dir:
            harness = FriendsHarness(Path(temp_dir) / "friends.json")
            harness.friends_items = [
                {
                    "steamid64": "1",
                    "personaname": "Offline Alice",
                    "personastate": 0,
                    "lastlogoff": 1_700_000_000,
                },
                {
                    "steamid64": "2",
                    "personaname": "Online Bob",
                    "personastate": 1,
                    "lastlogoff": 1_700_000_000,
                },
            ]

            with patch(
                "steamflow.friends_ui_service.format_last_seen",
                return_value="2h ago",
            ):
                results = harness.build_friends_results()

            by_title = {result["Title"]: result for result in results}
            self.assertIn("Last seen 2h ago", by_title["Offline Alice"]["SubTitle"])
            self.assertNotIn("Last seen", by_title["Online Bob"]["SubTitle"])

    def test_missing_api_key_links_to_api_setup(self):
        with TemporaryDirectory() as temp_dir:
            harness = FriendsHarness(Path(temp_dir) / "friends.json")
            harness.has_key = False

            result = harness.build_friends_results()[0]

            self.assertEqual(result["Title"], "Steam Friends Unavailable")
            self.assertEqual(result["JsonRPCAction"]["parameters"][0], "steam api")

    def test_empty_search_is_explicit(self):
        with TemporaryDirectory() as temp_dir:
            harness = FriendsHarness(Path(temp_dir) / "friends.json")
            harness.friends_items = [
                {"steamid64": "1", "personaname": "Alice", "personastate": 0}
            ]

            result = harness.build_friends_results("Bob")[0]

            self.assertEqual(result["Title"], "No friends found for 'Bob'")

    def test_cold_cache_fetches_synchronously_in_flow_query_process(self):
        with TemporaryDirectory() as temp_dir:
            harness = FriendsHarness(Path(temp_dir) / "friends.json")
            harness.friends_steamid64 = None
            harness.friends_last_sync = 0
            fetch_calls = []

            def fetch_friends(api_key, steamid64, timeout=3):
                fetch_calls.append((api_key, steamid64, timeout))
                return [
                    {
                        "steamid64": "76561199268740725",
                        "personaname": "Alice",
                        "personastate": 1,
                    }
                ]

            harness.fetch_friends_from_api = fetch_friends

            result = harness.build_friends_results()[0]

            self.assertEqual(result["Title"], "Alice")
            self.assertEqual(fetch_calls, [("key", "owner", 3)])
            self.assertFalse(Path(f"{harness.friends_cache_file}.refresh.lock").exists())

    def test_stale_snapshot_is_not_silently_shown_after_refresh_failure(self):
        with TemporaryDirectory() as temp_dir:
            harness = FriendsHarness(Path(temp_dir) / "friends.json")
            harness.friends_last_sync = time.time() - 10
            harness.friends_items = [
                {"steamid64": "1", "personaname": "Stale Alice", "personastate": 1}
            ]

            def fail_fetch(*_args, **_kwargs):
                raise RuntimeError("network unavailable")

            harness.fetch_friends_from_api = fail_fetch

            result = harness.build_friends_results()[0]

            self.assertEqual(result["Title"], "Steam Friends Unavailable")
            self.assertNotEqual(result["Title"], "Stale Alice")

    def test_friends_freshness_window_is_ten_seconds(self):
        self.assertEqual(STEAMFLOW_CONFIG.cache.friends_ttl_seconds, 10)

    def test_friend_favorites_refresh_window_is_sixty_seconds(self):
        self.assertEqual(
            STEAMFLOW_CONFIG.cache.friend_favorites_ttl_seconds,
            60,
        )

    def test_active_favorite_is_pinned_and_marked_before_regular_playing_friend(self):
        with TemporaryDirectory() as temp_dir:
            harness = FriendsHarness(Path(temp_dir) / "friends.json")
            favorite_steamid64 = "76561199268740725"
            harness.friend_favorites_by_steamid["owner"]["accountids"] = {
                1308474997
            }
            harness.friends_items = [
                {
                    "steamid64": "2",
                    "personaname": "Playing Bob",
                    "gameid": "570",
                    "gameextrainfo": "Dota 2",
                },
                {
                    "steamid64": favorite_steamid64,
                    "personaname": "Favorite Alice",
                    "personastate": 1,
                },
            ]

            results = harness.build_friends_results()

            self.assertEqual(results[0]["Title"], "Favorite Alice")
            self.assertEqual(results[0]["SubTitle"], "★ Online")
            self.assertEqual(results[1]["Title"], "Playing Bob")

    def test_stale_favorites_refresh_and_are_saved_for_active_account(self):
        with TemporaryDirectory() as temp_dir:
            harness = FriendsHarness(Path(temp_dir) / "friends.json")
            harness.friend_favorites_by_steamid["owner"]["timestamp"] = time.time() - 61
            token_calls = []
            fetch_calls = []
            harness.get_steam_session_token_for_favorites = lambda steamid64: (
                token_calls.append(steamid64) or "session-token"
            )
            harness.fetch_friend_favorites_from_api = (
                lambda token, timeout=3: fetch_calls.append((token, timeout))
                or {123}
            )

            accountids = harness.get_friend_favorite_accountids()

            self.assertEqual(accountids, {123})
            self.assertEqual(token_calls, ["owner"])
            self.assertEqual(fetch_calls, [("session-token", 3)])
            self.assertEqual(
                harness.friend_favorites_by_steamid["owner"]["accountids"],
                {123},
            )
            self.assertEqual(harness.feature_successes[0][0], "steam_favorites")

    def test_favorites_failure_uses_last_successful_cache(self):
        with TemporaryDirectory() as temp_dir:
            harness = FriendsHarness(Path(temp_dir) / "friends.json")
            harness.friend_favorites_by_steamid["owner"] = {
                "timestamp": time.time() - 61,
                "accountids": {456},
            }
            harness.get_steam_session_token_for_favorites = lambda _steamid64: (
                "session-token"
            )

            def fail_fetch(*_args, **_kwargs):
                raise RuntimeError("HTTP 401")

            harness.fetch_friend_favorites_from_api = fail_fetch

            accountids = harness.get_friend_favorite_accountids()

            self.assertEqual(accountids, {456})
            self.assertEqual(harness.feature_failures[0][0], "steam_favorites")
            self.assertEqual(harness.feature_failures[0][2], "auth_rejected")

    def test_fresh_playing_snapshot_is_grouped_without_network(self):
        with TemporaryDirectory() as temp_dir:
            harness = FriendsHarness(Path(temp_dir) / "friends.json")
            harness.friends_items = [
                {
                    "steamid64": "1",
                    "personaname": "Alice",
                    "personastate": 1,
                    "gameid": "570",
                    "gameextrainfo": "Dota 2",
                }
            ]

            self.assertEqual(
                harness.get_fresh_friends_playing_by_app(),
                {"570": ["Alice"]},
            )

    def test_stale_playing_snapshot_is_exposed_while_background_refresh_starts(self):
        with TemporaryDirectory() as temp_dir:
            harness = FriendsHarness(Path(temp_dir) / "friends.json")
            harness.friends_last_sync = time.time() - 11
            harness.friends_items = [
                {
                    "steamid64": "1",
                    "personaname": "Alice",
                    "gameid": "570",
                }
            ]

            self.assertEqual(
                harness.get_fresh_friends_playing_by_app(),
                {"570": ["Alice"]},
            )
            self.assertEqual(harness.started_friends_refresh_workers, 1)

    def test_fresh_playing_snapshot_does_not_start_background_refresh(self):
        with TemporaryDirectory() as temp_dir:
            harness = FriendsHarness(Path(temp_dir) / "friends.json")
            harness.friends_items = [
                {
                    "steamid64": "1",
                    "personaname": "Alice",
                    "gameid": "570",
                }
            ]

            self.assertEqual(
                harness.get_fresh_friends_playing_by_app(),
                {"570": ["Alice"]},
            )
            self.assertEqual(harness.started_friends_refresh_workers, 0)

    def test_cold_home_starts_background_refresh_without_activity(self):
        with TemporaryDirectory() as temp_dir:
            harness = FriendsHarness(Path(temp_dir) / "friends.json")
            harness.friends_steamid64 = None
            harness.friends_last_sync = 0

            self.assertEqual(harness.get_fresh_friends_playing_by_app(), {})
            self.assertEqual(harness.started_friends_refresh_workers, 1)

    def test_friends_playing_suffix_uses_english_when_other_locale_is_requested(self):
        self.assertEqual(
            build_friends_playing_suffix(["Alice"]),
            " | Alice is playing",
        )
        english_only = Localizer("ru").tr
        self.assertEqual(
            build_friends_playing_suffix(["A", "B"], tr=english_only),
            " | 2 friends are playing",
        )
        self.assertEqual(
            build_friends_playing_suffix([str(index) for index in range(5)], tr=english_only),
            " | 5 friends are playing",
        )
        self.assertEqual(
            build_friends_playing_suffix([str(index) for index in range(21)], tr=english_only),
            " | 21 friends are playing",
        )

    def test_home_passes_fresh_friend_activity_without_affecting_search_results(self):
        class FriendsProviderStub:
            def __init__(self):
                self.calls = 0

            def fresh_playing_by_app(self):
                self.calls += 1
                return {"570": ["Alice"]}

        class QueryHarness(SteamPluginUIQueryMixin):
            def __init__(self):
                self.friends = FriendsProviderStub()
                self.providers = SimpleNamespace(friends=self.friends)

            def build_local_result(self, app_id, name, **kwargs):
                return {
                    "app_id": app_id,
                    "name": name,
                    "friends_playing": kwargs.get("friends_playing"),
                }

        harness = QueryHarness()

        home_results = harness.process_local_results(
            [("570", "Dota 2")],
            include_friends_playing=True,
        )
        search_results = harness.process_local_results([("570", "Dota 2")])

        self.assertEqual(home_results[0]["friends_playing"], ["Alice"])
        self.assertIsNone(search_results[0]["friends_playing"])
        self.assertEqual(harness.friends.calls, 1)


if __name__ == "__main__":
    unittest.main()
