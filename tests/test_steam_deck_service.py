import json
import sys
import unittest
import urllib.parse
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LIB_PATH = PROJECT_ROOT / "lib"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(LIB_PATH) not in sys.path:
    sys.path.insert(0, str(LIB_PATH))

from steamflow.steam_deck_service import (
    apply_deck_compatibility_categories,
    build_store_items_url,
    get_latest_deck_playtime,
    get_next_history_check_interval,
    is_deck_activity_recent,
    normalize_app_ids,
    normalize_steam_deck_cache_payload,
    parse_deck_compatibility_categories,
)


DAY = 24 * 60 * 60


class SteamDeckServiceTests(unittest.TestCase):
    def test_latest_deck_playtime_uses_deck_fields_not_linux_activity(self):
        latest = get_latest_deck_playtime(
            [
                {
                    "appid": 1,
                    "last_deck_playtime": 100,
                    "last_linux_playtime": 999,
                },
                {
                    "appid": 2,
                    "last_deck_playtime": 300,
                },
            ]
        )

        self.assertEqual(latest, 300)

    def test_activity_window_is_exactly_fifty_days(self):
        now = 100 * DAY

        self.assertTrue(is_deck_activity_recent(now - 50 * DAY, now=now))
        self.assertFalse(is_deck_activity_recent(now - 50 * DAY - 1, now=now))
        self.assertFalse(is_deck_activity_recent(0, now=now))

    def test_adaptive_intervals_settle_at_seven_days_until_deck_is_detected(self):
        intervals = (DAY, 3 * DAY, 7 * DAY)

        self.assertEqual(get_next_history_check_interval(False, 1, intervals), DAY)
        self.assertEqual(get_next_history_check_interval(False, 2, intervals), 3 * DAY)
        self.assertEqual(get_next_history_check_interval(False, 3, intervals), 7 * DAY)
        self.assertEqual(get_next_history_check_interval(False, 20, intervals), 7 * DAY)
        self.assertEqual(
            get_next_history_check_interval(
                True,
                0,
                intervals,
                detected_interval_seconds=14 * DAY,
            ),
            14 * DAY,
        )

    def test_store_items_url_batches_ids_and_requests_platforms(self):
        url = build_store_items_url(["570", 1245620, "570", "bad"], country_code="kz", language="russian")
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
        input_data = json.loads(query["input_json"][0])

        self.assertEqual(input_data["ids"], [{"appid": 570}, {"appid": 1245620}])
        self.assertEqual(input_data["context"]["country_code"], "KZ")
        self.assertEqual(input_data["context"]["language"], "russian")
        self.assertTrue(input_data["data_request"]["include_platforms"])

    def test_compatibility_parser_and_enrichment_use_normalized_app_ids(self):
        payload = {
            "response": {
                "store_items": [
                    {
                        "appid": 570,
                        "platforms": {"steam_deck_compat_category": 2},
                    },
                    {
                        "appid": 1245620,
                        "platforms": {"steam_deck_compat_category": 3},
                    },
                ]
            }
        }

        categories = parse_deck_compatibility_categories(payload)
        games = apply_deck_compatibility_categories(
            [{"id": 570, "name": "Dota 2"}, {"id": 730, "name": "CS2"}],
            categories,
        )

        self.assertEqual(categories, {"570": 2, "1245620": 3})
        self.assertEqual(games[0]["steam_deck_compat_category"], 2)
        self.assertNotIn("steam_deck_compat_category", games[1])
        self.assertEqual(normalize_app_ids(["570", 570, "0", "-1", None]), ["570"])

    def test_cache_normalizer_keeps_account_and_compatibility_data_bounded(self):
        normalized = normalize_steam_deck_cache_payload(
            {
                "accounts": {
                    "76561198000000000": {
                        "last_deck_playtime": "123",
                        "negative_check_count": "-2",
                    },
                    "invalid": {"last_deck_playtime": 999},
                },
                "compatibility": {
                    "570": {"category": 2, "timestamp": "100"},
                    "730": {"category": 99, "timestamp": 100},
                },
            }
        )

        self.assertEqual(
            set(normalized["accounts"]),
            {"76561198000000000"},
        )
        self.assertEqual(
            normalized["accounts"]["76561198000000000"]["negative_check_count"],
            0,
        )
        self.assertEqual(normalized["compatibility"]["570"]["category"], 2)
        self.assertEqual(normalized["compatibility"]["730"]["category"], 0)


if __name__ == "__main__":
    unittest.main()
