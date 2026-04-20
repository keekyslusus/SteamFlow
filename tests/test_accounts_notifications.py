import sys
import threading
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
if "vdf" not in sys.modules:
    sys.modules["vdf"] = SimpleNamespace(load=lambda *_args, **_kwargs: {}, dump=lambda *_args, **_kwargs: None)

from steamflow.accounts import SteamPluginAccountsMixin


class AccountsNotificationHarness(SteamPluginAccountsMixin):
    DEFAULT_ICON = "default-icon"

    def __init__(self, steam_path=None):
        self.state_lock = threading.RLock()
        self.steam_path = Path(steam_path) if steam_path else None
        self.messages = []
        self.logged_exceptions = []
        self.active_steamid64 = "76561198000000001"
        self.target_account = {
            "steamid64": "76561198000000000",
            "account_name": "altaccount",
            "persona_name": "Alt User",
        }

    def show_msg(self, title, subtitle, ico_path=""):
        self.messages.append((title, subtitle, ico_path))

    def get_steam_path(self):
        return self.steam_path

    def get_steam_user_details(self, steamid64):
        if str(steamid64) == self.target_account["steamid64"]:
            return dict(self.target_account)
        return {}

    def get_active_steam_user_steamid64(self):
        return self.active_steamid64

    def start_steam_switch_worker(self, steamid64):
        raise RuntimeError("worker boom")

    def log_exception(self, message):
        self.logged_exceptions.append(message)


class AccountsNotificationTests(unittest.TestCase):
    def test_switch_account_shows_notification_when_steam_is_missing(self):
        harness = AccountsNotificationHarness()

        result = harness.switch_steam_account("76561198000000000")

        self.assertEqual(result, "Steam installation not found")
        self.assertEqual(harness.messages[-1][0], "Steam Switch Failed")

    def test_switch_account_shows_notification_when_worker_start_fails(self):
        with TemporaryDirectory() as temp_dir:
            harness = AccountsNotificationHarness(temp_dir)

            result = harness.switch_steam_account("76561198000000000")

        self.assertIn("Failed to start Steam switch worker", result)
        self.assertEqual(harness.messages[-1][0], "Steam Switch Failed")


if __name__ == "__main__":
    unittest.main()
