import subprocess
import sys

from .account_switcher import is_windows_process_running
from .constants import STEAMFLOW_CONFIG
from .http_client import urllib_json_request
from .hooks import (
    get_secure_settings_dir,
    log_exception_if_supported,
    schedule_installed_games_refresh_if_supported,
    schedule_plugin_query_reset_if_supported,
)
from .os_integration import start_hidden_process
from .providers import get_plugin_providers
from .localization import Localizer, plugin_tr
from .session_token import (
    HTMLCACHE_REFRESH_TIMEOUT_SECONDS,
    STEAM_STORE_ORIGIN,
    SteamSessionTokenProvider,
)
CLIENTCOMM_GET_LOGON_INFO_URL = "https://api.steampowered.com/IClientCommService/GetAllClientLogonInfo/v1/"
CLIENTCOMM_SET_APP_UPDATE_STATE_URL = (
    "https://api.steampowered.com/IClientCommService/SetClientAppUpdateState/v1/"
)
DOWNLOAD_ACTION_BY_STATUS = {
    STEAMFLOW_CONFIG.download.status_updating: "pause",
    STEAMFLOW_CONFIG.download.status_update_paused: "resume",
}
CLIENTCOMM_ACTION_BY_NAME = {
    "pause": 0,
    "resume": 1,
}


def normalize_download_control_action(action):
    normalized = str(action or "").strip().lower()
    return normalized if normalized in CLIENTCOMM_ACTION_BY_NAME else ""


def get_download_control_action_for_status(status_label):
    return DOWNLOAD_ACTION_BY_STATUS.get(str(status_label or "").strip(), "")


def _tr(translator, key, default=None, **values):
    if callable(translator):
        try:
            return translator(key, **values)
        except TypeError:
            return translator(key, **values)
    return Localizer("en").tr(key, **values)


def build_download_control_subtitle(status_label, control_enabled=True, tr=None):
    action = get_download_control_action_for_status(status_label)
    if control_enabled and action == "pause":
        return _tr(tr, "download.pause_updating")
    if control_enabled and action == "resume":
        return _tr(tr, "download.resume_updating")
    subtitle_by_status = {
        STEAMFLOW_CONFIG.download.status_updating: _tr(tr, "download.updating"),
        STEAMFLOW_CONFIG.download.status_update_paused: _tr(tr, "download.update_paused"),
        STEAMFLOW_CONFIG.download.status_update_queued: _tr(tr, "download.update_queued"),
        STEAMFLOW_CONFIG.download.status_update_required: _tr(tr, "download.update_required"),
    }
    return subtitle_by_status.get(str(status_label or "").strip(), _tr(tr, "download.installed_game"))


def _perform_json_request(url, method="GET", fields=None, timeout=3):
    return urllib_json_request(
        url,
        method=method,
        fields=fields,
        timeout=timeout,
        origin=STEAM_STORE_ORIGIN,
        referer=STEAM_STORE_ORIGIN + "/",
    )


def get_client_logon_info(access_token, timeout=3):
    return _perform_json_request(
        CLIENTCOMM_GET_LOGON_INFO_URL,
        method="GET",
        fields={
            "access_token": access_token,
            "origin": STEAM_STORE_ORIGIN,
        },
        timeout=timeout,
    )


def get_primary_client_instanceid(logon_info_payload):
    sessions = (
        (logon_info_payload or {}).get("response", {}).get("sessions", [])
        if isinstance(logon_info_payload, dict)
        else []
    )
    if not isinstance(sessions, list):
        return ""
    for session in sessions:
        if not isinstance(session, dict):
            continue
        client_instanceid = str(session.get("client_instanceid", "") or "").strip()
        if client_instanceid:
            return client_instanceid
    return ""


def set_client_app_update_state(access_token, app_id, action, client_instanceid=None, timeout=3):
    normalized_action = normalize_download_control_action(action)
    if not normalized_action:
        raise ValueError(f"Invalid download control action: {action}")

    fields = {
        "access_token": access_token,
        "origin": STEAM_STORE_ORIGIN,
        "appid": str(app_id or "").strip(),
        "action": str(CLIENTCOMM_ACTION_BY_NAME[normalized_action]),
    }
    client_instanceid = str(client_instanceid or "").strip()
    if client_instanceid:
        fields["client_instanceid"] = client_instanceid

    return _perform_json_request(
        CLIENTCOMM_SET_APP_UPDATE_STATE_URL,
        method="POST",
        fields=fields,
        timeout=timeout,
    )


