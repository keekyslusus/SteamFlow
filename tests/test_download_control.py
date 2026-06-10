import base64
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LIB_PATH = PROJECT_ROOT / "lib"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(LIB_PATH) not in sys.path:
    sys.path.insert(0, str(LIB_PATH))

from steamflow.download_control import (
    SteamPluginDownloadControlMixin,
)
from steamflow.os_integration import STEAM_GAMES_URI
from steamflow.session_token import (
    STEAM_ACCOUNT_PREFERENCES_URI,
    SteamSessionTokenProvider,
    extract_webapi_tokens_from_bytes,
    get_htmlcache_cache_data_files,
    scan_cache_file_for_webapi_tokens,
    select_best_webapi_token,
)
from steamflow.ui import SteamPluginUIMixin


def make_test_jwt(payload):
    header = {"typ": "JWT", "alg": "EdDSA"}
    header_segment = base64.urlsafe_b64encode(json.dumps(header).encode("utf-8")).decode("ascii").rstrip("=")
    payload_segment = base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).decode("ascii").rstrip("=")
    return f"{header_segment}.{payload_segment}.signature"


class DownloadControlHarness(SteamPluginDownloadControlMixin):
    def __init__(self, secure_settings_dir):
        self.plugin_dir = PROJECT_ROOT
        self.secure_settings_dir = Path(secure_settings_dir)
        self.refresh_requests = []
        self.status_by_app_id = {}
        self.logged_exceptions = []
        self.active_steamid64 = "76561198000000000"
        self.steam_running = True
        self.launch_game_calls = []
        self.enabled_features = {}

    def schedule_installed_games_refresh(self, delay_seconds=0, reset_user_paths=False):
        self.refresh_requests.append((delay_seconds, reset_user_paths))

    def get_active_steam_user_steamid64(self):
        return self.active_steamid64

    def get_installed_game_status(self, app_id):
        return self.status_by_app_id.get(str(app_id), "")

    def log_exception(self, message):
        self.logged_exceptions.append(message)

    def is_steam_client_running(self):
        return self.steam_running

    def launch_game(self, app_id):
        self.launch_game_calls.append(str(app_id))
        return "Game launched"

    def feature_enabled(self, name):
        return self.enabled_features.get(str(name), True)

class LocalDownloadUIHarness(SteamPluginDownloadControlMixin, SteamPluginUIMixin):
    DEFAULT_ICON = "default-icon"

    def __init__(self):
        self.status_by_app_id = {}
        self.live_status_by_app_id = {}
        self.enabled_features = {}

    def build_action(self, method, *parameters):
        return {"method": method, "parameters": list(parameters)}

    def build_result(self, title, subtitle, icon_path=None, action=None, context_data=None, **extra_fields):
        result = {
            "Title": title,
            "SubTitle": subtitle,
            "IcoPath": icon_path,
            "action": action,
            "ContextData": context_data,
        }
        result.update(extra_fields)
        return result

    def build_context_data(self, **kwargs):
        return dict(kwargs)

    def get_installed_game_status(self, app_id):
        return self.status_by_app_id.get(str(app_id), "")

    def get_live_local_game_status(self, app_id, fallback_status=""):
        return self.live_status_by_app_id.get(str(app_id), fallback_status)

    def get_playtime_minutes(self, app_id):
        return None

    def get_last_played_timestamp(self, app_id):
        return None

    def get_current_players(self, app_id):
        return None

    def should_show_playtime(self):
        return False

    def should_show_achievements(self):
        return False

    def should_show_last_played(self):
        return False

    def should_show_player_count(self):
        return False

    def should_prefetch_refund_state(self, app_id):
        return False

    def get_refund_state_for_local_game(self, app_id, allow_network_on_miss=False):
        return ""

    def get_local_game_account_notice(self, app_id):
        return ""

    def get_local_game_icon(self, app_id):
        return "local-icon"

    def get_install_path(self, app_id):
        return f"C:/Games/{app_id}"

    def has_current_account_local_data(self, app_id):
        return True

    def feature_enabled(self, name):
        return self.enabled_features.get(str(name), True)


