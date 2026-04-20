import sys
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LIB_PATH = PROJECT_ROOT / "lib"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(LIB_PATH) not in sys.path:
    sys.path.insert(0, str(LIB_PATH))
if "vdf" not in sys.modules:
    sys.modules["vdf"] = SimpleNamespace(load=lambda *_args, **_kwargs: {}, dump=lambda *_args, **_kwargs: None)

from steamflow.local import SteamPluginLocalMixin
from steamflow.ui import SteamPluginUIMixin


class LocalLogicHarness(SteamPluginLocalMixin):
    STATE_FLAG_UPDATE_REQUIRED = 2
    STATE_FLAG_FULLY_INSTALLED = 4
    STATE_FLAG_UPDATE_RUNNING = 256
    STATE_FLAG_UPDATE_PAUSED = 512
    STATE_FLAG_UPDATE_STARTED = 1024

    def __init__(self):
        self.state_lock = threading.RLock()
        self.playtime_minutes = {}
        self.last_played_timestamps = {}
        self.owned_game_playtimes = {}
        self.refund_shortcut_enabled = True
        self.app_details_by_id = {}
        self.ownership_state_by_id = {}
        self.current_account_data_by_id = {}
        self.achievement_progress_by_id = {}
        self.multiple_accounts = False

    def should_offer_refund_shortcut(self):
        return self.refund_shortcut_enabled

    def should_show_achievements(self):
        return True

    def get_app_details_metadata(self, app_id, allow_network_on_miss=True):
        return self.app_details_by_id.get(str(app_id))

    def get_active_account_ownership_state(self, app_id):
        return self.ownership_state_by_id.get(str(app_id), "unknown")

    def has_multiple_known_steam_accounts(self):
        return self.multiple_accounts

    def has_current_account_local_data(self, app_id):
        return self.current_account_data_by_id.get(str(app_id), False)

    def get_local_achievement_progress(self, app_id):
        return self.achievement_progress_by_id.get(str(app_id))

    def log_exception(self, _message):
        return None


class UILogicHarness(SteamPluginUIMixin, LocalLogicHarness):
    pass


class RefundStateTests(unittest.TestCase):
    def setUp(self):
        self.plugin = LocalLogicHarness()

    def test_refund_state_is_likely_for_paid_game_under_two_hours(self):
        self.plugin.playtime_minutes["1451940"] = 54
        self.plugin.app_details_by_id["1451940"] = {"type": "game", "is_free": False}
        self.plugin.current_account_data_by_id["1451940"] = True

        refund_state = self.plugin.get_refund_state_for_local_game("1451940")

        self.assertEqual(refund_state, "likely")

    def test_refund_state_is_unclear_for_paid_game_without_playtime(self):
        self.plugin.app_details_by_id["1451940"] = {"type": "game", "is_free": False}
        self.plugin.current_account_data_by_id["1451940"] = True

        refund_state = self.plugin.get_refund_state_for_local_game("1451940")

        self.assertEqual(refund_state, "unclear")

    def test_refund_state_is_hidden_for_games_over_two_hours(self):
        self.plugin.playtime_minutes["1451940"] = 200
        self.plugin.app_details_by_id["1451940"] = {"type": "game", "is_free": False}

        refund_state = self.plugin.get_refund_state_for_local_game("1451940")

        self.assertEqual(refund_state, "")

    def test_refund_state_is_hidden_for_free_or_non_game_apps(self):
        self.plugin.playtime_minutes["111"] = 54
        self.plugin.playtime_minutes["222"] = 54
        self.plugin.app_details_by_id["111"] = {"type": "game", "is_free": True}
        self.plugin.app_details_by_id["222"] = {"type": "dlc", "is_free": False}

        self.assertEqual(self.plugin.get_refund_state_for_local_game("111"), "")
        self.assertEqual(self.plugin.get_refund_state_for_local_game("222"), "")

    def test_refund_state_is_hidden_without_current_account_data(self):
        self.plugin.playtime_minutes["1451940"] = 54
        self.plugin.app_details_by_id["1451940"] = {"type": "game", "is_free": False}
        self.plugin.current_account_data_by_id["1451940"] = False

        refund_state = self.plugin.get_refund_state_for_local_game("1451940")

        self.assertEqual(refund_state, "")


