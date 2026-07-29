import json
import sys
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import parse_qs, urlparse


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LIB_PATH = PROJECT_ROOT / "lib"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(LIB_PATH) not in sys.path:
    sys.path.insert(0, str(LIB_PATH))


from steamflow.friend_join_service import (
    FriendJoinCoordinator,
    build_friend_join_cache_payload,
    build_player_link_details_url,
    get_cached_join_details,
    get_join_candidates,
    get_playing_friends,
    get_public_join_details,
    get_owned_cache_state,
    find_installed_app_path,
    installed_app_matches_owner,
    normalize_friend_join_cache_payload,
    normalize_player_link_detail,
    parse_player_link_details_payload,
)


OWNER_ID = "76561198000000001"
ALICE_ID = "76561199268740725"
BOB_ID = "76561198000000002"


def player_link_account(
    *,
    steamid64=ALICE_ID,
    app_id="570",
    rich_presence="",
    lobby_id=0,
    server_ip=0,
    server_port=0,
    private=False,
):
    return {
        "public_data": {"steamid": steamid64},
        "private_data": {
            "game_id": app_id,
            "rich_presence_kv": rich_presence,
            "lobby_steam_id": lobby_id,
            "game_server_ip_address": server_ip,
            "game_server_port": server_port,
            "game_is_private": private,
        },
    }


