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

from steamflow.store_search import (
    build_store_search_url,
    fetch_store_search_games,
    normalize_store_search_item,
    parse_store_search_games,
)


class StoreSearchTests(unittest.TestCase):
    def test_build_store_search_url_encodes_query_and_country(self):
        url = build_store_search_url("final fantasy vii", country_code="jp")

        self.assertIn("term=final+fantasy+vii", url)
        self.assertIn("cc=jp", url)
        self.assertIn("l=en", url)

    def test_normalize_store_search_item_preserves_expected_fields(self):
        item = normalize_store_search_item(
            {
                "type": "app",
                "id": 1462040,
                "name": "FINAL FANTASY VII REMAKE INTERGRADE",
                "platforms": {"windows": True},
                "tiny_image": "capsule.jpg",
                "price": {"final": 6999},
            }
        )

        self.assertEqual(item["id"], 1462040)
        self.assertTrue(item["has_price"])
        self.assertFalse(item["is_free"])

    def test_parse_store_search_games_filters_blacklist_and_limits_before_filtering(self):
        payload = {
            "items": [
                {"type": "app", "id": 1, "name": "Blocked"},
                {"type": "app", "id": 2, "name": "Kept"},
                {"type": "app", "id": 3, "name": "Beyond limit"},
            ]
        }

        games = parse_store_search_games(payload, blacklist={"1"}, max_results=2)

        self.assertEqual([game["id"] for game in games], [2])

    def test_fetch_store_search_games_uses_http_get_and_parser(self):
        calls = []

        def http_get(url, timeout, headers):
            calls.append((url, timeout, headers))
            payload = {"items": [{"type": "app", "id": 570, "name": "Dota 2", "is_free": True}]}
            return SimpleNamespace(data=json.dumps(payload).encode("utf-8"))

        games = fetch_store_search_games(http_get, "dota", country_code="us", max_results=8)

        self.assertEqual(games[0]["name"], "Dota 2")
        self.assertTrue(games[0]["is_free"])
        self.assertEqual(calls[0][1], 0.7)
        self.assertEqual(calls[0][2], {"User-Agent": "Mozilla/5.0"})


if __name__ == "__main__":
    unittest.main()
