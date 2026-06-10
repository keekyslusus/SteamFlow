import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from steamflow.feature_health import (
    feature_enabled,
    get_feature_health_status,
    record_feature_failure,
    record_feature_success,
)
import steamflow.feature_health as feature_health_module


class FeatureHealthTests(unittest.TestCase):
    def test_missing_and_corrupted_cache_default_to_healthy(self):
        with TemporaryDirectory() as temp_dir:
            cache_file = Path(temp_dir) / "cache_feature_health.json"
            self.assertTrue(feature_enabled(cache_file, "download_control", now=100))

            cache_file.write_text("{bad json", encoding="utf-8")
            status = get_feature_health_status(cache_file, "download_control", now=100)

        self.assertEqual(status["state"], "healthy")
        self.assertEqual(status["failures"], 0)

    def test_valid_malformed_entry_uses_defaults_instead_of_raising(self):
        with TemporaryDirectory() as temp_dir:
            cache_file = Path(temp_dir) / "cache_feature_health.json"
            cache_file.write_text(
                json.dumps(
                    {
                        "download_control": {
                            "state": "disabled",
                            "failures": "abc",
                            "last_success": "soon",
                            "last_failure": None,
                            "disabled_until": "later",
                        }
                    }
                ),
                encoding="utf-8",
            )

            status = get_feature_health_status(cache_file, "download_control", now=100)

            self.assertTrue(feature_enabled(cache_file, "download_control", now=100))

        self.assertEqual(status["failures"], 0)
        self.assertEqual(status["last_success"], 0)
        self.assertEqual(status["disabled_until"], 0)

    def test_record_success_resets_failure_state(self):
        with TemporaryDirectory() as temp_dir:
            cache_file = Path(temp_dir) / "cache_feature_health.json"
            record_feature_failure(cache_file, "steam_cart", "error", now=100)

            status = record_feature_success(cache_file, "steam_cart", now=200)

        self.assertEqual(status["state"], "healthy")
        self.assertEqual(status["failures"], 0)
        self.assertEqual(status["last_success"], 200)
        self.assertEqual(status["disabled_until"], 0)

    def test_first_failure_is_suspect_but_enabled(self):
        with TemporaryDirectory() as temp_dir:
            cache_file = Path(temp_dir) / "cache_feature_health.json"

            status = record_feature_failure(cache_file, "download_control", "HTTP 403", reason="clientcomm_rejected", now=100)

            self.assertTrue(feature_enabled(cache_file, "download_control", now=100))

        self.assertEqual(status["state"], "suspect")
        self.assertEqual(status["failures"], 1)
        self.assertEqual(status["last_reason"], "clientcomm_rejected")

    def test_threshold_failures_disable_until_cooldown_expires(self):
        with TemporaryDirectory() as temp_dir:
            cache_file = Path(temp_dir) / "cache_feature_health.json"

            for offset in range(3):
                status = record_feature_failure(
                    cache_file,
                    "download_control",
                    "HTTP 403",
                    reason="clientcomm_rejected",
                    now=100 + offset,
                    cooldown_seconds=60,
                )

            self.assertFalse(feature_enabled(cache_file, "download_control", now=110))
            self.assertTrue(feature_enabled(cache_file, "download_control", now=200))

        self.assertEqual(status["state"], "disabled")
        self.assertEqual(status["disabled_until"], 162)

    def test_written_cache_contains_default_feature_entries(self):
        with TemporaryDirectory() as temp_dir:
            cache_file = Path(temp_dir) / "cache_feature_health.json"
            record_feature_success(cache_file, "steam_session_token", now=100)

            data = json.loads(cache_file.read_text(encoding="utf-8"))

        self.assertIn("steam_session_token", data)
        self.assertIn("download_control", data)
        self.assertIn("steam_cart", data)
        self.assertIn("steam_wishlist", data)

    def test_wishlist_auth_error_classifies_as_wishlist_rejected(self):
        with TemporaryDirectory() as temp_dir:
            cache_file = Path(temp_dir) / "cache_feature_health.json"

            status = record_feature_failure(
                cache_file,
                "steam_wishlist",
                "HTTP 401",
                reason="wishlist_rejected",
                now=100,
            )

            self.assertTrue(feature_enabled(cache_file, "steam_wishlist", now=100))
            self.assertEqual(status["last_reason"], "wishlist_rejected")

    def test_debug_disable_all_fragile_features_overrides_status(self):
        with TemporaryDirectory() as temp_dir:
            cache_file = Path(temp_dir) / "cache_feature_health.json"
            original_value = feature_health_module.DEBUG_DISABLE_ALL_FRAGILE_FEATURES
            feature_health_module.DEBUG_DISABLE_ALL_FRAGILE_FEATURES = True
            try:
                status = get_feature_health_status(cache_file, "steam_wishlist", now=100)
                enabled = feature_enabled(cache_file, "steam_wishlist", now=100)
            finally:
                feature_health_module.DEBUG_DISABLE_ALL_FRAGILE_FEATURES = original_value

        self.assertFalse(enabled)
        self.assertEqual(status["state"], "disabled")
        self.assertEqual(status["last_reason"], "debug_disabled")


if __name__ == "__main__":
    unittest.main()
