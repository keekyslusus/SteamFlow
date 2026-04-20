import sys
import threading
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LIB_PATH = PROJECT_ROOT / "lib"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(LIB_PATH) not in sys.path:
    sys.path.insert(0, str(LIB_PATH))
if "vdf" not in sys.modules:
    sys.modules["vdf"] = SimpleNamespace(load=lambda *_args, **_kwargs: {}, dump=lambda *_args, **_kwargs: None)

from steamflow.accounts import SteamPluginAccountsMixin
from steamflow.local import SteamPluginLocalMixin


class LoginusersCacheHarness(SteamPluginAccountsMixin):
    def __init__(self, steam_path):
        self.state_lock = threading.RLock()
        self.steam_path = Path(steam_path)
        self.loginusers_cache_path = None
        self.loginusers_cache_mtime = 0
        self.loginusers_cache_data = None
        self.logged_exceptions = []

    def log_exception(self, message):
        self.logged_exceptions.append(message)


class AppManifestCacheHarness(SteamPluginLocalMixin):
    STATE_FLAG_UPDATE_REQUIRED = 2
    STATE_FLAG_FULLY_INSTALLED = 4
    STATE_FLAG_UPDATE_RUNNING = 256
    STATE_FLAG_UPDATE_PAUSED = 512
    STATE_FLAG_UPDATE_STARTED = 1024

    def __init__(self):
        self.state_lock = threading.RLock()
        self.appmanifest_cache = {}
        self.logged_exceptions = []

    def log_exception(self, message):
        self.logged_exceptions.append(message)


class LocalconfigStatsHarness(SteamPluginLocalMixin):
    def __init__(self, localconfig_path):
        self.state_lock = threading.RLock()
        self.localconfig_path = Path(localconfig_path)
        self.localconfig_mtime = 0
        self.playtime_minutes = {}
        self.last_played_timestamps = {}
        self.logged_exceptions = []

    def log_exception(self, message):
        self.logged_exceptions.append(message)

    def get_active_steam_user_id(self):
        return "410190284"


class LoginusersCacheTests(unittest.TestCase):
    def test_load_loginusers_data_reuses_cache_until_file_changes(self):
        with TemporaryDirectory() as temp_dir:
            steam_path = Path(temp_dir)
            loginusers_path = steam_path / "config" / "loginusers.vdf"
            loginusers_path.parent.mkdir(parents=True, exist_ok=True)
            loginusers_path.write_text('"users"\n{\n}\n', encoding="utf-8")
            plugin = LoginusersCacheHarness(steam_path)
            load_calls = []

            def fake_load(_file_obj):
                load_calls.append("load")
                return {"users": {"76561198000000000": {"AccountName": "alpha"}}}

            with patch("steamflow.accounts.vdf.load", side_effect=fake_load):
                first = plugin.load_loginusers_data()
                second = plugin.load_loginusers_data()
                time.sleep(0.01)
                loginusers_path.write_text('"users"\n{\n\t"changed"\t"1"\n}\n', encoding="utf-8")
                third = plugin.load_loginusers_data()

            self.assertEqual(first["users"]["76561198000000000"]["AccountName"], "alpha")
            self.assertEqual(second["users"]["76561198000000000"]["AccountName"], "alpha")
            self.assertEqual(third["users"]["76561198000000000"]["AccountName"], "alpha")
            self.assertEqual(load_calls, ["load", "load"])


class AppManifestCacheTests(unittest.TestCase):
    def test_load_appmanifest_data_reuses_cache_until_signature_changes(self):
        with TemporaryDirectory() as temp_dir:
            manifest_path = Path(temp_dir) / "appmanifest_1451940.acf"
            manifest_path.write_text('"AppState"\n{\n}\n', encoding="utf-8")
            plugin = AppManifestCacheHarness()
            load_calls = []

            def fake_load(_file_obj):
                load_calls.append("load")
                return {
                    "AppState": {
                        "appid": "1451940",
                        "name": "NEEDY GIRL OVERDOSE",
                        "installdir": "NEEDY GIRL OVERDOSE",
                        "StateFlags": "4",
                    }
                }

            with patch("steamflow.local.vdf.load", side_effect=fake_load):
                first = plugin.load_appmanifest_data(manifest_path)
                second = plugin.load_appmanifest_data(manifest_path)
                time.sleep(0.01)
                manifest_path.write_text('"AppState"\n{\n\t"extra"\t"1"\n}\n', encoding="utf-8")
                third = plugin.load_appmanifest_data(manifest_path)

            self.assertEqual(first["app_id"], "1451940")
            self.assertEqual(second["app_id"], "1451940")
            self.assertEqual(third["app_id"], "1451940")
            self.assertEqual(load_calls, ["load", "load"])

    def test_cleanup_appmanifest_cache_removes_stale_entries(self):
        plugin = AppManifestCacheHarness()
        plugin.appmanifest_cache = {
            "keep": {"signature": (1, 1), "data": {"app_id": "1"}},
            "drop": {"signature": (2, 2), "data": {"app_id": "2"}},
        }

        plugin.cleanup_appmanifest_cache({"keep"})

        self.assertIn("keep", plugin.appmanifest_cache)
        self.assertNotIn("drop", plugin.appmanifest_cache)


class LocalconfigStatsTests(unittest.TestCase):
    def test_load_localconfig_stats_reads_uppercase_apps_section(self):
        with TemporaryDirectory() as temp_dir:
            localconfig_path = Path(temp_dir) / "localconfig.vdf"
            localconfig_path.write_text("", encoding="utf-8")
            plugin = LocalconfigStatsHarness(localconfig_path)

            with patch(
                "steamflow.local.vdf.load",
                return_value={
                    "UserLocalConfigStore": {
                        "Software": {
                            "Valve": {
                                "Steam": {
                                    "Apps": {
                                        "570": {
                                            "Playtime": "11290",
                                            "LastPlayed": "1776516641",
                                        }
                                    }
                                }
                            }
                        }
                    }
                },
            ):
                playtimes, last_played = plugin.load_localconfig_stats()

        self.assertEqual(playtimes["570"], 11290)
        self.assertEqual(last_played["570"], 1776516641)

    def test_get_active_local_persona_state_reads_friend_store_local_prefs(self):
        with TemporaryDirectory() as temp_dir:
            localconfig_path = Path(temp_dir) / "localconfig.vdf"
            plugin = LocalconfigStatsHarness(localconfig_path)
            localconfig_path.write_text(
                '"UserLocalConfigStore"\n'
                "{\n"
                '\t"friends"\n'
                "\t{\n"
                '\t\t"FriendStoreLocalPrefs_410190284"\t\t"{\\"ePersonaState\\":7,\\"strNonFriendsAllowedToMsg\\":\\"\\"}"\n'
                "\t}\n"
                "}\n",
                encoding="utf-8",
            )

            persona_state = plugin.get_active_local_persona_state()

        self.assertEqual(persona_state, 7)
        self.assertEqual(plugin.get_local_persona_state_label(persona_state), "Invisible")
        self.assertEqual(plugin.get_local_persona_state_protocol(persona_state), "invisible")


if __name__ == "__main__":
    unittest.main()
