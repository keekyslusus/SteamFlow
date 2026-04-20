import json
import re
import struct
import threading
import time
import copy
from pathlib import Path

import vdf

try:
    import winreg
except ImportError:
    import _winreg as winreg


class SteamPluginLocalMixin:
    LOCAL_PERSONA_STATE_LABELS = {
        0: "Offline",
        1: "Online",
        2: "Busy",
        3: "Away",
        4: "Snooze",
        5: "Looking to trade",
        6: "Looking to play",
        7: "Invisible",
    }
    LOCAL_PERSONA_STATE_PROTOCOLS = {
        0: "offline",
        1: "online",
        7: "invisible",
    }

    def get_refund_state_for_local_game(self, app_id, allow_network_on_miss=False):
        if not self.should_offer_refund_shortcut() or not app_id:
            return ""

        if not self.has_current_account_local_data(app_id):
            return ""

        playtime_minutes = self.get_playtime_minutes(app_id)
        if playtime_minutes is not None and playtime_minutes >= 120:
            return ""

        metadata = self.get_app_details_metadata(app_id, allow_network_on_miss=allow_network_on_miss)
        if not metadata:
            return ""
        if metadata.get("type") != "game" or metadata.get("is_free") is not False:
            return ""

        if playtime_minutes is not None and playtime_minutes < 120:
            return "likely"
        if playtime_minutes is None:
            return "unclear"
        return ""

    def hidden_games_cache_is_stale(self):
        if not self.should_hide_hidden_games():
            return False

        hidden_collections_path = self.get_hidden_collections_path()
        if not hidden_collections_path or not hidden_collections_path.exists():
            with self.state_lock:
                return self.hidden_games_cache_loaded and bool(self.hidden_app_ids)

        try:
            current_mtime = hidden_collections_path.stat().st_mtime
        except OSError:
            return False

        with self.state_lock:
            return (
                not self.hidden_games_cache_loaded
                or hidden_collections_path != self.hidden_collections_path
                or current_mtime > self.hidden_games_mtime
            )

    def get_installed_games_items(self):
        with self.state_lock:
            return list(self.installed_games.items())

    def get_install_path(self, app_id):
        with self.state_lock:
            return self.installed_game_paths.get(str(app_id))

    def get_installed_game_status(self, app_id):
        with self.state_lock:
            return self.installed_game_statuses.get(str(app_id), "")

    def get_playtime_minutes(self, app_id):
        with self.state_lock:
            return self.playtime_minutes.get(str(app_id))

    def get_last_played_timestamp(self, app_id):
        with self.state_lock:
            return self.last_played_timestamps.get(str(app_id))

    def get_owned_game_playtime_minutes(self, app_id):
        with self.state_lock:
            return self.owned_game_playtimes.get(str(app_id))

    def get_local_achievement_progress(self, app_id):
        app_id = str(app_id or "").strip()
        if not app_id or not self.should_show_achievements():
            return None
        return self.ensure_local_achievement_progress_loaded(app_id)

    def has_current_account_stats_file(self, app_id):
        app_id = str(app_id or "").strip()
        if not app_id:
            return False

        active_user_id = self.get_active_steam_user_id()
        if not active_user_id or not self.stats_cache_path or not self.stats_cache_path.exists():
            return False

        user_stats_path = self.stats_cache_path / f"UserGameStats_{active_user_id}_{app_id}.bin"
        try:
            return user_stats_path.exists()
        except OSError:
            return False

    def active_local_user_state_is_stale(self):
        current_active_user_id = self.get_active_steam_user_id()
        with self.state_lock:
            tracked_active_user_id = self.active_steam_user_id_snapshot
        return current_active_user_id != tracked_active_user_id

    def localconfig_stats_are_stale(self):
        current_localconfig_path = self.get_localconfig_path()
        try:
            current_localconfig_mtime = (
                current_localconfig_path.stat().st_mtime
                if current_localconfig_path and current_localconfig_path.exists()
                else 0
            )
        except OSError:
            current_localconfig_mtime = 0

        with self.state_lock:
            tracked_localconfig_path = self.localconfig_path
            tracked_localconfig_mtime = self.localconfig_mtime

        return (
            current_localconfig_path != tracked_localconfig_path
            or current_localconfig_mtime > tracked_localconfig_mtime
        )

    def refresh_user_scoped_local_state_if_needed(self):
        if not self.active_local_user_state_is_stale() and not self.localconfig_stats_are_stale():
            return False
        self.refresh_user_scoped_local_state()
        return True

    def has_current_account_local_data(self, app_id):
        app_id = str(app_id or "").strip()
        if not app_id:
            return False

        if self.get_playtime_minutes(app_id) is not None:
            return True
        if self.get_last_played_timestamp(app_id):
            return True
        return self.has_current_account_stats_file(app_id)

    def should_show_cross_account_install_notice(self, app_id):
        app_id = str(app_id or "").strip()
        if not app_id:
            return False

        if self.has_current_account_local_data(app_id):
            return False

        metadata = self.get_app_details_metadata(app_id, allow_network_on_miss=False)
        if metadata and metadata.get("is_free") is True:
            return False

        return True

    def get_local_game_account_notice(self, app_id):
        ownership_state = self.get_active_account_ownership_state(app_id)
        if ownership_state == "not_owned" and self.should_show_cross_account_install_notice(app_id):
            return " | Installed via another account"

        if ownership_state == "unknown" and self.has_multiple_known_steam_accounts():
            if not self.has_current_account_local_data(app_id):
                return " | No current-account data"

        return ""

    def get_steam_path(self):
        paths_to_try = [
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam"),
            (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Valve\Steam"),
        ]
        for hkey, path in paths_to_try:
            try:
                with winreg.OpenKey(hkey, path) as key:
                    steam_path, _ = winreg.QueryValueEx(key, "InstallPath")
                steam_path = Path(steam_path)
                if steam_path.exists():
                    return steam_path
            except Exception:
                continue
        return None

    def get_localconfig_path(self):
        if not self.steam_path:
            return None

        userdata_path = self.steam_path / "userdata"
        if not userdata_path.exists():
            return None

        active_user_id = self.get_active_steam_user_id()
        if active_user_id:
            active_user_config = userdata_path / active_user_id / "config" / "localconfig.vdf"
            if active_user_config.exists():
                return active_user_config

        candidates = list(userdata_path.glob("*/config/localconfig.vdf"))
        if not candidates:
            return None

        return max(candidates, key=lambda path: path.stat().st_mtime)

    def load_localconfig_steam_data(self, localconfig_path=None):
        localconfig_path = Path(localconfig_path) if localconfig_path else (self.localconfig_path or self.get_localconfig_path())
        if not localconfig_path or not localconfig_path.exists():
            return {}

        data = self.load_localconfig_data_root(localconfig_path)
        steam_data = (
            data.get("UserLocalConfigStore", {})
            .get("Software", {})
            .get("Valve", {})
            .get("Steam", {})
        )
        return steam_data if isinstance(steam_data, dict) else {}

    def load_localconfig_friends_data(self, localconfig_path=None):
        localconfig_path = Path(localconfig_path) if localconfig_path else (self.localconfig_path or self.get_localconfig_path())
        if not localconfig_path or not localconfig_path.exists():
            return {}

        data = self.load_localconfig_data_root(localconfig_path)
        friends_data = data.get("UserLocalConfigStore", {}).get("friends") or data.get("UserLocalConfigStore", {}).get("Friends")
        return friends_data if isinstance(friends_data, dict) else {}

    def load_localconfig_data_root(self, localconfig_path=None):
        localconfig_path = Path(localconfig_path) if localconfig_path else (self.localconfig_path or self.get_localconfig_path())
        if not localconfig_path or not localconfig_path.exists():
            return {}

        try:
            current_mtime = localconfig_path.stat().st_mtime
        except OSError:
            current_mtime = 0

        with self.state_lock:
            cache_path = getattr(self, "localconfig_data_cache_path", None)
            cache_mtime = getattr(self, "localconfig_data_cache_mtime", 0)
            cache_data = getattr(self, "localconfig_data_cache", None)

        if (
            isinstance(cache_data, dict)
            and localconfig_path == cache_path
            and current_mtime <= cache_mtime
        ):
            return copy.deepcopy(cache_data)

        with open(localconfig_path, "r", encoding="utf-8", errors="ignore") as file_obj:
            data = vdf.load(file_obj)
        normalized_data = data if isinstance(data, dict) else {}
        with self.state_lock:
            self.localconfig_data_cache_path = localconfig_path
            self.localconfig_data_cache_mtime = current_mtime
            self.localconfig_data_cache = copy.deepcopy(normalized_data)
        return normalized_data

    def get_local_persona_state_label(self, persona_state):
        try:
            normalized_state = int(persona_state)
        except (TypeError, ValueError):
            return ""
        return self.LOCAL_PERSONA_STATE_LABELS.get(normalized_state, f"State {normalized_state}")

    def get_local_persona_state_protocol(self, persona_state):
        try:
            normalized_state = int(persona_state)
        except (TypeError, ValueError):
            return None
        return self.LOCAL_PERSONA_STATE_PROTOCOLS.get(normalized_state)

    def load_localconfig_text(self, localconfig_path=None):
        localconfig_path = Path(localconfig_path) if localconfig_path else (self.localconfig_path or self.get_localconfig_path())
        if not localconfig_path or not localconfig_path.exists():
            return ""

        try:
            current_mtime = localconfig_path.stat().st_mtime
        except OSError:
            current_mtime = 0

        with self.state_lock:
            cache_path = getattr(self, "localconfig_text_cache_path", None)
            cache_mtime = getattr(self, "localconfig_text_cache_mtime", 0)
            cache_text = getattr(self, "localconfig_text_cache", "")

        if (
            isinstance(cache_text, str)
            and localconfig_path == cache_path
            and current_mtime <= cache_mtime
        ):
            return cache_text

        with open(localconfig_path, "r", encoding="utf-8", errors="ignore") as file_obj:
            text = file_obj.read()

        with self.state_lock:
            self.localconfig_text_cache_path = localconfig_path
            self.localconfig_text_cache_mtime = current_mtime
            self.localconfig_text_cache = text
        return text

    def get_active_local_persona_state(self):
        active_user_id = str(self.get_active_steam_user_id() or "").strip()
        if not active_user_id:
            return None

        try:
            localconfig_text = self.load_localconfig_text()
            if not localconfig_text:
                return None
            pattern = rf'"FriendStoreLocalPrefs_{re.escape(active_user_id)}"\s+"{{\\\"ePersonaState\\\":\s*(\d+)'
            match = re.search(pattern, localconfig_text)
            if not match:
                return None
            return int(match.group(1))
        except Exception:
            self.log_exception("Failed to load active Steam friends status from localconfig.vdf")
            return None

    def get_hidden_collections_path(self):
        if self.localconfig_path:
            candidate = self.localconfig_path.parent / "cloudstorage" / "cloud-storage-namespace-1.json"
            if candidate.exists():
                return candidate

        if not self.steam_path:
            return None

        userdata_path = self.steam_path / "userdata"
        if not userdata_path.exists():
            return None

        active_user_id = self.get_active_steam_user_id()
        if active_user_id:
            active_user_cloudstorage = userdata_path / active_user_id / "config" / "cloudstorage" / "cloud-storage-namespace-1.json"
            if active_user_cloudstorage.exists():
                return active_user_cloudstorage

        candidates = list(userdata_path.glob("*/config/cloudstorage/cloud-storage-namespace-1.json"))
        if not candidates:
            return None

        return max(candidates, key=lambda path: path.stat().st_mtime)

    def load_hidden_app_ids(self):
        hidden_collections_path = self.get_hidden_collections_path()
        if not hidden_collections_path or not hidden_collections_path.exists():
            with self.state_lock:
                self.hidden_collections_path = hidden_collections_path
                self.hidden_games_mtime = 0
                self.hidden_app_ids = set()
                self.hidden_games_cache_loaded = True
            return set()

        try:
            current_mtime = hidden_collections_path.stat().st_mtime
            with self.state_lock:
                if (
                    self.hidden_games_cache_loaded
                    and hidden_collections_path == self.hidden_collections_path
                    and current_mtime <= self.hidden_games_mtime
                ):
                    return set(self.hidden_app_ids)

            with open(hidden_collections_path, "r", encoding="utf-8") as file_obj:
                data = json.load(file_obj)

            hidden_app_ids = set()
            if isinstance(data, list):
                for entry in data:
                    if not isinstance(entry, list) or len(entry) < 2:
                        continue
                    entry_key, entry_payload = entry[0], entry[1]
                    if entry_key != "user-collections.hidden" or not isinstance(entry_payload, dict):
                        continue

                    raw_value = entry_payload.get("value")
                    if not raw_value:
                        break

                    collection_data = json.loads(raw_value)
                    added = collection_data.get("added", [])
                    removed = {str(app_id) for app_id in collection_data.get("removed", [])}
                    hidden_app_ids = {
                        str(app_id)
                        for app_id in added
                        if str(app_id) not in removed
                    }
                    break

            with self.state_lock:
                self.hidden_collections_path = hidden_collections_path
                self.hidden_games_mtime = current_mtime
                self.hidden_app_ids = hidden_app_ids
                self.hidden_games_cache_loaded = True
            return set(hidden_app_ids)
        except Exception:
            self.log_exception("Failed to load hidden Steam games")
            return set()

    def get_all_steam_library_paths(self):
        if not self.steam_path:
            return []

        main_library_path = self.steam_path / "steamapps"
        library_paths = []
        if main_library_path.exists():
            library_paths.append(main_library_path)

        library_folders_vdf_path = main_library_path / "libraryfolders.vdf"
        if not library_folders_vdf_path.exists():
            with self.state_lock:
                self.library_folders_cache_path = library_folders_vdf_path
                self.library_folders_cache_mtime = 0
                self.library_paths_cache = list(library_paths)
            return list(library_paths)

        try:
            current_mtime = library_folders_vdf_path.stat().st_mtime
            with self.state_lock:
                if (
                    self.library_paths_cache is not None
                    and library_folders_vdf_path == self.library_folders_cache_path
                    and current_mtime <= self.library_folders_cache_mtime
                ):
                    return list(self.library_paths_cache)

            if library_folders_vdf_path.exists():
                with open(library_folders_vdf_path, "r", encoding="utf-8") as file_obj:
                    data = vdf.load(file_obj)
                for key, folder_info in data.get("libraryfolders", {}).items():
                    if key.isdigit() and "path" in folder_info:
                        alt_path = Path(folder_info["path"]) / "steamapps"
                        if alt_path.exists() and alt_path not in library_paths:
                            library_paths.append(alt_path)

                with self.state_lock:
                    self.library_folders_cache_path = library_folders_vdf_path
                    self.library_folders_cache_mtime = current_mtime
                    self.library_paths_cache = list(library_paths)
        except Exception:
            self.log_exception("Failed to load Steam library folders")
        return library_paths

    def get_appmanifest_signature(self, manifest_path):
        try:
            stat_result = manifest_path.stat()
            return (int(stat_result.st_mtime_ns), int(stat_result.st_size))
        except OSError:
            return None

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
            with open(manifest_path, "r", encoding="utf-8", errors="ignore") as file_obj:
                acf_data = vdf.load(file_obj).get("AppState", {})
            manifest_data = {
                "app_id": str(acf_data.get("appid", "")).strip(),
                "name": acf_data.get("name"),
                "install_dir": acf_data.get("installdir"),
                "state_flags": self.parse_state_flags(acf_data.get("StateFlags", 0)),
            }
            return self.store_appmanifest_cache(manifest_path, signature, manifest_data)
        except Exception:
            self.log_exception(f"Failed to parse manifest: {manifest_path}")
            return None

    def cleanup_appmanifest_cache(self, manifest_keys_in_use):
        with self.state_lock:
            stale_keys = [
                manifest_key
                for manifest_key in self.appmanifest_cache
                if manifest_key not in manifest_keys_in_use
            ]
            for manifest_key in stale_keys:
                self.appmanifest_cache.pop(manifest_key, None)

    def refresh_local_steam_user_paths(self):
        active_user_id = self.get_active_steam_user_id()
        localconfig_path = self.get_localconfig_path()
        with self.state_lock:
            localconfig_changed = localconfig_path != self.localconfig_path
            self.localconfig_path = localconfig_path
            if localconfig_changed:
                self.localconfig_mtime = 0

        hidden_collections_path = self.get_hidden_collections_path()
        with self.state_lock:
            hidden_collections_changed = hidden_collections_path != self.hidden_collections_path
            self.hidden_collections_path = hidden_collections_path
            if hidden_collections_changed:
                self.hidden_games_mtime = 0
                self.hidden_app_ids = set()
                self.hidden_games_cache_loaded = False

            self.stats_cache_path = (self.steam_path / "appcache" / "stats") if self.steam_path else None
            self.active_steam_user_id_snapshot = active_user_id

    def refresh_user_scoped_local_state(self):
        if not self.steam_path:
            return

        self.refresh_local_steam_user_paths()
        playtime_minutes = {}
        last_played_timestamps = {}
        if (
            self.should_show_playtime()
            or self.should_show_last_played()
            or self.should_sort_local_by_recent()
            or self.should_offer_refund_shortcut()
        ):
            playtime_minutes, last_played_timestamps = self.load_localconfig_stats()

        with self.state_lock:
            self.playtime_minutes = playtime_minutes
            self.last_played_timestamps = last_played_timestamps
            self.achievement_progress = {}
            self.achievement_progress_signatures = {}

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

        def _worker():
            if delay_seconds > 0:
                time.sleep(delay_seconds)
            self.update_installed_games(force=True, allow_background=True)

        threading.Thread(target=_worker, daemon=True).start()

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
        with self.state_lock:
            if self.installed_games_update_in_progress:
                return False
            self.installed_games_update_in_progress = True
        threading.Thread(target=self._refresh_installed_games_worker, daemon=True).start()
        return True

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
            blacklist = self.get_blacklisted_app_ids()
            if (
                self.should_show_playtime()
                or self.should_show_last_played()
                or self.should_sort_local_by_recent()
                or self.should_offer_refund_shortcut()
            ):
                playtime_minutes, last_played_timestamps = self.load_localconfig_stats()

            for steamapps_path in self.get_all_steam_library_paths():
                try:
                    if not steamapps_path.exists():
                        continue
                    for acf_file in steamapps_path.glob("appmanifest_*.acf"):
                        manifest_keys_in_use.add(str(acf_file))
                        try:
                            manifest_data = self.load_appmanifest_data(acf_file)
                            if not manifest_data:
                                continue
                            app_id = manifest_data.get("app_id", "")
                            name = manifest_data.get("name")
                            install_dir = manifest_data.get("install_dir")
                            state_flags = manifest_data.get("state_flags") or {}
                            if not app_id or not name or app_id in blacklist:
                                continue
                            if not state_flags["is_visible"]:
                                continue
                            installed_games[app_id] = name
                            installed_game_statuses[app_id] = state_flags["label"]
                            if install_dir:
                                installed_game_paths[app_id] = str(steamapps_path / "common" / install_dir)
                        except Exception:
                            self.log_exception(f"Failed to process manifest: {acf_file}")
                except Exception:
                    self.log_exception(f"Failed to scan Steam library: {steamapps_path}")

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

    def cleanup_local_achievement_cache(self, valid_app_ids):
        valid_app_ids = {str(app_id) for app_id in valid_app_ids}
        with self.state_lock:
            stale_progress_keys = [
                app_id
                for app_id in self.achievement_progress
                if app_id not in valid_app_ids
            ]
            stale_signature_keys = [
                app_id
                for app_id in self.achievement_progress_signatures
                if app_id not in valid_app_ids
            ]
            for app_id in stale_progress_keys:
                self.achievement_progress.pop(app_id, None)
            for app_id in stale_signature_keys:
                self.achievement_progress_signatures.pop(app_id, None)

    def ensure_local_achievement_progress_loaded(self, app_id):
        if not self.stats_cache_path or not self.stats_cache_path.exists():
            return None

        active_user_id = self.get_active_steam_user_id()
        if not active_user_id:
            return None

        app_id = str(app_id)
        schema_path = self.stats_cache_path / f"UserGameStatsSchema_{app_id}.bin"
        user_stats_path = self.stats_cache_path / f"UserGameStats_{active_user_id}_{app_id}.bin"
        signature = self.get_local_achievement_signature(schema_path, user_stats_path)

        with self.state_lock:
            cached_signature = self.achievement_progress_signatures.get(app_id)
            cached_progress = self.achievement_progress.get(app_id)

        if cached_signature == signature:
            return cached_progress

        total_achievements = self.read_local_achievement_total(schema_path)
        if total_achievements <= 0:
            with self.state_lock:
                self.achievement_progress_signatures[app_id] = signature
                self.achievement_progress.pop(app_id, None)
            return None

        unlocked_achievements = self.read_local_unlocked_achievement_count(user_stats_path)
        progress = (unlocked_achievements, total_achievements)

        with self.state_lock:
            self.achievement_progress_signatures[app_id] = signature
            self.achievement_progress[app_id] = progress
        return progress

    def get_local_achievement_signature(self, schema_path, user_stats_path):
        signature = []
        for path in (schema_path, user_stats_path):
            try:
                stat_result = path.stat()
                signature.extend((int(stat_result.st_mtime_ns), int(stat_result.st_size)))
            except OSError:
                signature.extend((0, 0))
        return tuple(signature)

    def read_local_achievement_total(self, schema_path):
        if not schema_path or not schema_path.exists():
            return 0
        try:
            return schema_path.read_bytes().count(b"icon_gray")
        except Exception:
            self.log_exception(f"Failed to load achievement schema: {schema_path}")
            return 0

    def read_local_unlocked_achievement_count(self, user_stats_path):
        if not user_stats_path or not user_stats_path.exists():
            return 0
        try:
            parsed = self.parse_binary_keyvalues(user_stats_path.read_bytes())
            cache = parsed.get("cache", {})
            unlocked_count = 0
            for section_data in cache.values():
                if not isinstance(section_data, dict):
                    continue
                bitmask = section_data.get("data")
                if isinstance(bitmask, int):
                    unlocked_count += (bitmask & 0xFFFFFFFF).bit_count()
            return unlocked_count
        except Exception:
            self.log_exception(f"Failed to load local user stats: {user_stats_path}")
            return 0

    def parse_binary_keyvalues(self, data):
        reader = self.BinaryKeyValuesReader(data)
        return self.parse_binary_keyvalues_object(reader)

    def parse_binary_keyvalues_object(self, reader):
        parsed = {}
        while reader.offset < len(reader.data):
            value_type = reader.read_byte()
            if value_type == self.BinaryKeyValuesReader.TYPE_END:
                return parsed

            key = reader.read_cstring()
            if value_type == self.BinaryKeyValuesReader.TYPE_NONE:
                parsed[key] = self.parse_binary_keyvalues_object(reader)
            elif value_type == self.BinaryKeyValuesReader.TYPE_STRING:
                parsed[key] = reader.read_cstring()
            elif value_type == self.BinaryKeyValuesReader.TYPE_INT:
                parsed[key] = reader.read_int32()
            elif value_type == self.BinaryKeyValuesReader.TYPE_UINT64:
                parsed[key] = reader.read_uint64()
            else:
                raise ValueError(f"Unsupported KeyValues type: {value_type}")
        return parsed

    class BinaryKeyValuesReader:
        TYPE_NONE = 0
        TYPE_STRING = 1
        TYPE_INT = 2
        TYPE_UINT64 = 7
        TYPE_END = 8

        def __init__(self, data):
            self.data = data
            self.offset = 0

        def read_byte(self):
            value = self.data[self.offset]
            self.offset += 1
            return value

        def read_cstring(self):
            end_index = self.data.index(0, self.offset)
            value = self.data[self.offset:end_index].decode("utf-8", errors="ignore")
            self.offset = end_index + 1
            return value

        def read_int32(self):
            value = struct.unpack_from("<i", self.data, self.offset)[0]
            self.offset += 4
            return value

        def read_uint64(self):
            value = struct.unpack_from("<Q", self.data, self.offset)[0]
            self.offset += 8
            return value

    def parse_state_flags(self, raw_state_flags):
        try:
            state_flags = int(raw_state_flags)
        except (TypeError, ValueError):
            state_flags = 0

        is_fully_installed = bool(state_flags & self.STATE_FLAG_FULLY_INSTALLED)
        is_update_paused = bool(state_flags & self.STATE_FLAG_UPDATE_PAUSED)
        is_updating = bool(state_flags & (self.STATE_FLAG_UPDATE_RUNNING | self.STATE_FLAG_UPDATE_STARTED))
        is_update_required = bool(state_flags & self.STATE_FLAG_UPDATE_REQUIRED)

        status_label = ""
        if is_update_paused:
            status_label = "Update Paused"
        elif is_updating:
            status_label = "Updating"
        elif is_update_required:
            status_label = "Update Queued" if is_fully_installed else "Update Required"

        return {
            "is_visible": is_fully_installed or is_update_required or is_updating or is_update_paused,
            "label": status_label,
        }

    def load_localconfig_stats(self):
        if not self.localconfig_path or not self.localconfig_path.exists():
            return {}, {}

        try:
            current_mtime = self.localconfig_path.stat().st_mtime
            with self.state_lock:
                if current_mtime <= self.localconfig_mtime and (
                    self.playtime_minutes or self.last_played_timestamps
                ):
                    return dict(self.playtime_minutes), dict(self.last_played_timestamps)

            steam_data = self.load_localconfig_steam_data(self.localconfig_path)
            apps = steam_data.get("apps") or steam_data.get("Apps") or {}
            if not isinstance(apps, dict):
                apps = {}

            playtimes = {}
            last_played_timestamps = {}
            for app_id, app_data in apps.items():
                playtime = app_data.get("Playtime")
                if playtime is None:
                    playtime = None
                try:
                    if playtime is not None:
                        playtimes[str(app_id)] = int(playtime)
                except (TypeError, ValueError):
                    pass

                last_played = app_data.get("LastPlayed")
                if last_played is None:
                    continue
                try:
                    last_played_timestamps[str(app_id)] = int(last_played)
                except (TypeError, ValueError):
                    continue

            with self.state_lock:
                self.localconfig_mtime = current_mtime
            return playtimes, last_played_timestamps
        except Exception:
            self.log_exception("Failed to load playtime data from localconfig.vdf")
            return {}, {}

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
