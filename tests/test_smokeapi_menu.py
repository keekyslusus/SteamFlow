import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from steamflow.menu import get_game_context_menu_entries


def build_entries(**overrides):
    values = {
        "app_id": "730",
        "name": "Counter-Strike 2",
        "install_path": "C:/Games/CS2",
        "is_owned": True,
        "refund_state": "",
        "default_icon": "steam",
        "steamdb_icon": "steamdb",
        "buy_icon": "buy",
        "csrin_icon": "csrin",
        "guides_icon": "guides",
        "discussions_icon": "discussions",
        "screenshot_icon": "screenshots",
        "refund_icon": "refund",
        "properties_icon": "properties",
        "smokeapi_icon": "smokeapi",
        "location_icon": "location",
        "download_icon": "download",
        "trash_icon": "trash",
    }
    values.update(overrides)
    return get_game_context_menu_entries(**values)


class SmokeAPIMenuTests(unittest.TestCase):
    def test_no_detected_action_adds_no_smoke_entry(self):
        entries = build_entries(smokeapi_action="")

        self.assertFalse(any("SmokeAPI" in entry["title"] for entry in entries))

    def test_install_action_uses_experimental_title_smokeapi_icon_and_parameters(self):
        entries = build_entries(smokeapi_action="install", smokeapi_safety="clean")

        entry = next(entry for entry in entries if entry["method"] == "install_smokeapi")
        self.assertIn("[experimental]", entry["title"])
        self.assertEqual(entry["icon"], "smokeapi")
        self.assertEqual(entry["parameters"], ["730", "C:/Games/CS2", "Counter-Strike 2"])

    def test_smoke_action_appears_after_properties_and_before_file_actions(self):
        entries = build_entries(smokeapi_action="install", smokeapi_safety="clean")

        methods = [entry["method"] for entry in entries]
        self.assertLess(
            methods.index("open_steam_game_properties_page"),
            methods.index("install_smokeapi"),
        )
        self.assertLess(
            methods.index("install_smokeapi"),
            methods.index("open_local_files"),
        )

    def test_install_action_warns_when_anti_cheat_is_detected(self):
        entries = build_entries(
            smokeapi_action="install",
            smokeapi_safety="risk",
            smokeapi_signals=("Easy Anti-Cheat",),
        )

        entry = next(entry for entry in entries if entry["method"] == "install_smokeapi")
        self.assertIn("anti-cheat detected", entry["subtitle"])
        self.assertIn("Easy Anti-Cheat", entry["subtitle"])

    def test_remove_action_is_exclusive(self):
        entries = build_entries(smokeapi_action="remove")

        methods = [entry["method"] for entry in entries]
        entry = next(entry for entry in entries if entry["method"] == "remove_smokeapi")
        self.assertIn("remove_smokeapi", methods)
        self.assertNotIn("install_smokeapi", methods)
        self.assertEqual(entry["icon"], "smokeapi")

    def test_smoke_action_requires_local_game_and_app_id(self):
        no_path = build_entries(install_path=None, smokeapi_action="install")
        no_app = build_entries(app_id="", smokeapi_action="install")

        self.assertFalse(any(entry["method"] == "install_smokeapi" for entry in no_path))
        self.assertFalse(any(entry["method"] == "install_smokeapi" for entry in no_app))


if __name__ == "__main__":
    unittest.main()
