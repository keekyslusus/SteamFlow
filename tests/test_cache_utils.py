import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LIB_PATH = PROJECT_ROOT / "lib"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(LIB_PATH) not in sys.path:
    sys.path.insert(0, str(LIB_PATH))

from steamflow.cache_utils import (
    cleanup_app_details_cache_entries,
    cleanup_timestamped_cache_entries,
    get_timestamped_cache_entry_state,
    update_timestamped_cache_entry,
)


class TimestampedCacheTests(unittest.TestCase):
    def test_update_timestamped_cache_entry_normalizes_key_and_payload(self):
        cache = {}

        updated = update_timestamped_cache_entry(cache, 570, {"player_count": 123}, now=100)

        self.assertTrue(updated)
        self.assertEqual(cache, {"570": {"timestamp": 100.0, "player_count": 123}})

    def test_get_timestamped_cache_entry_state_reports_missing_as_stale(self):
        entry, is_fresh = get_timestamped_cache_entry_state({}, "570", ttl_seconds=60)

        self.assertIsNone(entry)
        self.assertFalse(is_fresh)

    def test_cleanup_timestamped_cache_entries_removes_only_expired_entries(self):
        cache = {
            "old": {"timestamp": 10},
            "fresh": {"timestamp": 95},
        }

        changed = cleanup_timestamped_cache_entries(cache, ttl_seconds=50, now=100)

        self.assertTrue(changed)
        self.assertEqual(cache, {"fresh": {"timestamp": 95}})

    def test_cleanup_app_details_cache_entries_uses_success_and_failure_ttls(self):
        cache = {
            "success-old": {"timestamp": 10, "success": True},
            "success-fresh": {"timestamp": 80, "success": True},
            "failure-old": {"timestamp": 80, "success": False},
            "failure-fresh": {"timestamp": 96, "success": False},
        }

        changed = cleanup_app_details_cache_entries(
            cache,
            success_ttl_seconds=50,
            failure_ttl_seconds=10,
            now=100,
        )

        self.assertTrue(changed)
        self.assertEqual(
            cache,
            {
                "success-fresh": {"timestamp": 80, "success": True},
                "failure-fresh": {"timestamp": 96, "success": False},
            },
        )


if __name__ == "__main__":
    unittest.main()