class DownloadControlUtilityTests(unittest.TestCase):
    def test_extract_webapi_tokens_from_bytes_finds_embedded_token(self):
        token = make_test_jwt({"sub": "76561198000000000", "exp": 4102444800})
        blob = b"\x00\x01junk" + f'{{"webapi_token":"{token}"}}'.encode("utf-8") + b"\x02tail"

        extracted_tokens = extract_webapi_tokens_from_bytes(blob)

        self.assertEqual(extracted_tokens, [token])

    def test_extract_webapi_tokens_from_bytes_finds_html_escaped_token(self):
        token = make_test_jwt({"sub": "76561198000000000", "exp": 4102444800})
        blob = (
            b"\x00\x01junk"
            + f'data-store_user_config="{{&quot;webapi_token&quot;:&quot;{token}&quot;}}"'.encode("utf-8")
            + b"\x02tail"
        )

        extracted_tokens = extract_webapi_tokens_from_bytes(blob)

        self.assertEqual(extracted_tokens, [token])

    def test_scan_cache_file_for_webapi_tokens_reads_binary_cache_file(self):
        token = make_test_jwt({"sub": "76561198000000000", "exp": 4102444800})
        with TemporaryDirectory() as temp_dir:
            cache_file = Path(temp_dir) / "data_1"
            cache_file.write_bytes((b"\x00" * 64) + f'"webapi_token":"{token}"'.encode("utf-8") + (b"\x01" * 64))

            extracted_tokens = scan_cache_file_for_webapi_tokens(cache_file)

        self.assertEqual(extracted_tokens, [token])

    def test_extract_webapi_tokens_from_bytes_finds_access_token_query_parameter(self):
        token = make_test_jwt({"sub": "76561198000000000", "exp": 4102444800})
        blob = (
            b"\x00\x01junk"
            + f"https://api.steampowered.com/IStoreBrowseService/GetItems/v1?access_token={token}&origin=https%3A%2F%2Fstore.steampowered.com".encode("utf-8")
            + b"\x02tail"
        )

        extracted_tokens = extract_webapi_tokens_from_bytes(blob)

        self.assertEqual(extracted_tokens, [token])

    def test_scan_cache_file_for_webapi_tokens_ignores_locked_or_unreadable_file(self):
        with TemporaryDirectory() as temp_dir:
            cache_file = Path(temp_dir) / "data_0"
            cache_file.write_bytes(b'"webapi_token":"ignored"')

            with patch("steamflow.session_token._open_file_shared_read", side_effect=PermissionError):
                extracted_tokens = scan_cache_file_for_webapi_tokens(cache_file)

        self.assertEqual(extracted_tokens, [])

    def test_get_htmlcache_cache_data_files_includes_recent_fragment_files(self):
        with TemporaryDirectory() as temp_dir:
            cache_data_dir = Path(temp_dir) / "Steam" / "htmlcache" / "Default" / "Cache" / "Cache_Data"
            cache_data_dir.mkdir(parents=True)
            data_file = cache_data_dir / "data_1"
            fragment_file = cache_data_dir / "f_000001"
            data_file.write_bytes(b"data")
            fragment_file.write_bytes(b"fragment")

            data_mtime = 1700000000
            fragment_mtime = 1700000010
            os.utime(data_file, (data_mtime, data_mtime))
            os.utime(fragment_file, (fragment_mtime, fragment_mtime))

            cache_files = get_htmlcache_cache_data_files(localappdata=temp_dir, min_mtime=1700000005)

        self.assertEqual(cache_files, [fragment_file])

    def test_select_best_webapi_token_prefers_matching_steamid_and_latest_expiry(self):
        stale_token = make_test_jwt({"sub": "76561198000000000", "exp": 4102444700, "iat": 100})
        fresh_token = make_test_jwt({"sub": "76561198000000000", "exp": 4102444800, "iat": 200})
        other_account_token = make_test_jwt({"sub": "76561198000000001", "exp": 4102444900, "iat": 300})

        selected_token = select_best_webapi_token(
            [stale_token, other_account_token, fresh_token],
            "76561198000000000",
            now=1700000000,
        )

        self.assertEqual(selected_token, fresh_token)


