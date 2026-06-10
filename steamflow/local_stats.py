import struct

from .local_library_service import extract_localconfig_app_stats
from .providers import get_plugin_providers


class SteamPluginLocalStatsMixin:
    REQUIRED_PLUGIN_PROVIDERS = (
        "account",
        "settings",
        "store",
    )

    @property
    def local_stats_providers(self):
        return get_plugin_providers(self)

    def get_refund_state_for_local_game(self, app_id, allow_network_on_miss=False):
        if not self.local_stats_providers.settings.should_offer_refund_shortcut() or not app_id:
            return ""

        if not self.has_current_account_local_data(app_id):
            return ""

        playtime_minutes = self.get_playtime_minutes(app_id)
        if playtime_minutes is not None and playtime_minutes >= 120:
            return ""

        metadata = self.local_stats_providers.store.app_details_metadata(
            app_id,
            allow_network_on_miss=allow_network_on_miss,
        )
        if not metadata:
            return ""
        if metadata.get("type") != "game" or metadata.get("is_free") is not False:
            return ""

        if playtime_minutes is not None and playtime_minutes < 120:
            return "likely"
        if playtime_minutes is None:
            return "unclear"
        return ""

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
        if not app_id or not self.local_stats_providers.settings.should_show_achievements():
            return None
        return self.ensure_local_achievement_progress_loaded(app_id)

    def has_current_account_stats_file(self, app_id):
        app_id = str(app_id or "").strip()
        if not app_id:
            return False

        active_user_id = self.local_stats_providers.account.active_user_id()
        if not active_user_id or not self.stats_cache_path or not self.stats_cache_path.exists():
            return False

        user_stats_path = self.stats_cache_path / f"UserGameStats_{active_user_id}_{app_id}.bin"
        try:
            return user_stats_path.exists()
        except OSError:
            return False

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

        metadata = self.local_stats_providers.store.app_details_metadata(app_id, allow_network_on_miss=False)
        if metadata and metadata.get("is_free") is True:
            return False

        return True

    def get_local_game_account_notice(self, app_id):
        account_provider = self.local_stats_providers.account
        settings_provider = self.local_stats_providers.settings
        ownership_state = account_provider.active_account_ownership_state(app_id)
        if ownership_state == "not_owned" and self.should_show_cross_account_install_notice(app_id):
            return f" | {settings_provider.tr('local.account.installed_other')}"

        if ownership_state == "unknown" and account_provider.has_multiple_known_accounts():
            if not self.has_current_account_local_data(app_id):
                return f" | {settings_provider.tr('local.account.no_current_data')}"

        return ""

    def refresh_user_scoped_local_state(self):
        if not self.steam_path:
            return

        self.refresh_local_steam_user_paths()
        playtime_minutes = {}
        last_played_timestamps = {}
        if (
            self.local_stats_providers.settings.should_show_playtime()
            or self.local_stats_providers.settings.should_show_last_played()
            or self.local_stats_providers.settings.should_sort_local_by_recent()
            or self.local_stats_providers.settings.should_offer_refund_shortcut()
        ):
            playtime_minutes, last_played_timestamps = self.load_localconfig_stats()

        with self.state_lock:
            self.playtime_minutes = playtime_minutes
            self.last_played_timestamps = last_played_timestamps
            self.achievement_progress = {}
            self.achievement_progress_signatures = {}

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

        active_user_id = self.local_stats_providers.account.active_user_id()
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

            playtimes, last_played_timestamps = extract_localconfig_app_stats(
                self.load_localconfig_steam_data(self.localconfig_path)
            )

            with self.state_lock:
                self.localconfig_mtime = current_mtime
            return playtimes, last_played_timestamps
        except Exception:
            self.log_exception("Failed to load playtime data from localconfig.vdf")
            return {}, {}
