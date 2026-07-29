import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from steamflow.smoke_safety import scan_and_cache_safety
from steamflow.smokeapi import SteamPluginSmokeAPIMixin
from steamflow.smokeapi_payload_service import SmokeAPIPayloadDownloadResult


class SmokeAPIHarness(SteamPluginSmokeAPIMixin):
    def __init__(self, plugin_dir):
        self.plugin_dir = Path(plugin_dir)
        self.smoke_safety_cache_file = self.plugin_dir / "cache_smoke_safety.json"
        self.properties_icon = "properties"
        self.settings = {"enable_smokeapi_context_menu": True, "language": "English"}
        self.messages = []
        self.context_menu_cache = {"old": "entry"}

    def get_setting_bool(self, name, default):
        return bool(self.settings.get(name, default))

    def show_msg(self, title, subtitle, icon_path=""):
        self.messages.append((title, subtitle, icon_path))


class WarmSmokeAPIHarness(SmokeAPIHarness):
    def __init__(self, plugin_dir):
        super().__init__(plugin_dir)
        self.started_tasks = []

    def start_daemon_task(self, target, *args, **kwargs):
        self.started_tasks.append((target, args, kwargs))


class SmokeAPIActionsTests(unittest.TestCase):
    def create_game(self, root, original=b"original"):
        game = Path(root) / "game"
        game.mkdir()
        (game / "steam_api.dll").write_bytes(original)
        return game

    def create_payload(self, root, payload=b"smoke"):
        payload_dir = Path(root) / "resources" / "smokeapi"
        payload_dir.mkdir(parents=True)
        (payload_dir / "steam_api.dll").write_bytes(payload)
        return payload_dir

    def test_setting_off_hides_smoke_action(self):
        with TemporaryDirectory() as temp_dir:
            plugin = SmokeAPIHarness(temp_dir)
            plugin.settings["enable_smokeapi_context_menu"] = False
            game = self.create_game(temp_dir)

            state = plugin.get_smokeapi_menu_state("10", game)

            self.assertEqual(state["action"], "")

    def test_cached_anti_cheat_state_drives_warning_menu_state(self):
        with TemporaryDirectory() as temp_dir:
            plugin = SmokeAPIHarness(temp_dir)
            game = self.create_game(temp_dir)
            (game / "EasyAntiCheat").mkdir()
            scan_and_cache_safety(plugin.smoke_safety_cache_file, "10", game)

            state = plugin.get_smokeapi_menu_state("10", game)

            self.assertEqual(state["action"], "install")
            self.assertEqual(state["safety"], "risk")
            self.assertEqual(state["signals"], ("Easy Anti-Cheat",))

    def test_cancelled_anti_cheat_confirmation_does_not_modify_game(self):
        with TemporaryDirectory() as temp_dir:
            plugin = SmokeAPIHarness(temp_dir)
            self.create_payload(temp_dir)
            game = self.create_game(temp_dir)
            (game / "EasyAntiCheat").mkdir()

            with patch(
                "steamflow.smokeapi.inspect_smokeapi_payload",
                return_value=SimpleNamespace(ready=True),
            ), patch(
                "steamflow.smokeapi.show_yes_no_dialog",
                return_value=False,
            ) as dialog:
                result = plugin.install_smokeapi("10", game, "Risky Game")

            self.assertEqual(result, "SmokeAPI action cancelled")
            self.assertEqual((game / "steam_api.dll").read_bytes(), b"original")
            self.assertFalse((game / "steam_api_o.dll").exists())
            self.assertIn("Easy Anti-Cheat", dialog.call_args.args[1])

    def test_confirmed_install_and_remove_use_service_and_toasts(self):
        with TemporaryDirectory() as temp_dir:
            plugin = SmokeAPIHarness(temp_dir)
            self.create_payload(temp_dir)
            game = self.create_game(temp_dir)

            with patch(
                "steamflow.smokeapi.inspect_smokeapi_payload",
                return_value=SimpleNamespace(ready=True),
            ), patch(
                "steamflow.smokeapi.show_yes_no_dialog",
                return_value=True,
            ):
                install_result = plugin.install_smokeapi("10", game, "Test Game")
                remove_result = plugin.remove_smokeapi("10", game, "Test Game")

            self.assertIn("SmokeAPI installed", install_result)
            self.assertIn("SmokeAPI removed", remove_result)
            self.assertEqual((game / "steam_api.dll").read_bytes(), b"original")
            self.assertFalse(plugin.context_menu_cache)
            self.assertEqual(len(plugin.messages), 2)

    def test_declined_payload_download_leaves_original_untouched(self):
        with TemporaryDirectory() as temp_dir:
            plugin = SmokeAPIHarness(temp_dir)
            game = self.create_game(temp_dir)

            with patch("steamflow.smokeapi.show_yes_no_dialog", return_value=False) as dialog:
                result = plugin.install_smokeapi("10", game, "Test Game")

            self.assertEqual(result, "SmokeAPI action cancelled")
            self.assertIn("not included with SteamFlow", dialog.call_args.args[1])
            self.assertEqual((game / "steam_api.dll").read_bytes(), b"original")
            self.assertFalse((game / "steam_api_o.dll").exists())

    def test_downloaded_payload_continues_with_install(self):
        with TemporaryDirectory() as temp_dir:
            plugin = SmokeAPIHarness(temp_dir)
            game = self.create_game(temp_dir)

            def download(payload_dir):
                payload_dir = Path(payload_dir)
                payload_dir.mkdir(parents=True, exist_ok=True)
                (payload_dir / "steam_api.dll").write_bytes(b"smoke")
                return SmokeAPIPayloadDownloadResult(
                    downloaded_files=("steam_api.dll",),
                )

            with patch(
                "steamflow.smokeapi.inspect_smokeapi_payload"
            ) as inspect, patch(
                "steamflow.smokeapi.download_smokeapi_payload",
                side_effect=download,
            ), patch(
                "steamflow.smokeapi.show_yes_no_dialog",
                side_effect=(True, True),
            ) as dialog:
                inspect.return_value.ready = False
                result = plugin.install_smokeapi("10", game, "Test Game")

            self.assertIn("SmokeAPI installed", result)
            self.assertEqual(dialog.call_count, 2)
            self.assertEqual((game / "steam_api.dll").read_bytes(), b"smoke")
            self.assertEqual((game / "steam_api_o.dll").read_bytes(), b"original")

    def test_failed_payload_download_leaves_original_untouched(self):
        with TemporaryDirectory() as temp_dir:
            plugin = SmokeAPIHarness(temp_dir)
            game = self.create_game(temp_dir)

            with patch(
                "steamflow.smokeapi.download_smokeapi_payload",
                return_value=SmokeAPIPayloadDownloadResult(errors=("offline",)),
            ), patch(
                "steamflow.smokeapi.show_yes_no_dialog",
                return_value=True,
            ):
                result = plugin.install_smokeapi("10", game, "Test Game")

            self.assertIn("Could not download or verify", result)
            self.assertEqual((game / "steam_api.dll").read_bytes(), b"original")
            self.assertFalse((game / "steam_api_o.dll").exists())

    def test_library_warm_uses_one_sequential_background_task(self):
        with TemporaryDirectory() as temp_dir:
            plugin = WarmSmokeAPIHarness(temp_dir)
            game_paths = {}
            for app_id in ("10", "20", "30"):
                game = Path(temp_dir) / app_id
                game.mkdir()
                game_paths[app_id] = str(game)

            with patch("steamflow.smokeapi.get_cached_safety", return_value=None):
                plugin.warm_smoke_safety_cache(game_paths)
                plugin.warm_smoke_safety_cache(game_paths)

            self.assertEqual(len(plugin.started_tasks), 1)
            target, args, kwargs = plugin.started_tasks[0]
            with patch("steamflow.smokeapi.scan_and_cache_safety") as scan:
                target(*args, **kwargs)
            self.assertEqual(scan.call_count, 3)


if __name__ == "__main__":
    unittest.main()