class SteamSessionTokenProviderTests(unittest.TestCase):
    def test_refresh_uses_existing_htmlcache_before_opening_account_preferences(self):
        token = make_test_jwt({"sub": "76561198000000000", "exp": 4102444800})
        opened_uris = []
        saved_tokens = []

        with TemporaryDirectory() as temp_dir:
            provider = SteamSessionTokenProvider(
                temp_dir,
                "76561198000000000",
                validate_token=lambda candidate: True,
                open_uri=opened_uris.append,
                sleep=lambda _seconds: None,
            )
            with patch.object(provider, "load_saved_token", return_value=""):
                with patch.object(provider, "select_htmlcache_token", return_value=token):
                    with patch.object(provider, "save_token", side_effect=lambda candidate, source="htmlcache": saved_tokens.append((candidate, source))):
                        selected_token = provider.refresh_from_steam_htmlcache()

        self.assertEqual(selected_token, token)
        self.assertEqual(opened_uris, [])
        self.assertEqual(saved_tokens, [(token, "htmlcache")])

    def test_refresh_opens_account_preferences_and_saves_html_token_source(self):
        token = make_test_jwt({"sub": "76561198000000000", "exp": 4102444800})
        opened_uris = []
        saved_tokens = []

        with TemporaryDirectory() as temp_dir:
            provider = SteamSessionTokenProvider(
                temp_dir,
                "76561198000000000",
                validate_token=lambda candidate: True,
                open_uri=opened_uris.append,
                sleep=lambda _seconds: None,
            )
            with patch.object(provider, "load_saved_token", return_value=""):
                with patch.object(provider, "select_htmlcache_token", side_effect=["", token]):
                    with patch.object(provider, "save_token", side_effect=lambda candidate, source="htmlcache": saved_tokens.append((candidate, source))):
                        selected_token = provider.refresh_from_steam_htmlcache()

        self.assertEqual(selected_token, token)
        self.assertEqual(opened_uris, [STEAM_ACCOUNT_PREFERENCES_URI, STEAM_GAMES_URI])
        self.assertEqual(saved_tokens, [(token, "account_preferences")])

    def test_refresh_polls_until_account_preferences_token_reaches_htmlcache(self):
        token = make_test_jwt({"sub": "76561198000000000", "exp": 4102444800})
        opened_uris = []
        sleep_seconds = []

        with TemporaryDirectory() as temp_dir:
            provider = SteamSessionTokenProvider(
                temp_dir,
                "76561198000000000",
                validate_token=lambda candidate: True,
                open_uri=opened_uris.append,
                sleep=sleep_seconds.append,
            )
            with patch.object(provider, "load_saved_token", return_value=""):
                with patch.object(provider, "select_htmlcache_token", side_effect=["", "", "", token]):
                    with patch.object(provider, "save_token"):
                        selected_token = provider.refresh_from_steam_htmlcache(refresh_wait_seconds=1)

        self.assertEqual(selected_token, token)
        self.assertEqual(sleep_seconds, [0.25, 0.25])
        self.assertEqual(opened_uris, [STEAM_ACCOUNT_PREFERENCES_URI, STEAM_GAMES_URI])


class DownloadControlActionTests(unittest.TestCase):
    def test_control_steam_download_starts_worker_and_schedules_refresh(self):
        with TemporaryDirectory() as temp_dir:
            harness = DownloadControlHarness(temp_dir)

            with patch.object(subprocess, "Popen") as mocked_popen:
                with patch("steamflow.download_control.schedule_plugin_query_reset_if_supported") as mocked_requery:
                    result = harness.control_steam_download("1451940", "resume")

        self.assertEqual(result, "Trying to resume download for App ID: 1451940")
        self.assertEqual(harness.refresh_requests, [(harness.DOWNLOAD_CONTROL_REFRESH_DELAY_SECONDS, False)])
        mocked_requery.assert_called_once_with(
            harness,
            delay_seconds=harness.DOWNLOAD_CONTROL_REQUERY_DELAY_SECONDS,
        )
        popen_args = mocked_popen.call_args[0][0]
        self.assertEqual(popen_args[1], str(PROJECT_ROOT / "steam_download_control_worker.py"))
        self.assertEqual(popen_args[-3:], ["76561198000000000", "1451940", "resume"])

    def test_control_steam_download_detects_action_from_local_status(self):
        with TemporaryDirectory() as temp_dir:
            harness = DownloadControlHarness(temp_dir)
            harness.status_by_app_id["1451940"] = "Update Paused"

            with patch.object(subprocess, "Popen"):
                result = harness.control_steam_download("1451940")

        self.assertEqual(result, "Trying to resume download for App ID: 1451940")

    def test_control_steam_download_launches_game_instead_of_starting_worker_when_client_is_not_running(self):
        with TemporaryDirectory() as temp_dir:
            harness = DownloadControlHarness(temp_dir)
            harness.steam_running = False

            with patch.object(subprocess, "Popen") as mocked_popen:
                result = harness.control_steam_download("1451940", "pause")

        self.assertEqual(result, "Game launched")
        self.assertEqual(harness.launch_game_calls, ["1451940"])
        mocked_popen.assert_not_called()
        self.assertEqual(harness.refresh_requests, [])

    def test_control_steam_download_returns_unavailable_when_feature_disabled(self):
        with TemporaryDirectory() as temp_dir:
            harness = DownloadControlHarness(temp_dir)
            harness.enabled_features["download_control"] = False

            with patch.object(subprocess, "Popen") as mocked_popen:
                result = harness.control_steam_download("1451940", "pause")

        self.assertEqual(result, "Steam download control is temporarily unavailable")
        mocked_popen.assert_not_called()


