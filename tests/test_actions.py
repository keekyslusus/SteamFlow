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
        self.join_candidates = []
        self.join_candidate_calls = []

    def _log_action_error(self, message):
        self.errors.append(message)

    def get_joinable_friends_for_app(
        self,
        app_id,
        only_steamid64=None,
        force_refresh=False,
    ):
        self.join_candidate_calls.append(
            (app_id, only_steamid64, force_refresh)
        )
        return list(self.join_candidates)


class ActionsTests(unittest.TestCase):
    def test_open_friend_chat_uses_confirmed_steam_protocol(self):
        opened_urls = []
        original_startfile = os_integration_module.os.startfile
        os_integration_module.os.startfile = opened_urls.append
        try:
            result = ActionsHarness().open_steam_friend_chat("76561199268740725")
        finally:
            os_integration_module.os.startfile = original_startfile

        self.assertEqual(result, "Steam chat opened")
        self.assertEqual(opened_urls, ["steam://friends/message/76561199268740725"])

    def test_open_friend_trade_offer_uses_account_id_in_steam_openurl(self):
        opened_urls = []
        original_startfile = os_integration_module.os.startfile
        os_integration_module.os.startfile = opened_urls.append
        try:
            result = ActionsHarness().open_steam_friend_trade_offer("76561198370456012")
        finally:
            os_integration_module.os.startfile = original_startfile

        self.assertEqual(result, "Steam trade offer opened")
        self.assertEqual(
            opened_urls,
            ["steam://openurl/https://steamcommunity.com/tradeoffer/new/?partner=410190284"],
        )

    def test_open_friend_trade_offer_rejects_invalid_steamid64(self):
        result = ActionsHarness().open_steam_friend_trade_offer("not-an-id")

        self.assertEqual(result, "Invalid Steam friend ID")

    def test_join_friend_game_revalidates_before_opening_protocol(self):
        harness = ActionsHarness()
        harness.join_candidates = [
            {
                "steamid64": "76561199268740725",
                "name": "Alice",
                "app_id": "1782210",
                "lobby_id": "109775244723268201",
            }
        ]
        opened_urls = []
        original_startfile = os_integration_module.os.startfile
        os_integration_module.os.startfile = opened_urls.append
        try:
            result = harness.join_steam_friend_game(
                "76561199268740725",
                "1782210",
            )
        finally:
            os_integration_module.os.startfile = original_startfile

        self.assertEqual(result, "Opening the friend's game in Steam")
        self.assertEqual(
            harness.join_candidate_calls,
            [("1782210", "76561199268740725", True)],
        )
        self.assertEqual(
            opened_urls,
            [
                "steam://joinlobby/1782210/109775244723268201/"
                "76561199268740725"
            ],
        )

    def test_join_friend_game_does_not_open_when_revalidation_expires(self):
        harness = ActionsHarness()
        opened_urls = []
        original_startfile = os_integration_module.os.startfile
        os_integration_module.os.startfile = opened_urls.append
        try:
            result = harness.join_steam_friend_game(
                "76561199268740725",
                "570",
            )
        finally:
            os_integration_module.os.startfile = original_startfile

        self.assertEqual(result, "This friend's game is no longer joinable")
        self.assertEqual(opened_urls, [])

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
