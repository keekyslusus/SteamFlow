import json
import os
import sys
import threading
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LIB_PATH = PROJECT_ROOT / "lib"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(LIB_PATH) not in sys.path:
    sys.path.insert(0, str(LIB_PATH))

from steamflow.app_details import (
    APP_DETAILS_FILE_MAX_AGE_SECONDS,
    MAX_CACHE_FILES,
    AppDetailsFileCache,
    AppDetailsMetadataProvider,
    MetricAppDetailsCache,
    normalize_app_details_metadata,
    parse_app_details_metadata,
)


class AppDetailsMetadataTests(unittest.TestCase):
    def test_parse_app_details_metadata_normalizes_shared_fields(self):
        metadata = parse_app_details_metadata(
            {
                "1451940": {
                    "success": True,
                    "data": {
                        "type": "game",
                        "is_free": 0,
                        "name": "NEEDY GIRL OVERDOSE",
                        "header_image": "header.jpg",
                        "platforms": {"windows": True},
                        "price_overview": {"final": 1699},
                        "release_date": {"coming_soon": False, "date": "Jan 21, 2022"},
                    },
                }
            },
            "1451940",
        )

        self.assertEqual(metadata["type"], "game")
        self.assertFalse(metadata["is_free"])
        self.assertEqual(metadata["capsule_image"], "header.jpg")
        self.assertTrue(metadata["has_price"])
        self.assertEqual(metadata["release_date_text"], "Jan 21, 2022")

    def test_normalize_app_details_metadata_rejects_invalid_details(self):
        self.assertIsNone(normalize_app_details_metadata(None))


class AppDetailsFileCacheTests(unittest.TestCase):
    def test_cache_path_includes_normalized_country_and_app_id(self):
        with TemporaryDirectory() as temp_dir:
            cache = AppDetailsFileCache(Path(temp_dir) / "cache_app_details")

            path = cache.entry_path("1451940", "KZ")

        self.assertEqual(path.parts[-2:], ("kz", "1451940.json"))

    def test_cache_hit_reads_expected_region_only(self):
        with TemporaryDirectory() as temp_dir:
            cache = AppDetailsFileCache(Path(temp_dir) / "cache_app_details")
            cache.write_entry("1451940", {"name": "US"}, success=True, country_code="us")
            cache.write_entry("1451940", {"name": "KZ"}, success=True, country_code="kz")

            self.assertEqual(cache.get_metadata("1451940", "kz"), {"name": "KZ"})

    def test_cache_write_uses_atomic_replace(self):
        with TemporaryDirectory() as temp_dir:
            cache = AppDetailsFileCache(Path(temp_dir) / "cache_app_details")
            cache.write_entry("1451940", {"type": "game"}, success=True)

            cache_path = cache.entry_path("1451940")
            cache_data = json.loads(cache_path.read_text(encoding="utf-8"))
            temp_files = list(cache_path.parent.glob("*.tmp"))

        self.assertEqual(cache_data["metadata"]["type"], "game")
        self.assertEqual(temp_files, [])

    def test_concurrent_writes_for_different_apps_preserve_both_entries(self):
        with TemporaryDirectory() as temp_dir:
            cache = AppDetailsFileCache(Path(temp_dir) / "cache_app_details")
            threads = [
                threading.Thread(target=cache.write_entry, args=(app_id, {"name": app_id}, True))
                for app_id in ("570", "400")
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()

            self.assertEqual(cache.get_metadata("570"), {"name": "570"})
            self.assertEqual(cache.get_metadata("400"), {"name": "400"})

    def test_cleanup_removes_old_entries_and_retains_recent_entries(self):
        with TemporaryDirectory() as temp_dir:
            cache = AppDetailsFileCache(Path(temp_dir) / "cache_app_details")
            cache.write_entry("570", {"name": "old"}, success=True)
            cache.write_entry("400", {"name": "recent"}, success=True)
            now = time.time()
            old_path = cache.entry_path("570")
            os.utime(old_path, (now - APP_DETAILS_FILE_MAX_AGE_SECONDS - 1,) * 2)

            cache.cleanup(now=now, force=True)

            self.assertFalse(old_path.exists())
            self.assertTrue(cache.entry_path("400").exists())

    def test_cleanup_enforces_file_cap_by_removing_oldest_entries(self):
        with TemporaryDirectory() as temp_dir:
            cache = AppDetailsFileCache(Path(temp_dir) / "cache_app_details")
            now = time.time()
            for app_id in range(1, MAX_CACHE_FILES + 2):
                cache.write_entry(str(app_id), {"name": str(app_id)}, success=True)
                path = cache.entry_path(str(app_id))
                os.utime(path, (now + app_id,) * 2)

            cache.cleanup(now=now + MAX_CACHE_FILES + 2, force=True)

            self.assertFalse(cache.entry_path("1").exists())
            self.assertTrue(cache.entry_path(str(MAX_CACHE_FILES + 1)).exists())

    def test_cache_hit_touches_file_no_more_than_once_per_day(self):
        with TemporaryDirectory() as temp_dir:
            cache = AppDetailsFileCache(Path(temp_dir) / "cache_app_details")
            cache.write_entry("570", {"name": "Dota 2"}, success=True)
            path = cache.entry_path("570")
            old_mtime = path.stat().st_mtime - 2 * 24 * 60 * 60
            os.utime(path, (old_mtime, old_mtime))

            with patch("steamflow.app_details.os.utime") as mocked_utime:
                cache.get_metadata("570")
                cache.get_metadata("570")

        mocked_utime.assert_called_once()

    def test_legacy_cache_migration_writes_region_file(self):
        with TemporaryDirectory() as temp_dir:
            cache = AppDetailsFileCache(Path(temp_dir) / "cache_app_details")

            cache.migrate_legacy_entries(
                {
                    "1451940": {
                        "timestamp": 123,
                        "success": True,
                        "metadata": {"type": "game"},
                        "country_code": "KZ",
                    }
                }
            )

            entry = cache.read_entry("1451940", "kz", touch=False)

        self.assertEqual(entry["timestamp"], 123)
        self.assertEqual(entry["metadata"], {"type": "game"})

    def test_provider_uses_cache_before_fetch(self):
        with TemporaryDirectory() as temp_dir:
            cache = MetricAppDetailsCache(Path(temp_dir) / "cache_app_details")
            cache.write_entry("1451940", {"type": "game", "is_free": False}, success=True)
            fetch_calls = []

            provider = AppDetailsMetadataProvider(
                lambda app_id: fetch_calls.append(app_id) or {"type": "dlc"},
                cache=cache,
            )

            metadata = provider.get_metadata("1451940")

        self.assertEqual(metadata, {"type": "game", "is_free": False})
        self.assertEqual(fetch_calls, [])


if __name__ == "__main__":
    unittest.main()
