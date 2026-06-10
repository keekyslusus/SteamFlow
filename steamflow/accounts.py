import copy

import vdf

from .hooks import schedule_installed_games_refresh_if_supported, show_message_if_supported
from .localization import plugin_tr
from .account_switcher import (
    STEAM_PROCESS_IMAGE_NAMES as DEFAULT_STEAM_PROCESS_IMAGE_NAMES,
    is_windows_process_running,
    launch_steam_client_executable as launch_steam_client_executable_helper,
    read_active_steam_user_id_from_registry,
    set_steam_registry_autologin_user as set_steam_registry_autologin_user_in_registry,
    start_steam_switch_worker_process,
    terminate_process_tree,
    terminate_steam_processes as terminate_steam_processes_helper,
)
from .account_service import (
    get_known_steam_accounts as get_known_steam_accounts_from_loginusers,
    get_loginusers_backup_path as get_loginusers_backup_path_for_file,
    get_loginusers_path as get_loginusers_path_for_steam_path,
    get_steam_account_label as get_normalized_steam_account_label,
    get_steam_user_details as get_steam_user_details_from_loginusers,
    load_loginusers_file,
    normalize_loginusers_data,
    save_loginusers_file,
    select_last_known_steamid64,
    set_loginusers_autologin_account_data,
    steamid64_to_user_id,
    user_id_to_steamid64,
)


