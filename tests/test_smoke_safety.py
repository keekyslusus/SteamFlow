import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from steamflow.smoke_safety import (
    get_cached_safety,
    scan_and_cache_safety,
    scan_anti_cheat,
)


class SmokeSafetyTests(unittest.TestCase):
    def test_scan_detects_easy_anti_cheat_directory(self):
        with TemporaryDirectory() as temp_dir:
            game = Path(temp_dir)
            (game / "EasyAntiCheat").mkdir()

            result = scan_anti_cheat(game, now=100)

            self.assertTrue(result.risk)
            self.assertEqual(result.signals, ("Easy Anti-Cheat",))

    def test_scan_detects_battleye_file_glob(self):
        with TemporaryDirectory() as temp_dir:
            game = Path(temp_dir)
            nested = game / "bin"
            nested.mkdir()
            (nested / "BEClient_x64.dll").write_bytes(b"")

            result = scan_anti_cheat(game)

            self.assertTrue(result.risk)
            self.assertIn("BattlEye", result.signals)

    def test_scan_detects_ea_anticheat_files(self):
        markers = (
            "EAAntiCheat.GameServiceLauncher.dll",
            "EAAntiCheat.GameServiceLauncher.exe",
            "EAAntiCheat.Installer.exe",
        )
        for marker in markers:
            with self.subTest(marker=marker), TemporaryDirectory() as temp_dir:
                game = Path(temp_dir)
                (game / marker).write_bytes(b"")

                result = scan_anti_cheat(game)

                self.assertTrue(result.risk)
                self.assertEqual(result.signals, ("EA AntiCheat",))

    def test_scan_detects_netease_anticheat_files(self):
        markers = (
            "NeacClient.exe",
            "FragNeacClient.exe",
            "NSHNeacClient.exe",
        )
        for marker in markers:
            with self.subTest(marker=marker), TemporaryDirectory() as temp_dir:
                nested = Path(temp_dir) / "game" / "bin"
                nested.mkdir(parents=True)
                (nested / marker).write_bytes(b"")

                result = scan_anti_cheat(temp_dir)

                self.assertTrue(result.risk)
                self.assertEqual(result.signals, ("NetEase AntiCheat Experts",))

    def test_scan_detects_anticheatexpert_markers(self):
        markers = (
            ("directory", "AntiCheatExpert"),
            ("file", "ACE-Service64.exe"),
            ("file", "ACE-Setup64.exe"),
        )
        for marker_type, marker in markers:
            with self.subTest(marker=marker), TemporaryDirectory() as temp_dir:
                nested = Path(temp_dir) / "Game" / "Binaries" / "Win64"
                nested.mkdir(parents=True)
                marker_path = nested / marker
                if marker_type == "directory":
                    marker_path.mkdir()
                else:
                    marker_path.write_bytes(b"")

                result = scan_anti_cheat(temp_dir)

                self.assertTrue(result.risk)
                self.assertEqual(result.signals, ("AntiCheatExpert",))

    def test_scan_detects_anybrain_anticheat_installer(self):
        with TemporaryDirectory() as temp_dir:
            installers = Path(temp_dir) / "Installers"
            installers.mkdir()
            (installers / "AntiCheatInstaller.exe").write_bytes(b"")

            result = scan_anti_cheat(temp_dir)

            self.assertTrue(result.risk)
            self.assertEqual(result.signals, ("AnyBrain AntiCheat",))

    def test_scan_empty_tree_is_clean(self):
        with TemporaryDirectory() as temp_dir:
            result = scan_anti_cheat(temp_dir)

            self.assertFalse(result.risk)
            self.assertEqual(result.signals, ())

    def test_scan_stops_after_first_anti_cheat_signal(self):
        walked_directories = iter(
            [
                ("game", ["EasyAntiCheat"], []),
                ("game/deep", [], ["BEClient_x64.dll"]),
            ]
        )
        with TemporaryDirectory() as temp_dir:
            with patch("steamflow.smoke_safety.os.walk", return_value=walked_directories):
                result = scan_anti_cheat(temp_dir)

        self.assertEqual(result.signals, ("Easy Anti-Cheat",))
        self.assertEqual(list(walked_directories), [("game/deep", [], ["BEClient_x64.dll"])])

    def test_cache_hit_requires_same_path_signature(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            game = root / "game"
            game.mkdir()
            cache_file = root / "cache.json"
            scan_and_cache_safety(cache_file, "730", game, now=100)

            cached = get_cached_safety(cache_file, "730", game, now=101)
            (game / "new-file.txt").write_text("changed", encoding="utf-8")
            invalidated = get_cached_safety(cache_file, "730", game, now=102)

            self.assertIsNotNone(cached)
            self.assertIsNone(invalidated)

    def test_cache_entry_expires_at_ttl(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            game = root / "game"
            game.mkdir()
            cache_file = root / "cache.json"
            scan_and_cache_safety(cache_file, "730", game, now=100)

            self.assertIsNone(
                get_cached_safety(cache_file, "730", game, ttl_seconds=10, now=111)
            )


if __name__ == "__main__":
    unittest.main()
