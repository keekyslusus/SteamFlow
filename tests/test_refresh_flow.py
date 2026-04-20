import os
import sys
import threading
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock, patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LIB_PATH = PROJECT_ROOT / "lib"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(LIB_PATH) not in sys.path:
    sys.path.insert(0, str(LIB_PATH))
if "vdf" not in sys.modules:
    sys.modules["vdf"] = SimpleNamespace(load=lambda *_args, **_kwargs: {}, dump=lambda *_args, **_kwargs: None)

from steamflow.accounts import SteamPluginAccountsMixin
from steamflow.actions import SteamPluginActionsMixin
from steamflow.local import SteamPluginLocalMixin


class ImmediateThread:
    def __init__(self, target=None, daemon=None):
        self.target = target
        self.daemon = daemon

    def start(self):
        if callable(self.target):
            self.target()


class RefreshFlowHarness(SteamPluginLocalMixin):
    def __init__(self):
        self.state_lock = threading.RLock()
        self.last_update = 0
        self.active_steam_user_id_snapshot = None
        self.installed_games_update_in_progress = False
        self.hidden_games_cache_loaded = False
        self.hidden_app_ids = set()
        self.hidden_collections_path = None
        self.hidden_games_mtime = 0
        self.localconfig_path = None
        self.localconfig_mtime = 0
        self.stats_cache_path = None
        self.playtime_minutes = {}
        self.last_played_timestamps = {}
        self.achievement_progress = {}
        self.achievement_progress_signatures = {}
        self.hidden_games_stale = False
        self.refresh_calls = []
        self.start_refresh_calls = 0
        self.user_state_refresh_calls = 0
        self.current_active_user_id = None
        self.localconfig_path = None
        self.localconfig_mtime = 0
        self.current_localconfig_path = None
        self.current_localconfig_mtime = 0

    def should_hide_hidden_games(self):
        return False

    def hidden_games_cache_is_stale(self):
        return self.hidden_games_stale

    def get_active_steam_user_id(self):
        return self.current_active_user_id

    def get_localconfig_path(self):
        return self.current_localconfig_path

    def _refresh_installed_games_snapshot(self):
        self.refresh_calls.append("refresh")
        with self.state_lock:
            self.installed_games_update_in_progress = False
            self.last_update = time.time()

    def _start_installed_games_refresh(self):
        self.start_refresh_calls += 1
        return True

    def refresh_user_scoped_local_state(self):
        self.user_state_refresh_calls += 1
        with self.state_lock:
            self.active_steam_user_id_snapshot = self.current_active_user_id
            self.localconfig_path = self.current_localconfig_path
            self.localconfig_mtime = self.current_localconfig_mtime
            self.playtime_minutes = {"570": 11290}
            self.last_played_timestamps = {"570": 1776516641}
            self.achievement_progress = {}
            self.achievement_progress_signatures = {}


class InstallActionHarness(SteamPluginActionsMixin):
    def __init__(self):
        self.refresh_requests = []
        self.logged_errors = []
        self.changed_queries = []
        self.user_keyword = "steam"

    def schedule_installed_games_refresh(self, delay_seconds=0, reset_user_paths=False):
        self.refresh_requests.append((delay_seconds, reset_user_paths))

    def _log_action_error(self, message):
        self.logged_errors.append(message)

    def change_query(self, query, requery=False):
        self.changed_queries.append((query, requery))

    def build_plugin_query(self, *parts):
        suffix = " ".join(str(part).strip() for part in parts if str(part).strip())
        return f"{self.user_keyword} {suffix}".strip()


class SwitchAccountHarness(SteamPluginAccountsMixin):
    def __init__(self, steam_path):
        self.state_lock = threading.RLock()
        self.steam_path = Path(steam_path)
        self.refresh_requests = []
        self.switch_worker_calls = []
        self.logged_exceptions = []
        self.target_user = {
            "steamid64": "76561198000000000",
            "account_name": "alpha",
            "persona_name": "Alpha",
        }
        self.active_steamid64 = "76561198000000001"

    def get_steam_path(self):
        return self.steam_path

    def get_steam_user_details(self, steamid64):
        if str(steamid64) == self.target_user["steamid64"]:
            return dict(self.target_user)
        return {}

    def get_steam_account_label(self, account_data):
        return account_data.get("persona_name") or "Steam account"

    def get_active_steam_user_steamid64(self):
        return self.active_steamid64

    def start_steam_switch_worker(self, steamid64):
        self.switch_worker_calls.append(str(steamid64))

    def schedule_installed_games_refresh(self, delay_seconds=0, reset_user_paths=False):
        self.refresh_requests.append((delay_seconds, reset_user_paths))

    def log_exception(self, message):
        self.logged_exceptions.append(message)


