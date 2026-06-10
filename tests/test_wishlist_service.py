import json
import sys
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

from steamflow.wishlist_service import (
    add_wishlist_cache_item,
    build_wishlist_cache_payload,
    build_wishlist_results_plan,
    collect_unique_wishlist_app_ids,
    fetch_wishlist_items,
    fetch_wishlist_result,
    get_wishlist_fetch_error_message,
    is_wishlist_cache_fresh,
    is_wishlist_worker_running,
    normalize_wishlist_cache_payload,
    normalize_wishlist_items,
    parse_wishlist_payload,
    remove_wishlist_cache_item,
    select_wishlist_prewarm_items,
    sort_wishlist_items,
    start_wishlist_hydration_worker_process,
    wishlist_contains_app_id,
)


class WishlistServiceTests(unittest.TestCase):
    def test_normalize_wishlist_items_coerces_shape_and_skips_invalid_entries(self):
        self.assertEqual(
            normalize_wishlist_items(
                [
                    {"appid": 570, "date_added": "100", "priority": "2"},
                    {"appid": "10", "date_added": "bad", "priority": None},
                    {"appid": ""},
                    "invalid",
                ]
            ),
            [
                {"appid": "570", "date_added": 100, "priority": 2},
                {"appid": "10", "date_added": 0, "priority": 0},
            ],
        )

    def test_fetch_wishlist_items_normalizes_key_and_uses_expected_request(self):
        calls = []

        def http_get(url, **kwargs):
            calls.append((url, kwargs))
            payload = {"response": {"items": [{"appid": 570, "date_added": 100}]}}
            return SimpleNamespace(data=json.dumps(payload).encode("utf-8"))

        items = fetch_wishlist_items(
            " raw-key ",
            "76561198000000000",
            http_get,
            normalize_api_key=lambda value: str(value).strip().upper(),
            timeout=7,
        )

        self.assertEqual(items, [{"appid": "570", "date_added": 100, "priority": 0}])
        self.assertIn("IWishlistService/GetWishlist", calls[0][0])
        self.assertIn("key=RAW-KEY", calls[0][0])
        self.assertEqual(calls[0][1]["timeout"], 7)
        self.assertEqual(calls[0][1]["headers"]["User-Agent"], "Mozilla/5.0")

    def test_parse_wishlist_payload_returns_empty_for_non_list_items(self):
        self.assertEqual(parse_wishlist_payload({"response": {"items": {}}}), [])

    def test_fetch_wishlist_result_wraps_success_and_error(self):
        success = fetch_wishlist_result(
            lambda _api_key, _steamid64, timeout=3: [{"appid": "570"}],
            "KEY",
            "steamid",
        )

        self.assertTrue(success["success"])
        self.assertEqual(success["items"], [{"appid": "570"}])

        error = fetch_wishlist_result(
            lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
            "KEY",
            "steamid",
        )

        self.assertFalse(error["success"])
        self.assertEqual(get_wishlist_fetch_error_message(error["error"]), "boom")
        self.assertEqual(get_wishlist_fetch_error_message(RuntimeError("")), "Steam wishlist request failed")

    def test_wishlist_cache_payload_helpers_normalize_and_build_cache_shape(self):
        normalized = normalize_wishlist_cache_payload(
            {
                "last_attempt": "10.5",
                "timestamp": "bad",
                "steamid64": 76561198000000000,
                "items": [{"appid": 570, "date_added": "100"}],
            }
        )

        self.assertEqual(normalized["last_attempt"], 10.5)
        self.assertEqual(normalized["last_sync"], 0.0)
        self.assertEqual(normalized["steamid64"], "76561198000000000")
        self.assertEqual(normalized["items"], [{"appid": "570", "date_added": 100, "priority": 0}])

        payload = build_wishlist_cache_payload(1, 2, "steamid", normalized["items"])

        self.assertEqual(payload["last_attempt"], 1)
        self.assertEqual(payload["timestamp"], 2)
        self.assertEqual(payload["items"], normalized["items"])

    def test_is_wishlist_cache_fresh_requires_matching_user_and_fresh_timestamp(self):
        self.assertTrue(is_wishlist_cache_fresh("steamid", "steamid", 10, 20, lambda timestamp, ttl: True))
        self.assertFalse(is_wishlist_cache_fresh("", "steamid", 10, 20, lambda timestamp, ttl: True))
        self.assertFalse(is_wishlist_cache_fresh("steamid", "other", 10, 20, lambda timestamp, ttl: True))

    def test_worker_helpers_detect_running_lock_and_build_command(self):
        with TemporaryDirectory() as temp_dir:
            lock_file = Path(temp_dir) / "worker.lock"
            lock_file.write_text("", encoding="utf-8")
            self.assertTrue(is_wishlist_worker_running(lock_file, now=lock_file.stat().st_mtime + 10))

            plugin_dir = Path(temp_dir)
            worker_script = plugin_dir / "steam_wishlist_worker.py"
            worker_script.write_text("", encoding="utf-8")
            calls = []
            country_calls = []

            start_wishlist_hydration_worker_process(
                plugin_dir,
                lambda: country_calls.append("called") or "us",
                [{"appid": "570"}, {"appid": "10"}, {"appid": "570"}],
                python_executable="python",
                popen=lambda *args, **kwargs: calls.append((args, kwargs)),
                platform="linux",
            )

        command = calls[0][0][0]
        kwargs = calls[0][1]
        self.assertEqual(command, ["python", str(worker_script), "us", "570,10", "english"])
        self.assertTrue(kwargs["start_new_session"])
        self.assertEqual(country_calls, ["called"])
        self.assertEqual(collect_unique_wishlist_app_ids([{"appid": "1"}, {"appid": "1"}, {"appid": "2"}]), ["1", "2"])

    def test_worker_process_can_force_retry_cached_failures(self):
        with TemporaryDirectory() as temp_dir:
            plugin_dir = Path(temp_dir)
            worker_script = plugin_dir / "steam_wishlist_worker.py"
            worker_script.write_text("", encoding="utf-8")
            calls = []

            start_wishlist_hydration_worker_process(
                plugin_dir,
                "us",
                [{"appid": "570"}],
                python_executable="python",
                popen=lambda *args, **kwargs: calls.append((args, kwargs)),
                platform="linux",
                force=True,
            )

        self.assertEqual(calls[0][0][0], ["python", str(worker_script), "us", "570", "english", "--force"])

    def test_sort_wishlist_items_orders_newest_first_then_app_id(self):
        sorted_items = sort_wishlist_items([{"appid": "20", "date_added": 1}, {"appid": "10", "date_added": 2}])

        self.assertEqual([item["appid"] for item in sorted_items], ["10", "20"])
        self.assertEqual(select_wishlist_prewarm_items(sorted_items, 1), [{"appid": "10", "date_added": 2}])

    def test_wishlist_cache_mutation_helpers_update_membership(self):
        items = [{"appid": "10", "date_added": 100, "priority": 0}]

        self.assertTrue(wishlist_contains_app_id(items, "10"))
        self.assertFalse(wishlist_contains_app_id(items, "20"))

        added = add_wishlist_cache_item(items, "20", now=200)
        self.assertEqual([item["appid"] for item in added], ["10", "20"])
        self.assertEqual(added[1]["date_added"], 200)
        self.assertEqual(add_wishlist_cache_item(added, "20", now=300), added)

        removed = remove_wishlist_cache_item(added, "10")
        self.assertEqual([item["appid"] for item in removed], ["20"])

    def test_build_wishlist_results_plan_splits_loaded_visible_and_missing_items(self):
        wishlist_items = [
            {"appid": "30", "date_added": 300},
            {"appid": "20", "date_added": 200},
            {"appid": "10", "date_added": 100},
        ]
        metadata_by_app_id = {
            "10": {"name": "Final Fantasy"},
            "20": {"name": "Portal"},
        }

        plan = build_wishlist_results_plan(
            wishlist_items,
            "final",
            lambda app_id: metadata_by_app_id.get(str(app_id)),
            max_results=5,
        )

        self.assertEqual(plan["loaded_count"], 2)
        self.assertEqual(plan["matching_loaded_count"], 1)
        self.assertEqual([item["appid"] for item in plan["missing_items"]], ["30"])
        self.assertEqual([item["appid"] for item in plan["visible_items"]], ["10"])


if __name__ == "__main__":
    unittest.main()