class LocalAccountNoticeTests(unittest.TestCase):
    def setUp(self):
        self.plugin = LocalLogicHarness()

    def test_notice_is_empty_for_single_account_unknown_ownership(self):
        self.plugin.ownership_state_by_id["10"] = "unknown"
        self.plugin.multiple_accounts = False

        notice = self.plugin.get_local_game_account_notice("10")

        self.assertEqual(notice, "")

    def test_notice_warns_when_active_account_does_not_own_game(self):
        self.plugin.ownership_state_by_id["10"] = "not_owned"
        self.plugin.app_details_by_id["10"] = {"type": "game", "is_free": False}

        notice = self.plugin.get_local_game_account_notice("10")

        self.assertEqual(notice, " | Installed via another account")

    def test_notice_is_hidden_when_current_account_has_local_data(self):
        self.plugin.ownership_state_by_id["570"] = "not_owned"
        self.plugin.app_details_by_id["570"] = {"type": "game", "is_free": False}
        self.plugin.current_account_data_by_id["570"] = True

        notice = self.plugin.get_local_game_account_notice("570")

        self.assertEqual(notice, "")

    def test_notice_is_hidden_for_free_games_when_metadata_is_known(self):
        self.plugin.ownership_state_by_id["570"] = "not_owned"
        self.plugin.app_details_by_id["570"] = {"type": "game", "is_free": True}

        notice = self.plugin.get_local_game_account_notice("570")

        self.assertEqual(notice, "")

    def test_notice_warns_for_multi_account_game_without_current_account_data(self):
        self.plugin.ownership_state_by_id["10"] = "unknown"
        self.plugin.multiple_accounts = True
        self.plugin.current_account_data_by_id["10"] = False

        notice = self.plugin.get_local_game_account_notice("10")

        self.assertEqual(notice, " | No current-account data")


class StateFlagParsingTests(unittest.TestCase):
    def setUp(self):
        self.plugin = LocalLogicHarness()

    def test_parse_state_flags_marks_fully_installed_game_visible(self):
        parsed = self.plugin.parse_state_flags(self.plugin.STATE_FLAG_FULLY_INSTALLED)

        self.assertTrue(parsed["is_visible"])
        self.assertEqual(parsed["label"], "")

    def test_parse_state_flags_marks_update_required_before_install(self):
        parsed = self.plugin.parse_state_flags(self.plugin.STATE_FLAG_UPDATE_REQUIRED)

        self.assertTrue(parsed["is_visible"])
        self.assertEqual(parsed["label"], "Update Required")

    def test_parse_state_flags_marks_queued_update_for_installed_game(self):
        parsed = self.plugin.parse_state_flags(
            self.plugin.STATE_FLAG_FULLY_INSTALLED | self.plugin.STATE_FLAG_UPDATE_REQUIRED
        )

        self.assertTrue(parsed["is_visible"])
        self.assertEqual(parsed["label"], "Update Queued")

    def test_parse_state_flags_marks_paused_update(self):
        parsed = self.plugin.parse_state_flags(self.plugin.STATE_FLAG_UPDATE_PAUSED)

        self.assertTrue(parsed["is_visible"])
        self.assertEqual(parsed["label"], "Update Paused")


class AchievementDisplayTests(unittest.TestCase):
    def setUp(self):
        self.plugin = UILogicHarness()

    def test_zero_progress_is_hidden_without_current_account_data(self):
        self.plugin.achievement_progress_by_id["570"] = (0, 100)
        self.plugin.current_account_data_by_id["570"] = False

        suffix = self.plugin.format_achievement_progress("570")

        self.assertEqual(suffix, "")

    def test_positive_progress_is_still_shown(self):
        self.plugin.achievement_progress_by_id["570"] = (3, 100)
        self.plugin.current_account_data_by_id["570"] = False

        suffix = self.plugin.format_achievement_progress("570")

        self.assertEqual(suffix, " | 3/100")
