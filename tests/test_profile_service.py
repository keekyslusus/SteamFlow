import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LIB_PATH = PROJECT_ROOT / "lib"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(LIB_PATH) not in sys.path:
    sys.path.insert(0, str(LIB_PATH))

from steamflow.profile_service import (
    build_owned_games_cache_payload,
    build_avatar_frame_cache_entry,
    build_no_avatar_frame_cache_entry,
    build_owned_games_refresh_log_details,
    fetch_owned_app_ids,
    fetch_owned_games_refresh_result,
    fetch_player_summary,
    get_cached_avatar_frame_state,
    get_owned_app_state,
    get_profile_status_label,
    is_owned_games_cache_fresh,
    normalize_avatar_frame_image_url,
    normalize_owned_games_cache_payload,
    parse_avatar_frame_payload,
    parse_owned_games_payload,
    parse_player_summary_payload,
    should_schedule_owned_games_refresh,
)


class ProfileServiceTests(unittest.TestCase):
    def test_parse_player_summary_payload_normalizes_active_profile_summary(self):
        summary = parse_player_summary_payload(
            {
                "response": {
                    "players": [
                        {
                            "personaname": " Alpha ",
                            "personastate": "1",
                            "gameextrainfo": "Dota 2",
                        }
                    ]
                }
            },
            "76561198000000000",
            now=123,
        )

        self.assertEqual(
            summary,
            {
                "steamid64": "76561198000000000",
                "personaname": "Alpha",
                "personastate": 1,
                "gameextrainfo": "Dota 2",
                "fetched_at": 123.0,
            },
        )

    def test_get_profile_status_label_prefers_current_game_then_persona_state(self):
        self.assertEqual(get_profile_status_label({"gameextrainfo": "Dota 2", "personastate": 1}), "Playing Dota 2")
        self.assertEqual(get_profile_status_label({"personastate": "3"}), "Away")
        self.assertEqual(get_profile_status_label({"personastate": "bad"}), "")

    def test_parse_owned_games_payload_returns_app_ids_and_playtimes(self):
        owned_app_ids, playtimes = parse_owned_games_payload(
            {
                "response": {
                    "games": [
                        {"appid": 570, "playtime_forever": "11290"},
                        {"appid": "10", "playtime_forever": "bad"},
                        {"appid": ""},
                        "invalid",
                    ]
                }
            }
        )

        self.assertEqual(owned_app_ids, {"570", "10"})
        self.assertEqual(playtimes, {"570": 11290, "10": 0})

    def test_normalize_owned_games_cache_payload_coerces_cache_shapes(self):
        normalized = normalize_owned_games_cache_payload(
            {
                "last_attempt": "10.5",
                "timestamp": "bad",
                "public_profile": True,
                "steamid64": 76561198000000000,
                "owned_app_ids": [570, "", "10"],
                "owned_game_playtimes": {"570": "11290", "10": "bad", "": 5},
            }
        )

        self.assertEqual(normalized["last_attempt"], 10.5)
        self.assertEqual(normalized["last_sync"], 0.0)
        self.assertTrue(normalized["public_profile"])
        self.assertEqual(normalized["steamid64"], "76561198000000000")
        self.assertEqual(normalized["owned_app_ids"], {"570", "10"})
        self.assertEqual(normalized["owned_game_playtimes"], {"570": 11290, "10": 0})

    def test_build_owned_games_cache_payload_sorts_app_ids(self):
        payload = build_owned_games_cache_payload(
            1,
            2,
            True,
            "76561198000000000",
            {"570", "10"},
            {"570": 11290},
        )

        self.assertEqual(payload["owned_app_ids"], ["10", "570"])
        self.assertEqual(payload["timestamp"], 2)

    def test_owned_games_cache_state_helpers_resolve_owned_not_owned_and_unknown(self):
        self.assertTrue(is_owned_games_cache_fresh(True, "steamid", "steamid", 10, 20, lambda timestamp, ttl: True))
        self.assertFalse(is_owned_games_cache_fresh(False, "steamid", "steamid", 10, 20, lambda timestamp, ttl: True))
        self.assertFalse(is_owned_games_cache_fresh(True, "other", "steamid", 10, 20, lambda timestamp, ttl: True))
        self.assertEqual(get_owned_app_state("570", "steamid", "steamid", {"570"}, cache_is_fresh=False), "owned")
        self.assertEqual(get_owned_app_state("10", "steamid", "steamid", {"570"}, cache_is_fresh=True), "not_owned")
        self.assertEqual(get_owned_app_state("10", "steamid", "steamid", {"570"}, cache_is_fresh=False), "unknown")

    def test_should_schedule_owned_games_refresh_respects_force_retry_and_fresh_cache(self):
        cache_checks = []

        self.assertTrue(should_schedule_owned_games_refresh(True, 100, 99, 600, True))
        self.assertFalse(
            should_schedule_owned_games_refresh(
                False,
                100,
                99,
                600,
                lambda: cache_checks.append("checked") or False,
            )
        )
        self.assertEqual(cache_checks, [])
        self.assertFalse(should_schedule_owned_games_refresh(False, 1000, 0, 600, True))
        self.assertTrue(should_schedule_owned_games_refresh(False, 1000, 0, 600, False))

    def test_fetch_owned_games_refresh_result_wraps_success_and_expected_errors(self):
        class TimeoutError(Exception):
            pass

        class HTTPError(Exception):
            pass

        urllib3_module = SimpleNamespace(exceptions=SimpleNamespace(TimeoutError=TimeoutError, HTTPError=HTTPError))

        result = fetch_owned_games_refresh_result(
            lambda _api_key, _steamid64, timeout=3: ({"570"}, {"570": 10}),
            "KEY",
            "steamid",
            urllib3_module,
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["owned_app_ids"], {"570"})
        self.assertFalse(result["should_log_error"])

        timeout_result = fetch_owned_games_refresh_result(
            lambda *_args, **_kwargs: (_ for _ in ()).throw(TimeoutError("slow")),
            "KEY",
            "steamid",
            urllib3_module,
        )

        self.assertFalse(timeout_result["success"])
        self.assertFalse(timeout_result["should_log_error"])

        unexpected_result = fetch_owned_games_refresh_result(
            lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
            "KEY",
            "steamid",
            urllib3_module,
        )

        self.assertFalse(unexpected_result["success"])
        self.assertTrue(unexpected_result["should_log_error"])
        self.assertEqual(
            build_owned_games_refresh_log_details("steamid", {"10", "570"}, True),
            "steamid64=steamid count=2 success=True",
        )

    def test_fetch_owned_app_ids_normalizes_api_key_and_uses_expected_request(self):
        calls = []

        def http_get(url, **kwargs):
            calls.append((url, kwargs))
            payload = {"response": {"games": [{"appid": 570, "playtime_forever": 10}]}}
            return SimpleNamespace(data=json.dumps(payload).encode("utf-8"))

        owned_app_ids, playtimes = fetch_owned_app_ids(
            " raw-key ",
            "76561198000000000",
            http_get,
            normalize_api_key=lambda value: str(value).strip().upper(),
            timeout=7,
        )

        self.assertEqual(owned_app_ids, {"570"})
        self.assertEqual(playtimes, {"570": 10})
        self.assertIn("key=RAW-KEY", calls[0][0])
        self.assertIn("include_played_free_games=1", calls[0][0])
        self.assertEqual(calls[0][1]["timeout"], 7)
        self.assertEqual(calls[0][1]["headers"]["User-Agent"], "Mozilla/5.0")

    def test_fetch_player_summary_uses_expected_request_and_parser(self):
        calls = []

        def http_get(url, **kwargs):
            calls.append((url, kwargs))
            payload = {"response": {"players": [{"personaname": "Beta", "personastate": 0}]}}
            return SimpleNamespace(data=json.dumps(payload).encode("utf-8"))

        summary = fetch_player_summary(
            "KEY",
            "76561198000000001",
            http_get,
            timeout=2,
            now=456,
        )

        self.assertEqual(summary["personaname"], "Beta")
        self.assertEqual(summary["fetched_at"], 456.0)
        self.assertIn("GetPlayerSummaries", calls[0][0])
        self.assertEqual(calls[0][1]["timeout"], 2)

    def test_parse_avatar_frame_payload_normalizes_relative_image_url(self):
        frame_data = parse_avatar_frame_payload(
            {
                "response": {
                    "avatar_frame": {
                        "communityitemid": "123",
                        "image_small": "items/avatarframes/frame.png",
                        "item_title": "Frame",
                    }
                }
            }
        )

        self.assertEqual(frame_data["communityitemid"], "123")
        self.assertEqual(
            frame_data["image_url"],
            "https://shared.fastly.steamstatic.com/community_assets/images/items/avatarframes/frame.png",
        )
        self.assertEqual(frame_data["name"], "Frame")
        self.assertEqual(normalize_avatar_frame_image_url("https://example.test/frame.png"), "https://example.test/frame.png")

    def test_avatar_frame_cache_helpers_return_cached_path_or_no_frame_state(self):
        class ExistingPath:
            def __init__(self, parts=None):
                self.parts = list(parts or [])

            def __truediv__(self, child):
                return ExistingPath(self.parts + [child])

            def exists(self):
                return True

            def __eq__(self, other):
                return isinstance(other, ExistingPath) and self.parts == other.parts

        frame_path, no_frame = get_cached_avatar_frame_state(
            {"steamid64": "steamid", "timestamp": 100, "image_name": "frame.png"},
            "steamid",
            ExistingPath(),
            now=110,
        )

        self.assertEqual(frame_path, ExistingPath(["frame.png"]))
        self.assertFalse(no_frame)

        frame_path, no_frame = get_cached_avatar_frame_state(
            {"steamid64": "steamid", "timestamp": 100, "no_frame": True},
            "steamid",
            ExistingPath(),
            now=110,
        )

        self.assertIsNone(frame_path)
        self.assertTrue(no_frame)
        self.assertEqual(build_no_avatar_frame_cache_entry("steamid", now=200)["timestamp"], 200.0)
        self.assertEqual(
            build_avatar_frame_cache_entry(
                "steamid",
                {"communityitemid": "123", "image_url": "https://example.test/frame.png", "name": "Frame"},
                "frame.png",
                now=300,
            ),
            {
                "steamid64": "steamid",
                "timestamp": 300.0,
                "communityitemid": "123",
                "image_name": "frame.png",
                "image_url": "https://example.test/frame.png",
                "frame_name": "Frame",
            },
        )


if __name__ == "__main__":
    unittest.main()
