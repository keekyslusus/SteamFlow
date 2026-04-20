import sys
import unittest
from pathlib import Path
from types import ModuleType

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LIB_PATH = PROJECT_ROOT / "lib"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(LIB_PATH) not in sys.path:
    sys.path.insert(0, str(LIB_PATH))
if "flox" in sys.modules:
    del sys.modules["flox"]
if "flox.clipboard" in sys.modules:
    del sys.modules["flox.clipboard"]
flox_module = ModuleType("flox")
clipboard_module = ModuleType("flox.clipboard")
clipboard_module.get = lambda: ""
flox_module.clipboard = clipboard_module
sys.modules["flox"] = flox_module
sys.modules["flox.clipboard"] = clipboard_module

from steamflow.ui_commands import SteamPluginUICommandsMixin


class UICommandsHarness(SteamPluginUICommandsMixin):
    OWNED_ICON = "owned-icon"
    BROWSER_ICON = "browser-icon"
    CLIPBOARD_ICON = "clipboard-icon"
    COMMUNITY_ICON = "community-icon"
    TRASH_ICON = "trash-icon"
    WISHLIST_ICON = "wishlist-icon"
    ONLINE_ICON = "online-icon"
    OFFLINE_ICON = "offline-icon"
    INVISIBLE_ICON = "invisible-icon"
    WARNING_ICON = "warning-icon"

    def __init__(self):
        self.messages = []
        self.logs = []
        self.saved_key_args = None
        self.removed_key = False
        self.has_api_key = False
        self.user_keyword = "steam"
        self.ensure_startup_initialized_called = 0
        self.active_steamid64 = "76561198000000000"
        self.validation_error = None
        self.validation_result = ({"570"}, {"570": 11290})
        self.wishlist_error = None
        self.active_local_persona_state = 7

    def ensure_startup_initialized(self):
        self.ensure_startup_initialized_called += 1

    def show_msg(self, title, subtitle, ico_path=""):
        self.messages.append((title, subtitle, ico_path))

    def normalize_steam_web_api_key(self, value):
        value = str(value or "").strip()
        return value if len(value) == 32 else ""

    def get_active_steam_user_steamid64(self):
        return self.active_steamid64

    def fetch_owned_app_ids_from_api(self, api_key, steamid64, timeout=5):
        if self.validation_error is not None:
            raise self.validation_error
        return self.validation_result

    def get_steam_user_details(self, steamid64):
        return {"persona_name": "TestUser", "account_name": "testuser"}

    def get_active_local_persona_state(self):
        return self.active_local_persona_state

    def get_local_persona_state_label(self, persona_state):
        labels = {
            0: "Offline",
            1: "Online",
            7: "Invisible",
        }
        return labels.get(persona_state, "")

    def get_local_persona_state_protocol(self, persona_state):
        return {
            0: "offline",
            1: "online",
            7: "invisible",
        }.get(persona_state)

    def save_owned_api_key(self, api_key, steamid64, persona_name=None, account_name=None):
        self.saved_key_args = (api_key, steamid64, persona_name, account_name)

    def save_owned_games_cache(self):
        return None

    def remove_owned_api_key(self):
        self.removed_key = True

    def has_owned_api_key(self):
        return self.has_api_key

    def get_owned_games_status(self):
        return "Steam API Not Configured", "Status subtitle"

    def get_wishlist_items(self):
        return [], self.wishlist_error

    def build_action(self, method, *parameters):
        return {"method": method, "parameters": list(parameters)}

    def build_plugin_query(self, *parts):
        suffix = " ".join(str(part).strip() for part in parts if str(part).strip())
        return f"{self.user_keyword} {suffix}".strip()

    def build_change_query_action(self, query, requery=True, keep_open=True):
        return {
            "method": "change_query",
            "parameters": [str(query), bool(requery)],
            "dontHideAfterAction": bool(keep_open),
        }

    def build_result(self, title, subtitle, icon_path=None, action=None, context_data=None, **extra_fields):
        result = {
            "Title": title,
            "SubTitle": subtitle,
            "IcoPath": icon_path,
            "action": action,
        }
        result.update(extra_fields)
        return result

    def log(self, level, message):
        self.logs.append((level, message))

    class DummyLock:
        def __enter__(self):
            return None

        def __exit__(self, exc_type, exc, tb):
            return False

    state_lock = DummyLock()

    owned_games_last_attempt = 0
    owned_games_last_sync = 0
    owned_games_public_profile = None
    owned_games_steamid64 = None
    owned_app_ids = set()
    owned_game_playtimes = {}
    owned_games_cache_loaded = False