def refresh_download_control_token(
    secure_settings_dir,
    steamid64,
    logger=None,
    refresh_wait_seconds=HTMLCACHE_REFRESH_TIMEOUT_SECONDS,
):
    provider = SteamSessionTokenProvider(
        secure_settings_dir,
        steamid64,
        logger=logger,
        validate_token=lambda token: get_client_logon_info(token, timeout=3),
    )
    return provider.refresh_from_steam_htmlcache(refresh_wait_seconds=refresh_wait_seconds)


def perform_download_control(secure_settings_dir, steamid64, app_id, action, logger=None):
    steamid64 = str(steamid64 or "").strip()
    app_id = str(app_id or "").strip()
    normalized_action = normalize_download_control_action(action)
    if not steamid64 or not app_id or not normalized_action:
        raise ValueError("Missing Steam download-control arguments")

    provider = SteamSessionTokenProvider(
        secure_settings_dir,
        steamid64,
        logger=logger,
        validate_token=lambda candidate: get_client_logon_info(candidate, timeout=3),
    )
    token = provider.get_saved_or_htmlcache_token()
    if not token:
        if logger:
            logger.info("No cached ClientComm token for %s; refreshing via Steam", steamid64)
        token = provider.refresh_from_steam_htmlcache()

    try:
        logon_info = get_client_logon_info(token, timeout=3)
    except Exception:
        provider.delete_saved_token()
        if logger:
            logger.info("Cached ClientComm token rejected for %s; refreshing", steamid64)
        token = provider.refresh_from_steam_htmlcache()
        logon_info = get_client_logon_info(token, timeout=3)

    client_instanceid = get_primary_client_instanceid(logon_info)
    return set_client_app_update_state(
        token,
        app_id,
        normalized_action,
        client_instanceid=client_instanceid,
        timeout=3,
    )


class SteamPluginDownloadControlMixin:
    REQUIRED_PLUGIN_ATTRS = (
        "plugin_dir",
        "settings_path",
    )
    REQUIRED_PLUGIN_PROVIDERS = (
        "account",
        "local",
    )
    DOWNLOAD_CONTROL_REFRESH_DELAY_SECONDS = 2.5
    DOWNLOAD_CONTROL_REQUERY_DELAY_SECONDS = 2.5

    @property
    def download_control_providers(self):
        return get_plugin_providers(self)

    def get_download_control_action_for_status(self, status_label):
        return get_download_control_action_for_status(status_label)

    def start_download_control_worker(self, steamid64, app_id, action):
        worker_script = self.plugin_dir / "steam_download_control_worker.py"
        if not worker_script.exists():
            raise FileNotFoundError(f"Steam download worker not found at {worker_script}")

        secure_settings_dir = get_secure_settings_dir(self)
        secure_settings_dir.mkdir(parents=True, exist_ok=True)

        start_hidden_process(
            [
                sys.executable,
                str(worker_script),
                str(secure_settings_dir),
                str(steamid64),
                str(app_id),
                str(action),
            ],
            subprocess_module=subprocess,
            cwd=str(self.plugin_dir),
        )

    def is_steam_client_running(self):
        return is_windows_process_running("steam.exe")

    def control_steam_download(self, app_id, action=None):
        app_id = str(app_id or "").strip()
        action = normalize_download_control_action(action)
        if not app_id:
            return plugin_tr(self, "action.missing_app_id")
        is_enabled = getattr(self, "feature_enabled", None)
        if callable(is_enabled) and not is_enabled("download_control"):
            return plugin_tr(self, "action.steam_unavailable")

        providers = self.download_control_providers
        if not action:
            action = self.get_download_control_action_for_status(providers.local.installed_game_status(app_id))
        if not action:
            return plugin_tr(self, "action.download_control_unavailable")

        if not self.is_steam_client_running():
            launch_game = getattr(self, "launch_game", None)
            if callable(launch_game):
                return launch_game(app_id)
            return plugin_tr(self, "action.steam_not_running")

        steamid64 = providers.account.active_steamid64()
        if not steamid64:
            return plugin_tr(self, "action.no_active_account")

        try:
            self.start_download_control_worker(steamid64, app_id, action)
            schedule_installed_games_refresh_if_supported(
                self,
                delay_seconds=self.DOWNLOAD_CONTROL_REFRESH_DELAY_SECONDS,
            )
            schedule_plugin_query_reset_if_supported(
                self,
                delay_seconds=self.DOWNLOAD_CONTROL_REQUERY_DELAY_SECONDS,
            )
            return plugin_tr(
                self,
                "action.download_control_trying",
                action=action,
                app_id=app_id,
            )
        except Exception as error:
            record_failure = getattr(self, "record_feature_failure", None)
            if callable(record_failure):
                record_failure("download_control", error, reason="worker_start_failed")
            log_exception_if_supported(self, f"Failed to start Steam download worker for app {app_id}")
            return plugin_tr(
                self,
                "action.download_control_failed",
                action=action,
                error=str(error),
            )
