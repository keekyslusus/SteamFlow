import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LIB_PATH = PROJECT_ROOT / "lib"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(LIB_PATH) not in sys.path:
    sys.path.insert(0, str(LIB_PATH))

from steamflow.menu import get_game_context_menu_entries, get_refund_menu_copy


ICON = "icon"


class MenuTests(unittest.TestCase):
    def test_refund_menu_copy_uses_likely_wording(self):
        title, subtitle = get_refund_menu_copy("likely", "NEEDY GIRL OVERDOSE")

        self.assertEqual(title, "Support: Open Refund Page")
        self.assertIn("Likely eligible", subtitle)
        self.assertIn("NEEDY GIRL OVERDOSE", subtitle)

    def test_refund_menu_copy_uses_unclear_wording(self):
        title, subtitle = get_refund_menu_copy("unclear", "NEEDY GIRL OVERDOSE")

        self.assertEqual(title, "Support: Check Refund Options")
        self.assertIn("Eligibility unclear", subtitle)

    def test_game_context_menu_includes_refund_only_for_local_games_with_refund_state(self):
        entries = get_game_context_menu_entries(
            app_id="1451940",
            name="NEEDY GIRL OVERDOSE",
            install_path="C:/Games/Needy",
            is_owned=False,
            refund_state="likely",
            default_icon=ICON,
            steamdb_icon=ICON,
            guides_icon=ICON,
            discussions_icon=ICON,
            screenshot_icon=ICON,
            refund_icon=ICON,
            properties_icon=ICON,
            location_icon=ICON,
            download_icon=ICON,
            trash_icon=ICON,
        )

        titles = [entry["title"] for entry in entries]
        self.assertIn("Support: Open Refund Page", titles)
        self.assertIn("Files: Uninstall Game", titles)

    def test_game_context_menu_hides_refund_for_store_results(self):
        entries = get_game_context_menu_entries(
            app_id="1451940",
            name="NEEDY GIRL OVERDOSE",
            install_path=None,
            is_owned=False,
            refund_state="likely",
            default_icon=ICON,
            steamdb_icon=ICON,
            guides_icon=ICON,
            discussions_icon=ICON,
            screenshot_icon=ICON,
            refund_icon=ICON,
            properties_icon=ICON,
            location_icon=ICON,
            download_icon=ICON,
            trash_icon=ICON,
        )

        titles = [entry["title"] for entry in entries]
        self.assertNotIn("Support: Open Refund Page", titles)
        self.assertNotIn("Files: Uninstall Game", titles)

    def test_game_context_menu_includes_install_for_owned_store_results(self):
        entries = get_game_context_menu_entries(
            app_id="570",
            name="Dota 2",
            install_path=None,
            is_owned=True,
            refund_state="",
            default_icon=ICON,
            steamdb_icon=ICON,
            guides_icon=ICON,
            discussions_icon=ICON,
            screenshot_icon=ICON,
            refund_icon=ICON,
            properties_icon=ICON,
            location_icon=ICON,
            download_icon=ICON,
            trash_icon=ICON,
        )

        titles = [entry["title"] for entry in entries]
        self.assertIn("Library: Install Game", titles)
        self.assertNotIn("Files: Uninstall Game", titles)


if __name__ == "__main__":
    unittest.main()
