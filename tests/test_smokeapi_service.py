import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from steamflow.smokeapi_service import (
    detect_smokeapi_state,
    find_dll_directories,
    install_smokeapi,
    remove_smokeapi,
)
from steamflow import smokeapi_service


class SmokeAPIServiceTests(unittest.TestCase):
    def make_payloads(self, root):
        payload_dir = Path(root) / "payload"
        payload_dir.mkdir()
        (payload_dir / "steam_api.dll").write_bytes(b"smoke-32")
        (payload_dir / "steam_api64.dll").write_bytes(b"smoke-64")
        return payload_dir

    def test_find_dll_directories_returns_every_nested_target(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first = root / "bin"
            second = root / "deep" / "x64"
            ignored = root / "assets"
            first.mkdir()
            second.mkdir(parents=True)
            ignored.mkdir()
            (first / "steam_api.dll").write_bytes(b"original-32")
            (second / "steam_api64.dll").write_bytes(b"original-64")
            (ignored / "readme.txt").write_text("none", encoding="utf-8")

            targets = find_dll_directories(root)

            self.assertEqual(set(targets), {first, second})

    def test_install_backs_up_every_api_writes_payload_and_config(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            payload_dir = self.make_payloads(root)
            target = root / "game" / "bin"
            target.mkdir(parents=True)
            (target / "steam_api.dll").write_bytes(b"original-32")
            (target / "steam_api64.dll").write_bytes(b"original-64")

            result = install_smokeapi(root / "game", payload_dir=payload_dir)

            self.assertTrue(result.success)
            self.assertEqual(result.changed_dlls, 2)
            self.assertEqual((target / "steam_api_o.dll").read_bytes(), b"original-32")
            self.assertEqual((target / "steam_api64_o.dll").read_bytes(), b"original-64")
            self.assertEqual((target / "steam_api.dll").read_bytes(), b"smoke-32")
            self.assertEqual((target / "steam_api64.dll").read_bytes(), b"smoke-64")
            config = json.loads((target / "SmokeAPI.config.json").read_text(encoding="utf-8"))
            self.assertEqual(config["$version"], 4)
            self.assertEqual(config["default_app_status"], "unlocked")

    def test_install_updates_all_target_directories(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            payload_dir = self.make_payloads(root)
            game = root / "game"
            first = game / "bin"
            second = game / "tools"
            first.mkdir(parents=True)
            second.mkdir()
            (first / "steam_api.dll").write_bytes(b"one")
            (second / "steam_api64.dll").write_bytes(b"two")

            result = install_smokeapi(game, payload_dir=payload_dir)

            self.assertTrue(result.success)
            self.assertEqual(result.successful_directories, 2)
            self.assertTrue((first / "SmokeAPI.config.json").is_file())
            self.assertTrue((second / "SmokeAPI.config.json").is_file())

    def test_remove_restores_originals_and_deletes_smoke_files(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            payload_dir = self.make_payloads(root)
            game = root / "game"
            game.mkdir()
            (game / "steam_api.dll").write_bytes(b"original")
            self.assertTrue(install_smokeapi(game, payload_dir=payload_dir).success)
            (game / "SmokeAPI.cache.json").write_text("{}", encoding="utf-8")
            (game / "SmokeAPI.log.log").write_text("log", encoding="utf-8")

            result = remove_smokeapi(game, payload_dir=payload_dir)

            self.assertTrue(result.success)
            self.assertEqual((game / "steam_api.dll").read_bytes(), b"original")
            self.assertFalse((game / "steam_api_o.dll").exists())
            self.assertFalse((game / "SmokeAPI.config.json").exists())
            self.assertFalse((game / "SmokeAPI.cache.json").exists())
            self.assertFalse((game / "SmokeAPI.log.log").exists())

    def test_detection_distinguishes_clean_installed_and_no_targets(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            payload_dir = self.make_payloads(root)
            empty_game = root / "empty"
            clean_game = root / "clean"
            installed_game = root / "installed"
            empty_game.mkdir()
            clean_game.mkdir()
            installed_game.mkdir()
            (clean_game / "steam_api.dll").write_bytes(b"clean")
            (installed_game / "steam_api.dll").write_bytes(b"smoke")
            (installed_game / "steam_api_o.dll").write_bytes(b"original")
            (installed_game / "SmokeAPI.config.json").write_text("{}", encoding="utf-8")

            self.assertEqual(detect_smokeapi_state(empty_game, payload_dir).action, "")
            self.assertEqual(detect_smokeapi_state(clean_game, payload_dir).action, "install")
            self.assertEqual(detect_smokeapi_state(installed_game, payload_dir).action, "remove")

    def test_detection_uses_bundled_payload_hash_with_backup_without_config(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            payload_dir = self.make_payloads(root)
            game = root / "game"
            game.mkdir()
            (game / "steam_api.dll").write_bytes(b"smoke-32")
            (game / "steam_api_o.dll").write_bytes(b"original")

            state = detect_smokeapi_state(game, payload_dir=payload_dir)

            self.assertEqual(state.action, "remove")

    def test_detection_uses_bundled_payload_hash_without_backup_or_config(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            payload_dir = self.make_payloads(root)
            game = root / "game"
            game.mkdir()
            (game / "steam_api.dll").write_bytes(b"smoke-32")

            state = detect_smokeapi_state(game, payload_dir=payload_dir)

            self.assertEqual(state.action, "remove")

    def test_detection_uses_smoke_leftover_with_backup(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            payload_dir = self.make_payloads(root)
            game = root / "game"
            game.mkdir()
            (game / "steam_api.dll").write_bytes(b"unknown-current")
            (game / "steam_api_o.dll").write_bytes(b"original")
            (game / "SmokeAPI.log.log").write_text("log", encoding="utf-8")

            state = detect_smokeapi_state(game, payload_dir=payload_dir)

            self.assertEqual(state.action, "remove")

    def test_payload_hashes_are_memoized_between_detections(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            payload_dir = self.make_payloads(root)
            game = root / "game"
            game.mkdir()
            (game / "steam_api.dll").write_bytes(b"original")

            with patch(
                "steamflow.smokeapi_service._hash_file",
                wraps=smokeapi_service._hash_file,
            ) as hash_file:
                detect_smokeapi_state(game, payload_dir=payload_dir)
                first_detection_calls = hash_file.call_count
                detect_smokeapi_state(game, payload_dir=payload_dir)

            self.assertEqual(first_detection_calls, 3)
            self.assertEqual(hash_file.call_count - first_detection_calls, 1)

    def test_ambiguous_bare_backup_hides_install(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            payload_dir = self.make_payloads(root)
            game = root / "game"
            game.mkdir()
            (game / "steam_api.dll").write_bytes(b"unknown-current")
            (game / "steam_api_o.dll").write_bytes(b"unknown-backup")

            state = detect_smokeapi_state(game, payload_dir=payload_dir)

            self.assertEqual(state.action, "")
            self.assertEqual(state.ambiguous_directories, (game,))

    def test_ambiguous_backup_in_one_directory_hides_install_for_whole_game(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            payload_dir = self.make_payloads(root)
            game = root / "game"
            clean = game / "clean"
            ambiguous = game / "ambiguous"
            clean.mkdir(parents=True)
            ambiguous.mkdir()
            (clean / "steam_api.dll").write_bytes(b"clean")
            (ambiguous / "steam_api64.dll").write_bytes(b"unknown-current")
            (ambiguous / "steam_api64_o.dll").write_bytes(b"unknown-backup")

            state = detect_smokeapi_state(game, payload_dir=payload_dir)
            result = install_smokeapi(game, payload_dir=payload_dir)

            self.assertEqual(state.action, "")
            self.assertIn("ambiguous_backup", result.errors)
            self.assertEqual((clean / "steam_api.dll").read_bytes(), b"clean")
            self.assertFalse((clean / "steam_api_o.dll").exists())

    def test_missing_payload_fails_before_changing_original(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            payload_dir = root / "payload"
            payload_dir.mkdir()
            game = root / "game"
            game.mkdir()
            original = game / "steam_api.dll"
            original.write_bytes(b"original")

            result = install_smokeapi(game, payload_dir=payload_dir)

            self.assertFalse(result.success)
            self.assertIn("payload_missing:steam_api.dll", result.errors)
            self.assertEqual(original.read_bytes(), b"original")
            self.assertFalse((game / "steam_api_o.dll").exists())

    def test_remove_with_missing_backup_leaves_dll_and_reports_it(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            payload_dir = self.make_payloads(root)
            game = root / "game"
            game.mkdir()
            live = game / "steam_api.dll"
            live.write_bytes(b"smoke")
            (game / "SmokeAPI.config.json").write_text("{}", encoding="utf-8")

            result = remove_smokeapi(game, payload_dir=payload_dir)

            self.assertFalse(result.success)
            self.assertTrue(result.backup_missing)
            self.assertTrue(live.exists())
            self.assertTrue((game / "SmokeAPI.config.json").exists())
            self.assertEqual(detect_smokeapi_state(game, payload_dir=payload_dir).action, "remove")

    def test_missing_backup_remove_cannot_reinstall_smoke_as_original(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            payload_dir = self.make_payloads(root)
            game = root / "game"
            game.mkdir()
            (game / "steam_api.dll").write_bytes(b"smoke-32")
            (game / "SmokeAPI.config.json").write_text("{}", encoding="utf-8")

            remove_result = remove_smokeapi(game, payload_dir=payload_dir)
            state_after_remove = detect_smokeapi_state(game, payload_dir=payload_dir)
            reinstall_result = install_smokeapi(game, payload_dir=payload_dir)

            self.assertTrue(remove_result.backup_missing)
            self.assertEqual(state_after_remove.action, "remove")
            self.assertIn("already_installed", reinstall_result.errors)
            self.assertFalse((game / "steam_api_o.dll").exists())


if __name__ == "__main__":
    unittest.main()