class LocalDownloadUITests(unittest.TestCase):
    def test_build_local_result_uses_pause_action_for_updating_game(self):
        harness = LocalDownloadUIHarness()
        harness.status_by_app_id["1451940"] = "Updating"

        result = harness.build_local_result("1451940", "NEEDY GIRL OVERDOSE")

        self.assertEqual(result["Title"], "\U0001F3AE NEEDY GIRL OVERDOSE [Updating]")
        self.assertEqual(result["SubTitle"], "Pause updating game")
        self.assertEqual(
            result["action"],
            {"method": "control_steam_download", "parameters": ["1451940", "pause"]},
        )

    def test_build_local_result_uses_resume_action_for_paused_update(self):
        harness = LocalDownloadUIHarness()
        harness.status_by_app_id["1451940"] = "Update Paused"

        result = harness.build_local_result("1451940", "NEEDY GIRL OVERDOSE")

        self.assertEqual(result["SubTitle"], "Resume updating game")
        self.assertEqual(
            result["action"],
            {"method": "control_steam_download", "parameters": ["1451940", "resume"]},
        )

    def test_build_local_result_prefers_live_paused_status_over_stale_snapshot_status(self):
        harness = LocalDownloadUIHarness()
        harness.status_by_app_id["646570"] = "Updating"
        harness.live_status_by_app_id["646570"] = "Update Paused"

        result = harness.build_local_result("646570", "Slay the Spire")

        self.assertEqual(result["Title"], "\U0001F3AE Slay the Spire [Update Paused]")
        self.assertEqual(result["SubTitle"], "Resume updating game")
        self.assertEqual(
            result["action"],
            {"method": "control_steam_download", "parameters": ["646570", "resume"]},
        )

    def test_build_local_result_keeps_status_but_launches_when_download_control_disabled(self):
        harness = LocalDownloadUIHarness()
        harness.status_by_app_id["1451940"] = "Updating"
        harness.enabled_features["download_control"] = False

        result = harness.build_local_result("1451940", "NEEDY GIRL OVERDOSE")

        self.assertEqual(result["Title"], "\U0001F3AE NEEDY GIRL OVERDOSE [Updating]")
        self.assertEqual(result["SubTitle"], "Installed game, updating")
        self.assertEqual(
            result["action"],
            {"method": "launch_game", "parameters": ["1451940"]},
        )

    def test_build_local_result_localizes_status_badge_without_changing_action_status(self):
        harness = LocalDownloadUIHarness()
        harness.status_by_app_id["1451940"] = "Updating"
        translations = {
            "download.status.updating": "Updating Localized",
            "download.pause_updating": "Pause updating game",
        }
        harness.tr = lambda key, **_values: translations.get(key, key)

        result = harness.build_local_result("1451940", "NEEDY GIRL OVERDOSE")

        self.assertEqual(result["Title"], "\U0001F3AE NEEDY GIRL OVERDOSE [Updating Localized]")
        self.assertEqual(
            result["action"],
            {"method": "control_steam_download", "parameters": ["1451940", "pause"]},
        )


if __name__ == "__main__":
    unittest.main()