class UICommandsTests(unittest.TestCase):
    def test_help_query_alias_matches_question_mark(self):
        harness = UICommandsHarness()

        self.assertTrue(harness.is_help_query("?"))
        self.assertFalse(harness.is_help_query("api"))

    def test_build_help_results_uses_dynamic_keyword_and_wishlist_unavailable_notice(self):
        harness = UICommandsHarness()
        harness.user_keyword = "st"
        harness.wishlist_error = "Steam API Not Configured"

        results = harness.build_help_results()

        self.assertEqual(
            [result["Title"] for result in results],
            ["st api", "st switch", "st status", "st wishlist"],
        )
        self.assertEqual(
            [result["IcoPath"] for result in results],
            ["owned-icon", "community-icon", "online-icon", "wishlist-icon"],
        )
        self.assertEqual(
            results[0]["action"],
            {"method": "change_query", "parameters": ["st api", True], "dontHideAfterAction": True},
        )
        self.assertIn("Unavailable: Steam API not configured", results[3]["SubTitle"])

    def test_status_query_alias_matches_expected_command(self):
        harness = UICommandsHarness()

        self.assertTrue(harness.is_status_query("status"))
        self.assertTrue(harness.is_status_query("statuses"))
        self.assertFalse(harness.is_status_query("switch"))

    def test_build_status_results_hides_current_protocol_status(self):
        harness = UICommandsHarness()
        harness.active_local_persona_state = 7

        results = harness.build_status_results()

        self.assertEqual(results[0]["Title"], "Current Status: Invisible")
        self.assertEqual(results[0]["IcoPath"], "invisible-icon")
        self.assertEqual(results[0]["SubTitle"], "Choose a different status for TestUser")
        self.assertEqual(
            [result["Title"] for result in results[1:]],
            ["Online", "Offline"],
        )
        self.assertEqual(
            [result["IcoPath"] for result in results[1:]],
            ["online-icon", "offline-icon"],
        )
        self.assertEqual(
            [result["action"] for result in results[1:]],
            [
                {"method": "set_steam_friends_status", "parameters": ["online"]},
                {"method": "set_steam_friends_status", "parameters": ["offline"]},
            ],
        )

    def test_build_status_results_uses_warning_icon_for_unknown_status(self):
        harness = UICommandsHarness()
        harness.active_local_persona_state = None

        results = harness.build_status_results()

        self.assertEqual(results[0]["Title"], "Current Status Unknown")
        self.assertEqual(results[0]["IcoPath"], "warning-icon")
        self.assertEqual(results[0]["SubTitle"], "Choose a status for TestUser")

    def test_build_owned_api_results_without_key_orders_items_for_setup_flow(self):
        harness = UICommandsHarness()

        results = harness.build_owned_api_results()

        self.assertEqual(
            [result["Title"] for result in results],
            [
                "Open Steam Web API Key Page",
                "Save API Key From Clipboard",
                "Steam API Not Configured",
            ],
        )
        self.assertEqual(
            [result["Score"] for result in results],
            [20000, 19999, 19997],
        )

    def test_save_owned_api_key_shows_success_message(self):
        harness = UICommandsHarness()

        from steamflow import ui_commands as module

        original_get_clipboard_text = module.get_clipboard_text
        module.get_clipboard_text = lambda: "A" * 32
        try:
            result = harness.save_owned_api_key_from_clipboard()
        finally:
            module.get_clipboard_text = original_get_clipboard_text

        self.assertIn("saved and bound", result)
        self.assertEqual(harness.messages[-1][0], "Steam API Key Saved")

    def test_save_owned_api_key_shows_error_for_invalid_clipboard(self):
        harness = UICommandsHarness()

        from steamflow import ui_commands as module

        original_get_clipboard_text = module.get_clipboard_text
        module.get_clipboard_text = lambda: "bad-key"
        try:
            result = harness.save_owned_api_key_from_clipboard()
        finally:
            module.get_clipboard_text = original_get_clipboard_text

        self.assertEqual(result, "Clipboard does not contain a valid Steam Web API key")
        self.assertEqual(harness.messages[-1][0], "Steam API Key Not Saved")

    def test_remove_owned_api_key_shows_message(self):
        harness = UICommandsHarness()

        result = harness.remove_owned_api_key_action()

        self.assertEqual(result, "Stored Steam API key removed")
        self.assertTrue(harness.removed_key)
        self.assertEqual(harness.messages[-1][0], "Steam API Key Removed")


if __name__ == "__main__":
    unittest.main()