class SteamPluginAccountsMixin:
    REQUIRED_PLUGIN_ATTRS = (
        "DEFAULT_ICON",
        "plugin_dir",
        "state_lock",
        "steam_path",
    )
    REQUIRED_PLUGIN_METHODS = (
        "get_steam_path",
        "log_exception",
    )
    STEAM_PROCESS_IMAGE_NAMES = DEFAULT_STEAM_PROCESS_IMAGE_NAMES

    def get_loginusers_backup_path(self):
        return get_loginusers_backup_path_for_file(self.get_loginusers_path())

    def _normalize_loginusers_data(self, parsed):
        return normalize_loginusers_data(parsed)

    def _get_cached_loginusers_data(self, candidate_path, current_mtime):
        with self.state_lock:
            cache_path = self.loginusers_cache_path
            cache_mtime = self.loginusers_cache_mtime
            cache_data = self.loginusers_cache_data

        if (
            candidate_path
            and cache_data is not None
            and candidate_path == cache_path
            and current_mtime <= cache_mtime
        ):
            return copy.deepcopy(cache_data)
        return None

    def _store_loginusers_cache(self, candidate_path, current_mtime, parsed):
        normalized = self._normalize_loginusers_data(parsed)
        with self.state_lock:
            self.loginusers_cache_path = candidate_path
            self.loginusers_cache_mtime = current_mtime
            self.loginusers_cache_data = copy.deepcopy(normalized)
        return copy.deepcopy(normalized)

    def load_loginusers_data(self):
        paths_to_try = [self.get_loginusers_path(), self.get_loginusers_backup_path()]
        parse_failed = False
        for candidate_path in paths_to_try:
            if not candidate_path or not candidate_path.exists():
                continue

            try:
                current_mtime = candidate_path.stat().st_mtime
            except OSError:
                current_mtime = 0

            cached_data = self._get_cached_loginusers_data(candidate_path, current_mtime)
            if cached_data is not None:
                return cached_data

            try:
                parsed = load_loginusers_file(candidate_path, vdf_loader=vdf.load)
                return self._store_loginusers_cache(candidate_path, current_mtime, parsed)
            except Exception:
                parse_failed = True
                continue

        if parse_failed:
            self.log_exception("Failed to load Steam loginusers.vdf")
        return {}

    def save_loginusers_data(self, data):
        loginusers_path = self.get_loginusers_path()
        if not loginusers_path:
            raise FileNotFoundError("Steam loginusers.vdf not found")

        backup_path = self.get_loginusers_backup_path()
        save_loginusers_file(loginusers_path, data, backup_path=backup_path, vdf_dumper=vdf.dump)

        try:
            current_mtime = loginusers_path.stat().st_mtime
        except OSError:
            current_mtime = 0
        self._store_loginusers_cache(loginusers_path, current_mtime, data)

    def get_steam_account_avatar_path(self, steamid64):
        if not self.steam_path or not steamid64:
            return None
        avatar_path = self.steam_path / "config" / "avatarcache" / f"{steamid64}.png"
        if avatar_path.exists():
            return avatar_path
        return None

    def get_steam_account_label(self, account_data):
        return get_normalized_steam_account_label(account_data)

    def get_known_steam_accounts(self):
        return get_known_steam_accounts_from_loginusers(
            self.load_loginusers_data(),
            avatar_path_resolver=self.get_steam_account_avatar_path,
        )

    def get_switchable_steam_accounts(self):
        active_steamid64 = self.get_active_steam_user_steamid64()
        return [
            account
            for account in self.get_known_steam_accounts()
            if account.get("steamid64") != active_steamid64
        ]

    def show_switch_error_message(self, message):
        try:
            show_message_if_supported(self, plugin_tr(self, "account.switch_failed_title"), str(message or ""), self.DEFAULT_ICON)
        except Exception:
            pass

    def has_multiple_known_steam_accounts(self):
        return len(self.get_known_steam_accounts()) > 1

    def set_loginusers_autologin_account(self, steamid64):
        target_steamid64 = str(steamid64 or "").strip()
        data = self.load_loginusers_data()
        normalized_user_data = set_loginusers_autologin_account_data(data, target_steamid64)
        if normalized_user_data is None:
            return None
        self.save_loginusers_data(data)
        return normalized_user_data

    def set_steam_registry_autologin_user(self, account_name):
        set_steam_registry_autologin_user_in_registry(account_name)

    def _is_windows_process_running(self, image_name):
        return is_windows_process_running(image_name)

    def terminate_steam_processes(self):
        terminate_steam_processes_helper(
            image_names=self.STEAM_PROCESS_IMAGE_NAMES,
            process_running=self._is_windows_process_running,
        )

    def terminate_steam_client(self):
        terminate_process_tree("steam.exe", process_running=self._is_windows_process_running)

    def launch_steam_client_executable(self):
        self.steam_path = launch_steam_client_executable_helper(
            self.steam_path,
            get_steam_path=self.get_steam_path,
        )

    def start_steam_switch_worker(self, steamid64):
        start_steam_switch_worker_process(
            self.plugin_dir,
            self.steam_path,
            steamid64,
        )

    def switch_steam_account(self, steamid64):
        target_steamid64 = str(steamid64 or "").strip()
        if not target_steamid64.isdigit():
            message = plugin_tr(self, "account.invalid")
            self.show_switch_error_message(message)
            return message

        if not self.steam_path:
            self.steam_path = self.get_steam_path()
        if not self.steam_path:
            message = plugin_tr(self, "account.steam_not_found")
            self.show_switch_error_message(message)
            return message

        target_account = self.get_steam_user_details(target_steamid64)
        if not target_account:
            message = plugin_tr(self, "account.not_found")
            self.show_switch_error_message(message)
            return message

        target_label = self.get_steam_account_label(target_account)
        if self.get_active_steam_user_steamid64() == target_steamid64:
            return plugin_tr(self, "account.already_active", account_label=target_label)

        try:
            self.start_steam_switch_worker(target_steamid64)
            schedule_installed_games_refresh_if_supported(self, delay_seconds=5, reset_user_paths=True)
            return plugin_tr(self, "account.switching", account_label=target_label)
        except Exception:
            self.log_exception(f"Failed to start Steam switch worker for {target_label}")
            message = plugin_tr(self, "account.switch_failed", account_label=target_label)
            self.show_switch_error_message(message)
            return message

    def get_loginusers_path(self):
        return get_loginusers_path_for_steam_path(self.steam_path)

    def get_steam_user_details(self, steamid64):
        if not steamid64:
            return {}

        try:
            return get_steam_user_details_from_loginusers(self.load_loginusers_data(), steamid64)
        except Exception:
            self.log_exception("Failed to load Steam loginusers.vdf")
            return {}

    def get_last_known_steam_user_id(self):
        try:
            chosen_steamid64 = select_last_known_steamid64(self.load_loginusers_data())
            if not chosen_steamid64:
                return None
            return steamid64_to_user_id(chosen_steamid64)
        except Exception:
            self.log_exception("Failed to resolve last known Steam user from loginusers.vdf")
            return None

    def get_active_steam_user_id(self):
        return read_active_steam_user_id_from_registry() or self.get_last_known_steam_user_id()

    def get_active_steam_user_steamid64(self):
        active_user_id = self.get_active_steam_user_id()
        if not active_user_id:
            return None
        try:
            return user_id_to_steamid64(active_user_id)
        except (TypeError, ValueError):
            return None
