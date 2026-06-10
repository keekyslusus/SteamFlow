import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LIB_PATH = PROJECT_ROOT / "lib"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(LIB_PATH) not in sys.path:
    sys.path.insert(0, str(LIB_PATH))

from steamflow.os_integration import (
    build_hidden_process_kwargs,
    build_hidden_run_kwargs,
    build_steam_run_game_uri,
    build_steam_store_uri,
    open_uri_with_web_fallback,
    resolve_steam_install_path_from_registry,
    start_hidden_process,
)


class OsIntegrationTests(unittest.TestCase):
    def test_builds_steam_uris(self):
        self.assertEqual(build_steam_store_uri("570"), "steam://store/570")
        self.assertEqual(build_steam_run_game_uri("570"), "steam://launch/570/dialog")

    def test_open_uri_with_web_fallback_reports_selected_transport(self):
        opened = []

        self.assertEqual(
            open_uri_with_web_fallback(
                "steam://store/570",
                "https://store.steampowered.com/app/570/",
                startfile=opened.append,
            ),
            "uri",
        )
        self.assertEqual(opened, ["steam://store/570"])

        browser_urls = []
        self.assertEqual(
            open_uri_with_web_fallback(
                "steam://store/570",
                "https://store.steampowered.com/app/570/",
                startfile=lambda _uri: (_ for _ in ()).throw(OSError("no handler")),
                browser_open=browser_urls.append,
            ),
            "web",
        )
        self.assertEqual(browser_urls, ["https://store.steampowered.com/app/570/"])

    def test_resolve_steam_install_path_from_registry_returns_existing_path(self):
        class RegistryKey:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

        class FakeRegistry:
            HKEY_LOCAL_MACHINE = "HKLM"
            HKEY_CURRENT_USER = "HKCU"

            def __init__(self, steam_path):
                self.steam_path = steam_path
                self.opened = []

            def OpenKey(self, hkey, path):
                self.opened.append((hkey, path))
                return RegistryKey()

            def QueryValueEx(self, _key, name):
                self.queried_name = name
                return str(self.steam_path), None

        with TemporaryDirectory() as temp_dir:
            registry = FakeRegistry(Path(temp_dir))

            self.assertEqual(resolve_steam_install_path_from_registry(registry=registry), Path(temp_dir))

        self.assertEqual(registry.queried_name, "InstallPath")

    def test_start_hidden_process_builds_common_popen_kwargs(self):
        calls = []

        start_hidden_process(
            ["python", "worker.py"],
            cwd="C:/plugin",
            popen=lambda *args, **kwargs: calls.append((args, kwargs)),
            platform="linux",
        )

        command = calls[0][0][0]
        kwargs = calls[0][1]
        self.assertEqual(command, ["python", "worker.py"])
        self.assertEqual(kwargs["cwd"], "C:/plugin")
        self.assertTrue(kwargs["start_new_session"])

    def test_build_hidden_process_kwargs_is_empty_off_windows(self):
        startupinfo, creationflags = build_hidden_process_kwargs(platform="linux")

        self.assertIsNone(startupinfo)
        self.assertEqual(creationflags, 0)

    def test_build_hidden_run_kwargs_hides_console_on_windows(self):
        class FakeSubprocess:
            CREATE_NO_WINDOW = 123

        self.assertEqual(
            build_hidden_run_kwargs(platform="win32", subprocess_module=FakeSubprocess),
            {"creationflags": 123},
        )


if __name__ == "__main__":
    unittest.main()
