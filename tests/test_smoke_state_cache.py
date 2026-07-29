import os
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from steamflow.smoke_state_cache import (
    detect_and_cache_smokeapi_action,
    get_cached_smokeapi_action,
    invalidate_smokeapi_state_cache,
)


class SmokeStateCacheTests(unittest.TestCase):
    def create_layout(self, root):
        payload_dir = Path(root) / "payload"
        payload_dir.mkdir()
        (payload_dir / "steam_api.dll").write_bytes(b"smoke-32")
        (payload_dir / "steam_api64.dll").write_bytes(b"smoke-64")
        game = Path(root) / "game"
        game.mkdir()
        (game / "steam_api.dll").write_bytes(b"original")
        return game, payload_dir, Path(root) / "cache.json"

    def test_detected_action_is_reused_without_another_disk_detection(self):
        with TemporaryDirectory() as temp_dir:
            game, payload_dir, cache_file = self.create_layout(temp_dir)
            action = detect_and_cache_smokeapi_action(
                cache_file, "10", game, payload_dir, now=100
            )

            with patch(
                "steamflow.smoke_state_cache.detect_smokeapi_state",
                side_effect=AssertionError("unexpected detection"),
            ):
                cached = get_cached_smokeapi_action(
                    cache_file, "10", game, payload_dir, now=101
                )

            self.assertEqual(action, "install")
            self.assertEqual(cached, "install")

    def test_install_path_signature_change_invalidates_entry(self):
        with TemporaryDirectory() as temp_dir:
            game, payload_dir, cache_file = self.create_layout(temp_dir)
            detect_and_cache_smokeapi_action(cache_file, "10", game, payload_dir, now=100)
            stat_result = game.stat()
            os.utime(
                game,
                ns=(stat_result.st_atime_ns, stat_result.st_mtime_ns + 1_000_000_000),
            )

            cached = get_cached_smokeapi_action(
                cache_file, "10", game, payload_dir, now=101
            )

            self.assertIsNone(cached)

    def test_payload_change_invalidates_entry(self):
        with TemporaryDirectory() as temp_dir:
            game, payload_dir, cache_file = self.create_layout(temp_dir)
            detect_and_cache_smokeapi_action(cache_file, "10", game, payload_dir, now=100)
            (payload_dir / "steam_api.dll").write_bytes(b"new-smoke")

            cached = get_cached_smokeapi_action(
                cache_file, "10", game, payload_dir, now=101
            )

            self.assertIsNone(cached)

    def test_entry_expires_and_can_be_explicitly_invalidated(self):
        with TemporaryDirectory() as temp_dir:
            game, payload_dir, cache_file = self.create_layout(temp_dir)
            detect_and_cache_smokeapi_action(cache_file, "10", game, payload_dir, now=100)

            expired = get_cached_smokeapi_action(
                cache_file,
                "10",
                game,
                payload_dir,
                ttl_seconds=10,
                now=111,
            )
            invalidate_smokeapi_state_cache(cache_file, "10")
            invalidated = get_cached_smokeapi_action(
                cache_file, "10", game, payload_dir, now=101
            )

            self.assertIsNone(expired)
            self.assertIsNone(invalidated)

    def test_empty_action_is_a_valid_cache_hit(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            payload_dir = root / "payload"
            payload_dir.mkdir()
            game = root / "game"
            game.mkdir()
            cache_file = root / "cache.json"

            detected = detect_and_cache_smokeapi_action(
                cache_file, "10", game, payload_dir, now=100
            )
            cached = get_cached_smokeapi_action(
                cache_file, "10", game, payload_dir, now=101
            )

            self.assertEqual(detected, "")
            self.assertEqual(cached, "")


if __name__ == "__main__":
    unittest.main()
