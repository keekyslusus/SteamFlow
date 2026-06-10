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

from steamflow.account_switcher import (
    is_windows_process_running,
    launch_steam_client_executable,
    read_active_steam_user_id_from_registry,
    set_steam_registry_autologin_user,
    start_steam_switch_worker_process,
    terminate_process_tree,
    terminate_steam_processes,
)


class AccountSwitcherTests(unittest.TestCase):
    def test_set_steam_registry_autologin_user_writes_expected_values_and_flushes(self):
        class RegistryKey:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

        class FakeRegistry:
            HKEY_CURRENT_USER = "HKCU"
            REG_SZ = "sz"
            REG_DWORD = "dword"

            def __init__(self):
                self.key = RegistryKey()
                self.created_keys = []
                self.values = []
                self.flushed_keys = []

            def CreateKey(self, hkey, path):
                self.created_keys.append((hkey, path))
                return self.key

            def SetValueEx(self, key, name, reserved, value_type, value):
                self.values.append((key, name, reserved, value_type, value))

            def FlushKey(self, key):
                self.flushed_keys.append(key)

        registry = FakeRegistry()

        set_steam_registry_autologin_user("alice", registry=registry, flush=True)

        self.assertEqual(registry.created_keys, [("HKCU", r"Software\Valve\Steam")])
        self.assertEqual(
            registry.values,
            [
                (registry.key, "AutoLoginUser", 0, "sz", "alice"),
                (registry.key, "RememberPassword", 0, "dword", 1),
            ],
        )
        self.assertEqual(registry.flushed_keys, [registry.key])

    def test_read_active_steam_user_id_from_registry_returns_nonzero_user(self):
        class RegistryKey:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

        class FakeRegistry:
            HKEY_CURRENT_USER = "HKCU"

            def OpenKey(self, hkey, path):
                self.opened_key = (hkey, path)
                return RegistryKey()

            def QueryValueEx(self, _key, name):
                self.queried_name = name
                return "12345", None

        registry = FakeRegistry()

        self.assertEqual(read_active_steam_user_id_from_registry(registry=registry), "12345")
        self.assertEqual(registry.opened_key, ("HKCU", r"SOFTWARE\Valve\Steam\ActiveProcess"))
        self.assertEqual(registry.queried_name, "ActiveUser")

    def test_read_active_steam_user_id_from_registry_ignores_zero_or_errors(self):
        class RegistryKey:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

        class ZeroRegistry:
            HKEY_CURRENT_USER = "HKCU"

            def OpenKey(self, _hkey, _path):
                return RegistryKey()

            def QueryValueEx(self, _key, _name):
                return "0", None

        class BrokenRegistry:
            HKEY_CURRENT_USER = "HKCU"

            def OpenKey(self, _hkey, _path):
                raise OSError("missing")

        self.assertIsNone(read_active_steam_user_id_from_registry(registry=ZeroRegistry()))
        self.assertIsNone(read_active_steam_user_id_from_registry(registry=BrokenRegistry()))

    def test_is_windows_process_running_detects_image_name_in_output(self):
        def runner(_command, **_kwargs):
            return SimpleNamespace(stdout="steam.exe 123", stderr="")

        self.assertTrue(is_windows_process_running("steam.exe", runner=runner))

    def test_is_windows_process_running_hides_tasklist_console_on_windows(self):
        calls = []

        class FakeSubprocess:
            CREATE_NO_WINDOW = 123

        def runner(command, **kwargs):
            calls.append((command, kwargs))
            return SimpleNamespace(stdout="", stderr="")

        is_windows_process_running(
            "steam.exe",
            runner=runner,
            platform="win32",
            subprocess_module=FakeSubprocess,
        )

        self.assertEqual(calls[0][0], ["tasklist", "/FI", "IMAGENAME eq steam.exe"])
        self.assertEqual(calls[0][1]["creationflags"], 123)

    def test_terminate_process_tree_runs_taskkill_when_process_is_running(self):
        calls = []
        running = {"value": True}

        def runner(command, **_kwargs):
            calls.append(command)
            running["value"] = False
            return SimpleNamespace(stdout="", stderr="", returncode=0)

        terminate_process_tree("steam.exe", runner=runner, process_running=lambda _image_name: running["value"])

        self.assertEqual(calls, [["taskkill", "/F", "/T", "/IM", "steam.exe"]])

    def test_terminate_steam_processes_raises_with_remaining_processes_after_timeout(self):
        process_checks = iter([False, True, True])

        with self.assertRaisesRegex(RuntimeError, "Steam processes still running"):
            terminate_steam_processes(
                image_names=("steam.exe",),
                process_running=lambda _image_name: next(process_checks),
                runner=lambda *_args, **_kwargs: SimpleNamespace(stdout="", stderr="", returncode=0),
                sleeper=lambda _seconds: None,
                now=iter([0, 11]).__next__,
                timeout_seconds=10,
            )

    def test_launch_steam_client_executable_uses_popen(self):
        with TemporaryDirectory() as temp_dir:
            steam_path = Path(temp_dir)
            steam_exe = steam_path / "steam.exe"
            steam_exe.write_text("", encoding="utf-8")
            calls = []

            returned_path = launch_steam_client_executable(
                steam_path,
                popen=lambda command, cwd: calls.append((command, cwd)),
                startfile=lambda _path: None,
            )

        self.assertEqual(returned_path, steam_path)
        self.assertEqual(calls, [([str(steam_exe)], str(steam_path))])

    def test_start_steam_switch_worker_process_builds_worker_command(self):
        with TemporaryDirectory() as temp_dir:
            plugin_dir = Path(temp_dir)
            worker_script = plugin_dir / "steam_switch_worker.py"
            worker_script.write_text("", encoding="utf-8")
            calls = []

            start_steam_switch_worker_process(
                plugin_dir,
                "C:/Steam",
                "76561198000000000",
                python_executable="python",
                popen=lambda *args, **kwargs: calls.append((args, kwargs)),
                platform="linux",
            )

        command = calls[0][0][0]
        kwargs = calls[0][1]
        self.assertEqual(command, ["python", str(worker_script), "C:/Steam", "76561198000000000"])
        self.assertTrue(kwargs["start_new_session"])


if __name__ == "__main__":
    unittest.main()
