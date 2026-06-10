import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LIB_PATH = PROJECT_ROOT / "lib"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(LIB_PATH) not in sys.path:
    sys.path.insert(0, str(LIB_PATH))

from steamflow.store_collections import (
    normalize_featured_category_item,
    normalize_store_collection_name,
    parse_dynamic_store_ignored_app_ids,
    parse_featured_collection_games,
)


class StoreCollectionsTests(unittest.TestCase):
    def test_normalize_store_collection_name_accepts_supported_names(self):
        self.assertEqual(normalize_store_collection_name("top sellers"), "top_sellers")
        self.assertEqual(normalize_store_collection_name("specials"), "specials")
        self.assertEqual(normalize_store_collection_name("new releases"), "")

    def test_normalize_featured_category_item_maps_price_and_platforms(self):
        item = normalize_featured_category_item(
            {
                "id": 570,
                "name": "Dota 2",
                "final_price": 0,
                "original_price": 0,
                "currency": "USD",
                "small_capsule_image": "https://example.test/capsule.jpg",
                "windows_available": True,
            },
            result_source="specials",
        )

        self.assertEqual(item["type"], "app")
        self.assertEqual(item["id"], 570)
        self.assertEqual(item["price"], {"final": 0, "initial": 0, "currency": "USD"})
        self.assertTrue(item["is_free"])
        self.assertTrue(item["platforms"]["windows"])
        self.assertEqual(item["result_source"], "specials")

    def test_parse_featured_collection_games_filters_blacklist_and_ignored_apps(self):
        payload = {
            "specials": {
                "items": [
                    {"id": 1, "name": "Ignored"},
                    {"id": 2, "name": "Blacklisted"},
                    {"id": 3, "name": "Visible"},
                ]
            }
        }

        games = parse_featured_collection_games(
            payload,
            "specials",
            blacklist={"2"},
            ignored_app_ids={"1"},
            max_results=5,
        )

        self.assertEqual([game["name"] for game in games], ["Visible"])

    def test_parse_dynamic_store_ignored_app_ids_accepts_list_or_dict(self):
        self.assertEqual(
            parse_dynamic_store_ignored_app_ids({"rgIgnoredApps": [10, "20"]}),
            {"10", "20"},
        )
        self.assertEqual(
            parse_dynamic_store_ignored_app_ids({"rgIgnoredApps": {"30": 1}}),
            {"30"},
        )


if __name__ == "__main__":
    unittest.main()
