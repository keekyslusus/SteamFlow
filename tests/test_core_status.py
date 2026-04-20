import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LIB_PATH = PROJECT_ROOT / "lib"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(LIB_PATH) not in sys.path:
    sys.path.insert(0, str(LIB_PATH))

from steamflow.core import SteamPluginCoreMixin


class CoreStatusHarness(SteamPluginCoreMixin):
    class DummyLock:
        def __enter__(self):
            return None

        def __exit__(self, exc_type, exc, tb):
            return False

    state_lock = DummyLock()

    def __init__(self):
        self.active_steamid64 = "76561198000000000"
        self.active_user_details = {"persona_name": "ActiveUser", "account_name": "activeuser"}
        self.owned_api_key_present = False
        self.owned_api_key_bound_steamid64 = None
        self.owned_api_key_persona_name = None
        self.owned_api_key_account_name = None
        self.owned_games_last_sync = 0

    def get_active_steam_user_steamid64(self):
        return self.active_steamid64

    def get_steam_user_details(self, steamid64):
        return dict(self.active_user_details)

    def has_owned_api_key(self):
        return self.owned_api_key_present


class CoreStatusTests(unittest.TestCase):
    def test_status_uses_not_configured_when_key_is_missing(self):
        harness = CoreStatusHarness()

        title, subtitle = harness.get_owned_games_status()

        self.assertEqual(title, "Steam API Not Configured")
        self.assertIn("Steam account features", subtitle)

    def test_status_uses_bound_to_another_account_for_mismatch(self):
        harness = CoreStatusHarness()
        harness.owned_api_key_present = True
        harness.owned_api_key_bound_steamid64 = "76561198000000001"
        harness.owned_api_key_persona_name = "OtherUser"

        title, subtitle = harness.get_owned_games_status()

        self.assertEqual(title, "Steam API Bound to Another Account")
        self.assertIn("OtherUser", subtitle)

    def test_status_uses_connected_when_key_matches_active_account(self):
        harness = CoreStatusHarness()
        harness.owned_api_key_present = True
        harness.owned_api_key_bound_steamid64 = harness.active_steamid64
        harness.owned_api_key_persona_name = "ActiveUser"
        harness.owned_games_last_sync = 1

        title, subtitle = harness.get_owned_games_status()

        self.assertEqual(title, "Steam API Connected")
        self.assertIn("Bound to ActiveUser", subtitle)


if __name__ == "__main__":
    unittest.main()
