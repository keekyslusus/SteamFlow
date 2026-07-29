import json
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LIB_PATH = PROJECT_ROOT / "lib"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(LIB_PATH) not in sys.path:
    sys.path.insert(0, str(LIB_PATH))

from steamflow.friend_favorites_service import (
    build_friend_favorites_cache_payload,
    build_friend_favorites_url,
    fetch_friend_favorite_accountids,
    get_cached_friend_favorites,
    is_friend_favorites_cache_fresh,
    normalize_friend_favorites_cache_payload,
    parse_friend_favorites_payload,
)


class Response:
    def __init__(self, payload):
        self.data = json.dumps(payload).encode("utf-8")


class FriendFavoritesServiceTests(unittest.TestCase):
    def test_get_favorites_uses_session_access_token(self):
        url = build_friend_favorites_url("header.payload.signature")

        self.assertIn("IFriendsListService/GetFavorites/v1/", url)
        self.assertIn("access_token=header.payload.signature", url)
        self.assertNotIn("key=", url)

    def test_parses_only_friend_accountids(self):
        accountids = parse_friend_favorites_payload(
            {
                "response": {
                    "favorites": [
                        {"accountid": 123},
                        {"clanid": 456},
                        {"chat_group_id": 789},
                        {"accountid": "123"},
                        {"accountid": "bad"},
                    ]
                }
            }
        )

        self.assertEqual(accountids, {123})

    def test_fetches_and_decodes_favorites(self):
        calls = []

        def http_get(url, timeout, headers):
            calls.append((url, timeout, headers))
            return Response({"response": {"favorites": [{"accountid": 321}]}})

        accountids = fetch_friend_favorite_accountids(
            "header.payload.signature",
            http_get,
            timeout=4,
        )

        self.assertEqual(accountids, {321})
        self.assertEqual(calls[0][1], 4)

    def test_cache_is_normalized_per_owner_and_uses_strict_ttl(self):
        normalized = normalize_friend_favorites_cache_payload(
            {
                "accounts": {
                    "owner-a": {
                        "timestamp": "100",
                        "accountids": ["2", 1, "bad"],
                    },
                    "owner-b": {
                        "timestamp": 50,
                        "accountids": [3],
                    },
                }
            }
        )

        self.assertEqual(get_cached_friend_favorites(normalized, "owner-a"), ({1, 2}, 100.0))
        self.assertEqual(get_cached_friend_favorites(normalized, "owner-b"), ({3}, 50.0))
        self.assertTrue(
            is_friend_favorites_cache_fresh(
                normalized,
                "owner-a",
                ttl_seconds=60,
                now=159,
            )
        )
        self.assertFalse(
            is_friend_favorites_cache_fresh(
                normalized,
                "owner-a",
                ttl_seconds=60,
                now=160,
            )
        )

        payload = build_friend_favorites_cache_payload(normalized)
        self.assertEqual(payload["accounts"]["owner-a"]["accountids"], [1, 2])


if __name__ == "__main__":
    unittest.main()