class StaleWhileRevalidateTests(unittest.TestCase):
    def test_update_installed_games_uses_background_refresh_when_snapshot_exists(self):
        plugin = RefreshFlowHarness()
        plugin.last_update = time.time() - 301

        plugin.update_installed_games()

        self.assertEqual(plugin.start_refresh_calls, 1)
        self.assertEqual(plugin.refresh_calls, [])

    def test_update_installed_games_refreshes_synchronously_without_snapshot(self):
        plugin = RefreshFlowHarness()

        plugin.update_installed_games()

        self.assertEqual(plugin.start_refresh_calls, 0)
        self.assertEqual(plugin.refresh_calls, ["refresh"])

    def test_update_installed_games_skips_work_when_snapshot_is_fresh(self):
        plugin = RefreshFlowHarness()
        plugin.last_update = time.time()

        plugin.update_installed_games()

        self.assertEqual(plugin.start_refresh_calls, 0)
        self.assertEqual(plugin.refresh_calls, [])

    def test_update_installed_games_refreshes_user_scoped_state_when_active_account_changes(self):
        plugin = RefreshFlowHarness()
        plugin.last_update = time.time()
        plugin.active_steam_user_id_snapshot = "111"
        plugin.current_active_user_id = "222"

        plugin.update_installed_games()

        self.assertEqual(plugin.user_state_refresh_calls, 1)
        self.assertEqual(plugin.start_refresh_calls, 1)
        self.assertEqual(plugin.playtime_minutes["570"], 11290)
        self.assertEqual(plugin.last_played_timestamps["570"], 1776516641)

    def test_refresh_user_scoped_local_state_if_needed_detects_manual_account_switch(self):
        plugin = RefreshFlowHarness()
        plugin.active_steam_user_id_snapshot = "111"
        plugin.current_active_user_id = "222"

        refreshed = plugin.refresh_user_scoped_local_state_if_needed()

        self.assertTrue(refreshed)
        self.assertEqual(plugin.user_state_refresh_calls, 1)

    def test_refresh_user_scoped_local_state_if_needed_detects_localconfig_change(self):
        with TemporaryDirectory() as temp_dir:
            plugin = RefreshFlowHarness()
            localconfig_path = Path(temp_dir) / "localconfig.vdf"
            localconfig_path.write_text("", encoding="utf-8")
            plugin.current_active_user_id = "222"
            plugin.active_steam_user_id_snapshot = "222"
            plugin.current_localconfig_path = localconfig_path
            plugin.current_localconfig_mtime = localconfig_path.stat().st_mtime
            plugin.localconfig_path = localconfig_path
            plugin.localconfig_mtime = 0

            refreshed = plugin.refresh_user_scoped_local_state_if_needed()

        self.assertTrue(refreshed)
        self.assertEqual(plugin.user_state_refresh_calls, 1)


class ScheduledRefreshTests(unittest.TestCase):
    def test_schedule_installed_games_refresh_invalidates_and_runs_worker(self):
        plugin = RefreshFlowHarness()
        plugin.last_update = 123
        update_calls = []
        plugin.update_installed_games = lambda force=False, allow_background=True: update_calls.append(
            (force, allow_background)
        )

        with patch("steamflow.local.threading.Thread", ImmediateThread), patch("steamflow.local.time.sleep") as mocked_sleep:
            plugin.schedule_installed_games_refresh(delay_seconds=2, reset_user_paths=True)

        self.assertEqual(plugin.last_update, 0)
        self.assertEqual(update_calls, [(True, True)])
        mocked_sleep.assert_called_once_with(2)

    def test_invalidate_installed_games_snapshot_clears_active_user_snapshot(self):
        plugin = RefreshFlowHarness()
        plugin.active_steam_user_id_snapshot = "111"

        plugin.invalidate_installed_games_snapshot(reset_user_paths=True)

        self.assertIsNone(plugin.active_steam_user_id_snapshot)


class InstallAndSwitchSchedulingTests(unittest.TestCase):
    def test_open_steam_uses_games_uri(self):
        plugin = InstallActionHarness()

        with patch.object(os, "startfile", return_value=None) as mocked_startfile:
            result = plugin.open_steam()

        self.assertEqual(result, "Steam opened")
        mocked_startfile.assert_called_once_with(plugin.STEAM_GAMES_URI)

    def test_set_steam_friends_status_uses_protocol_uri(self):
        plugin = InstallActionHarness()

        with patch.object(os, "startfile", return_value=None) as mocked_startfile:
            result = plugin.set_steam_friends_status("invisible")

        self.assertEqual(result, "Steam status set to Invisible")
        mocked_startfile.assert_called_once_with(plugin.STEAM_FRIENDS_STATUS_URIS["invisible"])
        self.assertEqual(plugin.changed_queries, [("steam", True)])

    def test_install_steam_game_schedules_delayed_refresh(self):
        plugin = InstallActionHarness()

        with patch.object(os, "startfile", return_value=None):
            result = plugin.install_steam_game("1451940")

        self.assertIn("Steam install opened", result)
        self.assertEqual(plugin.refresh_requests, [(2, False)])

    def test_switch_steam_account_schedules_delayed_refresh_with_user_reset(self):
        with TemporaryDirectory() as temp_dir:
            steam_path = Path(temp_dir)
            (steam_path / "steam.exe").write_text("", encoding="utf-8")
            plugin = SwitchAccountHarness(steam_path)

            result = plugin.switch_steam_account("76561198000000000")

        self.assertEqual(plugin.switch_worker_calls, ["76561198000000000"])
        self.assertEqual(plugin.refresh_requests, [(5, True)])
        self.assertIn("Switching Steam account to Alpha", result)


if __name__ == "__main__":
    unittest.main()
