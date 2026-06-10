import copy
from pathlib import Path

from .local_library_service import (
    get_localconfig_friends_data,
    get_localconfig_steam_data,
    load_hidden_app_ids_file,
    load_steam_library_paths,
    load_vdf_file,
    parse_active_persona_state,
    resolve_hidden_collections_path,
    resolve_localconfig_path,
)
from .os_integration import resolve_steam_install_path_from_registry
from .providers import get_plugin_providers


class SteamPluginLocalPresenceMixin:
    REQUIRED_PLUGIN_PROVIDERS = (
        "account",
        "settings",
    )
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

    @property
    def local_presence_providers(self):
        return get_plugin_providers(self)

    def hidden_games_cache_is_stale(self):
        if not self.local_presence_providers.settings.should_hide_hidden_games():
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

    def active_local_user_state_is_stale(self):
        current_active_user_id = self.local_presence_providers.account.active_user_id()
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

    def get_steam_path(self):
        return resolve_steam_install_path_from_registry()

    def get_localconfig_path(self):
        return resolve_localconfig_path(self.steam_path, self.local_presence_providers.account.active_user_id())

    def load_localconfig_steam_data(self, localconfig_path=None):
        localconfig_path = Path(localconfig_path) if localconfig_path else (self.localconfig_path or self.get_localconfig_path())
        if not localconfig_path or not localconfig_path.exists():
            return {}

        return get_localconfig_steam_data(self.load_localconfig_data_root(localconfig_path))

    def load_localconfig_friends_data(self, localconfig_path=None):
        localconfig_path = Path(localconfig_path) if localconfig_path else (self.localconfig_path or self.get_localconfig_path())
        if not localconfig_path or not localconfig_path.exists():
            return {}

        return get_localconfig_friends_data(self.load_localconfig_data_root(localconfig_path))

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

        normalized_data = load_vdf_file(localconfig_path)
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
        active_user_id = str(self.local_presence_providers.account.active_user_id() or "").strip()
        if not active_user_id:
            return None

        try:
            localconfig_text = self.load_localconfig_text()
            if not localconfig_text:
                return None
            return parse_active_persona_state(localconfig_text, active_user_id)
        except Exception:
            self.log_exception("Failed to load active Steam friends status from localconfig.vdf")
            return None

    def get_hidden_collections_path(self):
        return resolve_hidden_collections_path(
            self.steam_path,
            active_user_id=self.local_presence_providers.account.active_user_id(),
            localconfig_path=self.localconfig_path,
        )

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

            hidden_app_ids = load_hidden_app_ids_file(hidden_collections_path)

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

            library_paths = load_steam_library_paths(self.steam_path)
            with self.state_lock:
                self.library_folders_cache_path = library_folders_vdf_path
                self.library_folders_cache_mtime = current_mtime
                self.library_paths_cache = list(library_paths)
        except Exception:
            self.log_exception("Failed to load Steam library folders")
        return library_paths

    def refresh_local_steam_user_paths(self):
        active_user_id = self.local_presence_providers.account.active_user_id()
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
