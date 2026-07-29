import sys
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LIB_PATH = PROJECT_ROOT / "lib"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(LIB_PATH) not in sys.path:
    sys.path.insert(0, str(LIB_PATH))

from steamflow.friends_service import (
    FriendsListUnavailableError,
    build_friend_list_url,
    build_player_summaries_url,
    fetch_friends,
    friend_presence_group,
    group_playing_friends_by_app,
    is_favorite_friend,
    is_friends_refresh_running,
    normalize_friends_cache_payload,
    parse_friend_list_payload,
    release_friends_refresh_lock,
    should_schedule_friends_refresh,
    sort_friends,
    start_friends_refresh_worker_process,
    steamid64_to_accountid,
    try_acquire_friends_refresh_lock,
    wait_for_friends_cache_update,
)
from steamflow.cache_utils import write_json_file


class Response:
    def __init__(self, payload):
        import json

        self.data = json.dumps(payload).encode("utf-8")


class FriendsServiceTests(unittest.TestCase):
    def test_stale_snapshot_schedules_refresh_but_fresh_snapshot_does_not(self):
        self.assertTrue(
            should_schedule_friends_refresh(
                "owner",
                "owner",
                last_sync=89,
                last_attempt=89,
                error="",
                ttl_seconds=10,
                retry_delay_seconds=60,
                now=100,
            )
        )
        self.assertFalse(
            should_schedule_friends_refresh(
                "owner",
                "owner",
                last_sync=91,
                last_attempt=91,
                error="",
                ttl_seconds=10,
                retry_delay_seconds=60,
                now=100,
            )
        )

    def test_failed_refresh_respects_retry_delay(self):
        self.assertFalse(
            should_schedule_friends_refresh(
                "owner",
                "owner",
                last_sync=1,
                last_attempt=90,
                error="request_failed",
                ttl_seconds=10,
                retry_delay_seconds=60,
                now=100,
            )
        )
        self.assertTrue(
            should_schedule_friends_refresh(
                "owner",
                "owner",
                last_sync=1,
                last_attempt=39,
                error="request_failed",
                ttl_seconds=10,
                retry_delay_seconds=60,
                now=100,
            )
        )

    def test_refresh_lock_reports_running_worker(self):
        with TemporaryDirectory() as temp_dir:
            cache_file = Path(temp_dir) / "cache_friends.json"
            lock = try_acquire_friends_refresh_lock(cache_file, now=100)
            try:
                self.assertTrue(is_friends_refresh_running(cache_file))
            finally:
                release_friends_refresh_lock(lock)
            self.assertFalse(is_friends_refresh_running(cache_file))

    def test_starts_hidden_refresh_worker_without_api_key_in_command(self):
        calls = []

        class FakeProcess:
            pass

        def popen(command, **kwargs):
            calls.append((command, kwargs))
            return FakeProcess()

        class FakeSubprocess:
            DEVNULL = object()
            STARTUPINFO = None

        with TemporaryDirectory() as temp_dir:
            plugin_dir = Path(temp_dir)
            (plugin_dir / "main.py").touch()
            process = start_friends_refresh_worker_process(
                plugin_dir,
                python_executable="python",
                popen=popen,
                platform="linux",
                subprocess_module=FakeSubprocess,
            )

        self.assertIsInstance(process, FakeProcess)
        command, kwargs = calls[0]
        self.assertEqual(command[:2], ["python", str(plugin_dir / "main.py")])
        request = json.loads(command[2])
        self.assertEqual(request["method"], "refresh_steam_friends")
        self.assertNotIn("key", command[2].lower())
        self.assertEqual(kwargs["cwd"], str(plugin_dir))

    def test_refresh_lock_prevents_two_short_lived_flow_processes_from_fetching(self):
        with TemporaryDirectory() as temp_dir:
            cache_file = Path(temp_dir) / "cache_friends.json"
            first_lock = try_acquire_friends_refresh_lock(cache_file)
            try:
                self.assertIsNotNone(first_lock)
                self.assertIsNone(try_acquire_friends_refresh_lock(cache_file))
            finally:
                release_friends_refresh_lock(first_lock)

            second_lock = try_acquire_friends_refresh_lock(cache_file)
            self.assertIsNotNone(second_lock)
            release_friends_refresh_lock(second_lock)

    def test_waits_for_completed_cache_instead_of_in_progress_snapshot(self):
        with TemporaryDirectory() as temp_dir:
            cache_file = Path(temp_dir) / "cache_friends.json"
            write_json_file(
                cache_file,
                {
                    "last_attempt": 2,
                    "timestamp": 1,
                    "steamid64": "owner",
                    "items": [{"steamid": "old"}],
                    "error": "",
                },
            )
            wrote_completed_cache = False

            def complete_refresh(_seconds):
                nonlocal wrote_completed_cache
                if wrote_completed_cache:
                    return
                wrote_completed_cache = True
                write_json_file(
                    cache_file,
                    {
                        "last_attempt": 3,
                        "timestamp": 3,
                        "steamid64": "owner",
                        "items": [{"steamid": "fresh"}],
                        "error": "",
                    },
                )

            payload = wait_for_friends_cache_update(
                cache_file,
                "owner",
                previous_attempt=1,
                timeout_seconds=0.2,
                poll_seconds=0,
                sleeper=complete_refresh,
            )

            self.assertEqual(payload["items"][0]["steamid64"], "fresh")

    def test_builds_documented_web_api_urls(self):
        self.assertIn("ISteamUser/GetFriendList/v1/", build_friend_list_url("key", "owner"))
        self.assertIn("relationship=friend", build_friend_list_url("key", "owner"))
        summaries_url = build_player_summaries_url("key", ["1", "2"])
        self.assertIn("ISteamUser/GetPlayerSummaries/v2/", summaries_url)
        self.assertIn("steamids=1%2C2", summaries_url)

    def test_private_or_missing_friend_list_has_specific_error(self):
        with self.assertRaises(FriendsListUnavailableError):
            parse_friend_list_payload({"friendslist": None})

    def test_private_friend_list_http_error_has_specific_error(self):
        def http_get(*_args, **_kwargs):
            raise RuntimeError("HTTP 401")

        with self.assertRaises(FriendsListUnavailableError):
            fetch_friends("key", "owner", http_get)

    def test_fetches_player_summaries_in_batches_and_keeps_last_logoff(self):
        calls = []
        friend_ids = [str(index) for index in range(1, 102)]

        def http_get(url, timeout, headers):
            calls.append((url, timeout, headers))
            if "GetFriendList" in url:
                return Response(
                    {
                        "friendslist": {
                            "friends": [
                                {"steamid": friend_id, "relationship": "friend", "friend_since": 123}
                                for friend_id in friend_ids
                            ]
                        }
                    }
                )
            ids = url.split("steamids=", 1)[1].split("&", 1)[0].replace("%2C", ",").split(",")
            return Response(
                {
                    "response": {
                        "players": [
                            {
                                "steamid": friend_id,
                                "personaname": f"Friend {friend_id}",
                                "personastate": 1,
                                "lastlogoff": 456,
                                "lobbysteamid": "109775244723268201",
                            }
                            for friend_id in ids
                        ]
                    }
                }
            )

        friends = fetch_friends("key", "owner", http_get)

        self.assertEqual(len(calls), 3)
        self.assertEqual(len(friends), 101)
        self.assertNotIn("friend_since", friends[0])
        self.assertEqual(friends[0]["lastlogoff"], 456)
        self.assertEqual(friends[0]["personaname"], "Friend 1")
        self.assertEqual(
            friends[0]["lobbysteamid"],
            "109775244723268201",
        )

    def test_searches_name_game_and_steam_id_then_sorts_presence(self):
        friends = [
            {"steamid": "3", "personaname": "Charlie", "personastate": 0},
            {"steamid": "2", "personaname": "Bravo", "personastate": 1},
            {
                "steamid": "1",
                "personaname": "Alpha",
                "personastate": 1,
                "gameid": "570",
                "gameextrainfo": "Dota 2",
            },
        ]

        self.assertEqual(
            [item["steamid64"] for item in sort_friends(friends)],
            ["1", "2", "3"],
        )
        self.assertEqual([item["steamid64"] for item in sort_friends(friends, "dota")], ["1"])
        self.assertEqual([item["steamid64"] for item in sort_friends(friends, "3")], ["3"])
        self.assertEqual(friend_presence_group(friends[2]), "playing")

    def test_active_favorites_are_pinned_but_search_relevance_wins(self):
        favorite_steamid64 = "76561199268740725"
        favorite_accountid = steamid64_to_accountid(favorite_steamid64)
        friends = [
            {
                "steamid": "2",
                "personaname": "Alice Exact",
                "gameid": "570",
                "gameextrainfo": "Dota 2",
            },
            {
                "steamid": favorite_steamid64,
                "personaname": "Favorite Bob",
                "personastate": 1,
            },
        ]

        self.assertEqual(
            [item["personaname"] for item in sort_friends(
                friends,
                favorite_accountids={favorite_accountid},
            )],
            ["Favorite Bob", "Alice Exact"],
        )
        self.assertEqual(
            [item["personaname"] for item in sort_friends(
                friends,
                "alice exact",
                {favorite_accountid},
            )],
            ["Alice Exact"],
        )
        self.assertTrue(
            is_favorite_friend(
                {"steamid64": favorite_steamid64},
                {favorite_accountid},
            )
        )

    def test_offline_favorite_stays_in_regular_offline_block(self):
        friends = [
            {"steamid": "2", "personaname": "Online Bob", "personastate": 1},
            {"steamid": "1", "personaname": "Offline Favorite", "personastate": 0},
        ]

        self.assertEqual(
            [item["personaname"] for item in sort_friends(
                friends,
                favorite_accountids={1},
            )],
            ["Online Bob", "Offline Favorite"],
        )

    def test_groups_playing_friends_by_app_and_sorts_names(self):
        grouped = group_playing_friends_by_app(
            [
                {
                    "steamid": "2",
                    "personaname": "Bravo",
                    "gameid": "570",
                    "gameextrainfo": "Dota 2",
                },
                {
                    "steamid": "1",
                    "personaname": "Alpha",
                    "gameid": "570",
                    "gameextrainfo": "Dota 2",
                },
                {"steamid": "3", "personaname": "Offline"},
            ]
        )

        self.assertEqual(grouped, {"570": ["Alpha", "Bravo"]})

    def test_normalizes_cache_payload(self):
        cache = normalize_friends_cache_payload(
            {
                "last_attempt": "10",
                "timestamp": "20",
                "steamid64": "owner",
                "items": [{"steamid": "friend", "personaname": "Alice"}],
            }
        )

        self.assertEqual(cache["last_attempt"], 10.0)
        self.assertEqual(cache["last_sync"], 20.0)
        self.assertEqual(cache["items"][0]["steamid64"], "friend")


if __name__ == "__main__":
    unittest.main()
