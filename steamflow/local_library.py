import time

from .cache_utils import read_json_file, write_json_file
from .constants import STEAMFLOW_CONFIG
from .download_status_cache import set_download_control_status_hint as save_download_control_status_hint
from .local_library_service import (
    collect_installed_games_snapshot,
    cleanup_cache_keys,
    get_file_signature,
    load_appmanifest_file,
    parse_manifest_int,
    parse_state_flags,
)
from .providers import get_plugin_providers
from .tasks import get_background_task_manager


class SteamPluginLocalLibraryMixin:
    CONFIG = STEAMFLOW_CONFIG
    REQUIRED_PLUGIN_PROVIDERS = ("settings",)

    @property
    def local_library_providers(self):
        return get_plugin_providers(self)

    def get_installed_games_items(self):
        with self.state_lock:
            return list(self.installed_games.items())

    def get_install_path(self, app_id):
        with self.state_lock:
            return self.installed_game_paths.get(str(app_id))

    def get_installed_game_status(self, app_id):
        with self.state_lock:
            return self.installed_game_statuses.get(str(app_id), "")

    def get_appmanifest_signature(self, manifest_path):
        return get_file_signature(manifest_path)

    def get_cached_appmanifest_data(self, manifest_path, signature):
        if not manifest_path or not signature:
            return None

        manifest_key = str(manifest_path)
        with self.state_lock:
            cache_entry = self.appmanifest_cache.get(manifest_key)

        if not isinstance(cache_entry, dict) or cache_entry.get("signature") != signature:
            return None

        data = cache_entry.get("data")
        return dict(data) if isinstance(data, dict) else None

    def get_appmanifest_path_for_app_id(self, app_id):
        app_id = str(app_id or "").strip()
        if not app_id or not self.steam_path:
            return None

        manifest_name = f"appmanifest_{app_id}.acf"
        for steamapps_path in self.get_all_steam_library_paths():
            candidate = steamapps_path / manifest_name
            if candidate.exists():
                return candidate
        return None

    def store_appmanifest_cache(self, manifest_path, signature, data):
        if not manifest_path or not signature or not isinstance(data, dict):
            return dict(data or {})

        manifest_key = str(manifest_path)
        normalized_data = dict(data)
        with self.state_lock:
            self.appmanifest_cache[manifest_key] = {
                "signature": signature,
                "data": dict(normalized_data),
            }
        return normalized_data

    def load_appmanifest_data(self, manifest_path):
        signature = self.get_appmanifest_signature(manifest_path)
        cached_data = self.get_cached_appmanifest_data(manifest_path, signature)
        if cached_data is not None:
            return cached_data

        try:
            manifest_data = load_appmanifest_file(manifest_path, config=self.CONFIG)
            return self.store_appmanifest_cache(manifest_path, signature, manifest_data)
        except Exception:
            self.log_exception(f"Failed to parse manifest: {manifest_path}")
            return None

    def cleanup_appmanifest_cache(self, manifest_keys_in_use):
        with self.state_lock:
            cleanup_cache_keys(self.appmanifest_cache, manifest_keys_in_use)

    def parse_manifest_int(self, raw_value, default=0):
        return parse_manifest_int(raw_value, default=default)

    def get_download_progress_signature(self, manifest_data):
        if not isinstance(manifest_data, dict):
            return (0, 0, 0, 0)
        return (
            self.parse_manifest_int(manifest_data.get("bytes_downloaded", 0)),
            self.parse_manifest_int(manifest_data.get("bytes_to_download", 0)),
            self.parse_manifest_int(manifest_data.get("bytes_staged", 0)),
            self.parse_manifest_int(manifest_data.get("bytes_to_stage", 0)),
        )

    def load_download_progress_cache(self):
        if getattr(self, "app_download_progress_cache_loaded", False):
            return

        cache_file = getattr(self, "download_progress_cache_file", None)
        cache_data = read_json_file(cache_file, default={}) if cache_file else {}
        normalized_cache = {}
        if isinstance(cache_data, dict):
            for app_id, entry in cache_data.items():
                if not isinstance(entry, dict):
                    continue
                signature = entry.get("signature")
                try:
                    normalized_signature = (
                        tuple(int(value) for value in signature)
                        if isinstance(signature, (list, tuple)) and len(signature) == 4
                        else ()
                    )
                    hint_label = str(entry.get("hint_label", "") or "")
                    if not normalized_signature and not hint_label:
                        continue
                    normalized_cache[str(app_id)] = {
                        "signature": normalized_signature,
                        "first_seen_at": float(entry.get("first_seen_at", 0) or 0),
                        "hint_label": hint_label,
                        "hint_until": float(entry.get("hint_until", 0) or 0),
                    }
                except (TypeError, ValueError):
                    continue

        with self.state_lock:
            if not self.app_download_progress_cache:
                self.app_download_progress_cache = normalized_cache
            self.app_download_progress_cache_loaded = True

    def save_download_progress_cache(self):
        cache_file = getattr(self, "download_progress_cache_file", None)
        if not cache_file:
            return

        with self.state_lock:
            cache_data = {
                app_id: {
                    "signature": list(entry.get("signature", ())),
                    "first_seen_at": entry.get("first_seen_at", 0),
                    "hint_label": entry.get("hint_label", ""),
                    "hint_until": entry.get("hint_until", 0),
                }
                for app_id, entry in self.app_download_progress_cache.items()
                if isinstance(entry, dict)
            }
        write_json_file(cache_file, cache_data)

    def set_download_control_status_hint(self, app_id, action):
        return save_download_control_status_hint(
            getattr(self, "download_progress_cache_file", None),
            app_id,
            action,
            config=self.CONFIG,
        )

    def derive_appmanifest_status_label(self, app_id, state_flags, manifest_data):
        state_flags = state_flags if isinstance(state_flags, dict) else {}
        base_label = str(state_flags.get("label", "") or "")
        now = time.time()
        app_id = str(app_id or "").strip()
        self.load_download_progress_cache()
        with self.state_lock:
            progress_entry = self.app_download_progress_cache.get(app_id, {})
            hint_label = str(progress_entry.get("hint_label", "") or "")
            hint_until = float(progress_entry.get("hint_until", 0) or 0)
            if hint_label and now < hint_until:
                return hint_label

        if state_flags.get("is_update_paused"):
            return self.CONFIG.download.status_update_paused
        if not state_flags.get("is_updating"):
            return base_label

        progress_signature = self.get_download_progress_signature(manifest_data)
        has_pending_bytes = any(progress_signature)
        if not has_pending_bytes:
            return self.CONFIG.download.status_updating

        with self.state_lock:
            progress_entry = self.app_download_progress_cache.get(app_id, {})
            previous_signature = tuple(progress_entry.get("signature", ()))
            first_seen_at = float(progress_entry.get("first_seen_at", now) or now)

            if previous_signature != progress_signature:
                modified_at = float(manifest_data.get("modified_at", 0) or 0)
                first_seen_at = min(now, modified_at) if modified_at > 0 else now
                self.app_download_progress_cache[app_id] = {
                    "signature": progress_signature,
                    "first_seen_at": first_seen_at,
                }
                self.save_download_progress_cache()
                if (now - first_seen_at) >= self.CONFIG.download.progress_stall_seconds:
                    return self.CONFIG.download.status_update_paused
                return self.CONFIG.download.status_updating

            if (now - first_seen_at) >= self.CONFIG.download.progress_stall_seconds:
                return self.CONFIG.download.status_update_paused

        return self.CONFIG.download.status_updating

    def get_live_local_game_status(self, app_id, fallback_status=""):
        app_id = str(app_id or "").strip()
        fallback_status = str(fallback_status or "")
        if not app_id:
            return fallback_status

        manifest_path = self.get_appmanifest_path_for_app_id(app_id)
        if not manifest_path:
            return fallback_status

        manifest_data = self.load_appmanifest_data(manifest_path)
        if not manifest_data:
            return fallback_status

        state_flags = manifest_data.get("state_flags") or {}
        live_status = self.derive_appmanifest_status_label(app_id, state_flags, manifest_data)
        return live_status or fallback_status

    def invalidate_installed_games_snapshot(self, reset_user_paths=False):
        with self.state_lock:
            self.last_update = 0
            if reset_user_paths:
                self.active_steam_user_id_snapshot = None
                self.localconfig_path = None
                self.hidden_collections_path = None
                self.stats_cache_path = None
                self.localconfig_mtime = 0
                self.hidden_games_mtime = 0
                self.hidden_app_ids = set()
                self.hidden_games_cache_loaded = False
                self.achievement_progress = {}
                self.achievement_progress_signatures = {}

    def schedule_installed_games_refresh(self, delay_seconds=0, reset_user_paths=False):
        self.invalidate_installed_games_snapshot(reset_user_paths=reset_user_paths)
        get_background_task_manager(self).start_delayed(
            delay_seconds,
            self.update_installed_games,
            force=True,
            allow_background=True,
        )

    def has_installed_games_snapshot(self):
        with self.state_lock:
            return self.last_update > 0

    def installed_games_refresh_is_needed(self, force=False):
        if force or not self.has_installed_games_snapshot():
            return True
        if self.hidden_games_cache_is_stale():
            return True
        with self.state_lock:
            last_update = self.last_update
        return (time.time() - last_update) >= 300

    def _start_installed_games_refresh(self):
        return get_background_task_manager(self).start_flagged_refresh(
            self,
            "installed_games_update_in_progress",
            self._refresh_installed_games_worker,
        )

    def _refresh_installed_games_worker(self):
        self._refresh_installed_games_snapshot()

    def _refresh_installed_games_snapshot(self):
        installed_games = {}
        installed_game_paths = {}
        installed_game_statuses = {}
        playtime_minutes = {}
        last_played_timestamps = {}
        manifest_keys_in_use = set()
        update_completed = False

        try:
            if not self.steam_path:
                return

            self.refresh_local_steam_user_paths()
            settings_provider = self.local_library_providers.settings
            blacklist = settings_provider.blacklisted_app_ids()
            if (
                settings_provider.should_show_playtime()
                or settings_provider.should_show_last_played()
                or settings_provider.should_sort_local_by_recent()
                or settings_provider.should_offer_refund_shortcut()
            ):
                playtime_minutes, last_played_timestamps = self.load_localconfig_stats()

            snapshot = collect_installed_games_snapshot(
                self.get_all_steam_library_paths(),
                self.load_appmanifest_data,
                self.derive_appmanifest_status_label,
                blacklist=blacklist,
                log_exception=self.log_exception,
            )
            installed_games = snapshot.installed_games
            installed_game_paths = snapshot.installed_game_paths
            installed_game_statuses = snapshot.installed_game_statuses
            manifest_keys_in_use = snapshot.manifest_keys_in_use

            self.cleanup_appmanifest_cache(manifest_keys_in_use)
            self.cleanup_local_achievement_cache(installed_games.keys())
            update_completed = True
        finally:
            with self.state_lock:
                if update_completed:
                    self.installed_games = installed_games
                    self.installed_game_paths = installed_game_paths
                    self.installed_game_statuses = installed_game_statuses
                    self.playtime_minutes = playtime_minutes
                    self.last_played_timestamps = last_played_timestamps
                    self.last_update = time.time()
                self.installed_games_update_in_progress = False

    def update_installed_games(self, force=False, allow_background=True):
        if not force and self.has_installed_games_snapshot() and self.active_local_user_state_is_stale():
            self.refresh_user_scoped_local_state()
            if allow_background:
                self._start_installed_games_refresh()
            return

        if not self.installed_games_refresh_is_needed(force=force):
            return

        if allow_background and self.has_installed_games_snapshot():
            self._start_installed_games_refresh()
            return

        with self.state_lock:
            if self.installed_games_update_in_progress:
                return
            self.installed_games_update_in_progress = True
        self._refresh_installed_games_snapshot()

    def parse_state_flags(self, raw_state_flags):
        return parse_state_flags(raw_state_flags, config=self.CONFIG)

    def get_local_game_icon(self, app_id):
        if not self.steam_icon_cache or not self.steam_icon_cache.exists():
            return self.DEFAULT_ICON

        icon_cache_path = self.steam_icon_cache / str(app_id)
        if not icon_cache_path.is_dir():
            return self.DEFAULT_ICON

        try:
            files = [file_path for file_path in icon_cache_path.iterdir() if file_path.suffix.lower() == ".jpg" and file_path.is_file()]
            filtered_files = [
                file_path
                for file_path in files
                if not (
                    file_path.name.lower().startswith("header")
                    or file_path.name.lower().startswith("library")
                    or file_path.name.lower().startswith("logo")
                )
            ]
            if filtered_files:
                return str(filtered_files[0])
        except Exception:
            self.log_exception(f"Failed to resolve local icon for app {app_id}")

        return self.DEFAULT_ICON
