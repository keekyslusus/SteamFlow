import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LIB_PATH = PROJECT_ROOT / "lib"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(LIB_PATH) not in sys.path:
    sys.path.insert(0, str(LIB_PATH))

from steamflow import os_integration as os_integration_module
from steamflow.actions import SteamPluginActionsMixin


class ActionsHarness(SteamPluginActionsMixin):
    def __init__(self):
        self.errors = []

    def _log_action_error(self, message):
        self.errors.append(message)


class ActionsTests(unittest.TestCase):
    def test_search_csrin_page_uses_phpbb_topic_search_url(self):
        opened_urls = []
        original_open = os_integration_module.webbrowser.open
        os_integration_module.webbrowser.open = opened_urls.append
        try:
            result = ActionsHarness().search_csrin_page("Slay the Spire")
        finally:
            os_integration_module.webbrowser.open = original_open

        self.assertEqual(result, "CS.RIN search opened for Slay the Spire")
        self.assertEqual(
            opened_urls,
            ["https://cs.rin.ru/forum/search.php?keywords=Slay+the+Spire&fid[]=10&sr=topics&sf=titleonly"],
        )

    def test_search_csrin_page_rejects_missing_name(self):
        opened_urls = []
        original_open = os_integration_module.webbrowser.open
        os_integration_module.webbrowser.open = opened_urls.append
        try:
            result = ActionsHarness().search_csrin_page(" ")
        finally:
            os_integration_module.webbrowser.open = original_open

        self.assertEqual(result, "Failed to search CS.RIN: missing game name")
        self.assertEqual(opened_urls, [])


if __name__ == "__main__":
    unittest.main()