class FriendJoinServiceTests(unittest.TestCase):
    def test_build_player_link_details_url_uses_session_token_and_input_json(self):
        url = build_player_link_details_url("session-token", [ALICE_ID])
        query = parse_qs(urlparse(url).query)

        self.assertEqual(query["access_token"], ["session-token"])
        self.assertEqual(
            json.loads(query["input_json"][0]),
            {"steamids": [ALICE_ID]},
        )
        self.assertNotIn("key", query)

    def test_connect_rich_presence_marks_matching_game_joinable(self):
        normalized = normalize_player_link_detail(
            player_link_account(
                rich_presence='"rp"\n{\n\t"connect"\t"127.0.0.1:27015"\n}',
            )
        )

        self.assertTrue(normalized["joinable"])
        self.assertTrue(normalized["has_connect"])
        self.assertFalse(normalized["has_lobby"])
        self.assertFalse(normalized["has_server"])

    def test_lobby_or_complete_server_endpoint_marks_game_joinable(self):
        cases = [
            {"lobby_id": "109775241012345678"},
            {"server_ip": 2130706433, "server_port": 27015},
        ]
        for values in cases:
            with self.subTest(values=values):
                normalized = normalize_player_link_detail(
                    player_link_account(**values)
                )

                self.assertTrue(normalized["joinable"])

    def test_incomplete_server_and_private_game_are_not_joinable(self):
        cases = [
            player_link_account(server_ip=2130706433, server_port=0),
            player_link_account(
                rich_presence='"rp" { "connect" "127.0.0.1:27015" }',
                private=True,
            ),
        ]
        for account in cases:
            with self.subTest(account=account):
                self.assertFalse(
                    normalize_player_link_detail(account)["joinable"]
                )

    def test_string_false_private_flag_does_not_block_join(self):
        normalized = normalize_player_link_detail(
            player_link_account(
                lobby_id="109775241012345678",
                private="false",
            )
        )

        self.assertTrue(normalized["joinable"])

    def test_payload_parser_indexes_accounts_by_steamid64(self):
        parsed = parse_player_link_details_payload(
            {
                "response": {
                    "accounts": [
                        player_link_account(lobby_id="109775241012345678")
                    ]
                }
            }
        )

        self.assertEqual(set(parsed), {ALICE_ID})
        self.assertEqual(parsed[ALICE_ID]["app_id"], "570")
        self.assertEqual(
            parsed[ALICE_ID]["lobby_id"],
            "109775241012345678",
        )

    def test_safe_cache_keeps_flags_but_not_raw_connection_data(self):
        raw_accounts = {
            OWNER_ID: {
                "timestamp": 100,
                "details": {
                    ALICE_ID: {
                        "steamid64": ALICE_ID,
                        "app_id": "570",
                        "joinable": True,
                        "has_connect": True,
                        "has_lobby": True,
                        "lobby_id": "109775241012345678",
                        "connect": "secret-connect-value",
                        "server_ip": "127.0.0.1",
                    }
                },
            }
        }

        payload = build_friend_join_cache_payload(raw_accounts)
        serialized = json.dumps(payload)
        normalized = normalize_friend_join_cache_payload(payload)

        self.assertNotIn("secret-connect-value", serialized)
        self.assertNotIn("127.0.0.1", serialized)
        self.assertTrue(normalized[OWNER_ID]["details"][ALICE_ID]["joinable"])
        self.assertEqual(
            normalized[OWNER_ID]["details"][ALICE_ID]["lobby_id"],
            "109775241012345678",
        )
        self.assertIsNotNone(
            get_cached_join_details(normalized, OWNER_ID, 5, now=104.999)
        )
        self.assertIsNone(
            get_cached_join_details(normalized, OWNER_ID, 5, now=105)
        )

    def test_candidates_require_matching_app_and_optional_friend(self):
        friends = [
            {"steamid64": ALICE_ID, "personaname": "Alice"},
            {"steamid64": "76561198000000002", "personaname": "Bob"},
        ]
        details = {
            ALICE_ID: {"app_id": "570", "joinable": True},
            "76561198000000002": {"app_id": "730", "joinable": True},
        }

        self.assertEqual(
            get_join_candidates(friends, details, "570"),
            [{"steamid64": ALICE_ID, "name": "Alice", "app_id": "570"}],
        )
        self.assertEqual(
            get_join_candidates(
                friends,
                details,
                "570",
                only_steamid64="76561198000000002",
            ),
            [],
        )
        self.assertEqual(
            get_join_candidates(
                friends,
                details,
                "570",
                only_steamid64="not-a-steamid",
            ),
            [],
        )

    def test_playing_friends_filter_uses_public_presence_before_network(self):
        friends = [
            {
                "steamid64": ALICE_ID,
                "personaname": "Alice",
                "gameid": "570",
            },
            {
                "steamid64": BOB_ID,
                "personaname": "Bob",
                "gameid": "730",
            },
            {
                "steamid64": "76561198000000003",
                "personaname": "Carol",
                "gameid": "",
            },
        ]

        self.assertEqual(get_playing_friends(friends, "570"), [friends[0]])
        self.assertEqual(
            get_playing_friends(
                friends,
                "570",
                only_steamid64=BOB_ID,
            ),
            [],
        )
        self.assertEqual(get_playing_friends(friends), friends[:2])

    def test_public_player_summary_lobby_marks_friend_joinable(self):
        friend = {
            "steamid64": ALICE_ID,
            "personaname": "Alice",
            "gameid": "1782210",
            "lobbysteamid": "109775244723268201",
        }

        details = get_public_join_details([friend])

        self.assertTrue(details[ALICE_ID]["joinable"])
        self.assertTrue(details[ALICE_ID]["has_lobby"])
        self.assertEqual(details[ALICE_ID]["app_id"], "1782210")
        self.assertEqual(
            details[ALICE_ID]["lobby_id"],
            "109775244723268201",
        )

    def test_public_player_summary_without_lobby_is_not_joinable(self):
        friend = {
            "steamid64": ALICE_ID,
            "personaname": "Alice",
            "gameid": "570",
        }

        details = get_public_join_details([friend])

        self.assertFalse(details[ALICE_ID]["joinable"])

    def test_owned_cache_must_match_account_app_and_freshness(self):
        payload = {
            "timestamp": 100,
            "steamid64": OWNER_ID,
            "owned_app_ids": ["570"],
            "owned_game_playtimes": {},
        }

        self.assertTrue(
            get_owned_cache_state(payload, OWNER_ID, "570", 60, now=159)
        )
        self.assertFalse(
            get_owned_cache_state(payload, OWNER_ID, "570", 60, now=160)
        )
        self.assertFalse(
            get_owned_cache_state(payload, ALICE_ID, "570", 60, now=101)
        )
        self.assertFalse(
            get_owned_cache_state(payload, OWNER_ID, "730", 60, now=101)
        )

    def test_installed_check_requires_fully_installed_manifest(self):
        import steamflow.friend_join_service as service_module

        with TemporaryDirectory() as temp_dir:
            steamapps = Path(temp_dir) / "steamapps"
            install_dir = steamapps / "common" / "Dota 2"
            install_dir.mkdir(parents=True)
            manifest_path = steamapps / "appmanifest_570.acf"
            manifest_path.write_text("", encoding="utf-8")
            original_library_paths = service_module.load_steam_library_paths
            original_manifest_loader = service_module.load_appmanifest_file
            service_module.load_steam_library_paths = (
                lambda _steam_path: [steamapps]
            )
            try:
                service_module.load_appmanifest_file = lambda _path: {
                    "install_dir": "Dota 2",
                    "state_flags": {
                        "is_visible": True,
                        "is_fully_installed": False,
                    },
                }
                self.assertIsNone(find_installed_app_path(temp_dir, "570"))

                service_module.load_appmanifest_file = lambda _path: {
                    "install_dir": "Dota 2",
                    "state_flags": {
                        "is_visible": True,
                        "is_fully_installed": True,
                    },
                }
                self.assertEqual(
                    find_installed_app_path(temp_dir, "570"),
                    install_dir,
                )
            finally:
                service_module.load_steam_library_paths = original_library_paths
                service_module.load_appmanifest_file = original_manifest_loader

    def test_installed_free_game_accepts_matching_manifest_last_owner(self):
        import steamflow.friend_join_service as service_module

        with TemporaryDirectory() as temp_dir:
            steamapps = Path(temp_dir) / "steamapps"
            install_dir = steamapps / "common" / "Dota 2"
            install_dir.mkdir(parents=True)
            manifest_path = steamapps / "appmanifest_570.acf"
            manifest_path.touch()
            original_library_paths = service_module.load_steam_library_paths
            original_manifest_loader = service_module.load_appmanifest_file
            service_module.load_steam_library_paths = (
                lambda _steam_path: [steamapps]
            )
            service_module.load_appmanifest_file = lambda _path: {
                "install_dir": "Dota 2",
                "last_owner": OWNER_ID,
                "state_flags": {"is_fully_installed": True},
            }
            try:
                self.assertTrue(
                    installed_app_matches_owner(
                        temp_dir,
                        "570",
                        OWNER_ID,
                    )
                )
                self.assertFalse(
                    installed_app_matches_owner(
                        temp_dir,
                        "570",
                        ALICE_ID,
                    )
                )
            finally:
                service_module.load_steam_library_paths = original_library_paths
                service_module.load_appmanifest_file = original_manifest_loader

    def test_coordinator_accepts_installed_free_game_owned_by_active_account(self):
        with TemporaryDirectory() as temp_dir:
            plugin_dir = Path(temp_dir) / "plugin"
            secure_dir = Path(temp_dir) / "secure"
            install_dir = Path(temp_dir) / "Dota 2"
            plugin_dir.mkdir()
            secure_dir.mkdir()
            install_dir.mkdir()
            (secure_dir / "cache_friends.json").write_text(
                json.dumps(
                    {
                        "timestamp": time.time(),
                        "steamid64": OWNER_ID,
                        "items": [
                            {
                                "steamid64": ALICE_ID,
                                "personaname": "Alice",
                                "gameid": "570",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            class TokenProvider:
                def __init__(self, *_args, **_kwargs):
                    pass

                def get_saved_or_htmlcache_token(self):
                    return "session-token"

            coordinator = FriendJoinCoordinator(
                plugin_dir,
                secure_dir,
                None,
                fetch_details=lambda *_args, **_kwargs: {
                    ALICE_ID: {
                        "steamid64": ALICE_ID,
                        "app_id": "570",
                        "joinable": True,
                    }
                },
                token_provider_factory=TokenProvider,
                installed_path_finder=lambda *_args: install_dir,
                installed_owner_matcher=lambda *_args: True,
            )

            self.assertEqual(
                coordinator.get_candidates("570"),
                [
                    {
                        "steamid64": ALICE_ID,
                        "name": "Alice",
                        "app_id": "570",
                    }
                ],
            )

    def test_coordinator_uses_public_lobby_without_session_token(self):
        with TemporaryDirectory() as temp_dir:
            plugin_dir = Path(temp_dir) / "plugin"
            secure_dir = Path(temp_dir) / "secure"
            install_dir = Path(temp_dir) / "Crab Game"
            plugin_dir.mkdir()
            secure_dir.mkdir()
            install_dir.mkdir()
            (secure_dir / "cache_friends.json").write_text(
                json.dumps(
                    {
                        "timestamp": time.time(),
                        "steamid64": OWNER_ID,
                        "items": [
                            {
                                "steamid64": ALICE_ID,
                                "personaname": "Alice",
                                "gameid": "1782210",
                                "lobbysteamid": "109775244723268201",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            fetch_calls = []

            coordinator = FriendJoinCoordinator(
                plugin_dir,
                secure_dir,
                None,
                fetch_details=lambda *_args, **_kwargs: fetch_calls.append(
                    "fetch"
                ),
                installed_path_finder=lambda *_args: install_dir,
                installed_owner_matcher=lambda *_args: True,
            )

            self.assertEqual(
                coordinator.get_candidates("1782210"),
                [
                    {
                        "steamid64": ALICE_ID,
                        "name": "Alice",
                        "app_id": "1782210",
                        "lobby_id": "109775244723268201",
                    }
                ],
            )
            self.assertEqual(fetch_calls, [])

    def test_coordinator_requires_owned_installed_game_and_reuses_five_second_cache(self):
        with TemporaryDirectory() as temp_dir:
            plugin_dir = Path(temp_dir) / "plugin"
            secure_dir = Path(temp_dir) / "secure"
            steam_dir = Path(temp_dir) / "steam"
            steamapps = steam_dir / "steamapps"
            install_dir = steamapps / "common" / "Dota 2"
            install_dir.mkdir(parents=True)
            plugin_dir.mkdir()
            secure_dir.mkdir()
            (steamapps / "appmanifest_570.acf").write_text(
                '"AppState"\n{\n"appid" "570"\n"name" "Dota 2"\n'
                '"installdir" "Dota 2"\n"StateFlags" "4"\n}',
                encoding="utf-8",
            )
            (plugin_dir / "cache_owned_games.json").write_text(
                json.dumps(
                    {
                        "timestamp": time.time(),
                        "steamid64": OWNER_ID,
                        "owned_app_ids": ["570", "730"],
                        "owned_game_playtimes": {},
                    }
                ),
                encoding="utf-8",
            )
            (secure_dir / "cache_friends.json").write_text(
                json.dumps(
                    {
                        "timestamp": time.time(),
                        "steamid64": OWNER_ID,
                        "items": [
                            {
                                "steamid64": ALICE_ID,
                                "personaname": "Alice",
                                "gameid": "570",
                            },
                            {
                                "steamid64": BOB_ID,
                                "personaname": "Bob",
                                "gameid": "730",
                            },
                            {
                                "steamid64": "76561198000000003",
                                "personaname": "Carol",
                                "gameid": "",
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )
            fetch_calls = []

            class TokenProvider:
                def __init__(self, *_args, **_kwargs):
                    pass

                def get_saved_or_htmlcache_token(self):
                    return "session-token"

            def fetch_details(token, steamids, timeout):
                fetch_calls.append((token, list(steamids), timeout))
                return {
                    ALICE_ID: {
                        "steamid64": ALICE_ID,
                        "app_id": "570",
                        "joinable": True,
                        "has_connect": True,
                        "has_lobby": False,
                        "has_server": False,
                    },
                    BOB_ID: {
                        "steamid64": BOB_ID,
                        "app_id": "730",
                        "joinable": True,
                        "has_connect": False,
                        "has_lobby": True,
                        "has_server": False,
                    },
                }

            coordinator = FriendJoinCoordinator(
                plugin_dir,
                secure_dir,
                steam_dir,
                fetch_details=fetch_details,
                token_provider_factory=TokenProvider,
                installed_path_finder=lambda _steam_path, app_id: (
                    install_dir if str(app_id) in {"570", "730"} else None
                ),
            )

            first = coordinator.get_candidates("570")
            second = coordinator.get_candidates("570")
            third = coordinator.get_candidates("730")

            self.assertEqual(first, second)
            self.assertEqual(first[0]["name"], "Alice")
            self.assertEqual(third[0]["name"], "Bob")
            self.assertEqual(len(fetch_calls), 1)
            self.assertEqual(fetch_calls[0][1], [ALICE_ID, BOB_ID])
            cached_text = coordinator.join_cache_file.read_text(
                encoding="utf-8"
            )
            self.assertNotIn("session-token", cached_text)

    def test_coordinator_skips_prerequisites_and_endpoint_when_no_friend_plays_app(self):
        with TemporaryDirectory() as temp_dir:
            plugin_dir = Path(temp_dir) / "plugin"
            secure_dir = Path(temp_dir) / "secure"
            plugin_dir.mkdir()
            secure_dir.mkdir()
            (secure_dir / "cache_friends.json").write_text(
                json.dumps(
                    {
                        "timestamp": time.time(),
                        "steamid64": OWNER_ID,
                        "items": [
                            {
                                "steamid64": ALICE_ID,
                                "personaname": "Alice",
                                "gameid": "730",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            calls = []

            coordinator = FriendJoinCoordinator(
                plugin_dir,
                secure_dir,
                None,
                fetch_details=lambda *_args, **_kwargs: calls.append("fetch"),
                installed_path_finder=lambda *_args: calls.append("install"),
            )

            self.assertEqual(coordinator.get_candidates("570"), [])
            self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
