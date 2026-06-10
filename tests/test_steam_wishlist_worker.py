import sys
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from steamflow.app_details import AppDetailsFileCache
import steam_wishlist_worker


class SteamWishlistWorkerTests(unittest.TestCase):
    def test_appdetails_cache_requires_matching_country_path(self):
        with TemporaryDirectory() as temp_dir:
            cache = AppDetailsFileCache(Path(temp_dir))
            cache.write_entry("570", {"name": "Dota 2"}, success=True, country_code="us")

            self.assertEqual(cache.get_metadata("570", "us"), {"name": "Dota 2"})
            self.assertIsNone(cache.get_metadata("570", "uz"))

    def test_worker_hydration_writes_shared_appdetails_file(self):
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            with (
                patch.object(steam_wishlist_worker, "APP_DETAILS_CACHE_DIR", temp_path / "cache_app_details"),
                patch.object(steam_wishlist_worker, "LOCK_FILE", temp_path / "worker.lock"),
                patch.object(steam_wishlist_worker, "fetch_app_details", return_value={"name": "Dota 2"}),
                patch.object(sys, "argv", ["steam_wishlist_worker.py", "KZ", "570"]),
            ):
                result = steam_wishlist_worker.main()

            cache = AppDetailsFileCache(temp_path / "cache_app_details")

            self.assertEqual(result, 0)
            self.assertEqual(cache.get_metadata("570", "kz"), {"name": "Dota 2"})

    def test_worker_refreshes_fresh_cache_when_language_mismatches(self):
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            cache = AppDetailsFileCache(temp_path / "cache_app_details")
            cache.write_entry("570", {"name": "Old"}, success=True, country_code="kz", steam_language="en")
            with (
                patch.object(steam_wishlist_worker, "APP_DETAILS_CACHE_DIR", temp_path / "cache_app_details"),
                patch.object(steam_wishlist_worker, "LOCK_FILE", temp_path / "worker.lock"),
                patch.object(steam_wishlist_worker, "fetch_app_details", return_value={"name": "Dota 2"}) as fetch,
                patch.object(sys, "argv", ["steam_wishlist_worker.py", "KZ", "570", "english"]),
            ):
                result = steam_wishlist_worker.main()

            updated_entry = cache.read_entry("570", "kz")

            self.assertEqual(result, 0)
            fetch.assert_called_once()
            self.assertEqual(updated_entry["metadata"], {"name": "Dota 2"})
            self.assertEqual(updated_entry["steam_language"], "english")


if __name__ == "__main__":
    unittest.main()
