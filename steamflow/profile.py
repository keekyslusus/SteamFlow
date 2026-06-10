import time

from .cache_utils import is_timestamp_fresh, read_json_file, write_json_file
from .constants import STEAMFLOW_CONFIG
from .profile_service import (
    build_avatar_frame_cache_entry,
    build_no_avatar_frame_cache_entry,
    compose_framed_avatar_icon,
    download_binary_file,
    fetch_avatar_frame_data,
    fetch_owned_app_ids,
    fetch_owned_games_refresh_result,
    fetch_player_summary,
    build_owned_games_refresh_log_details,
    get_cached_avatar_frame_state,
    get_owned_app_state,
    get_profile_status_label,
    is_owned_games_cache_fresh,
    is_profile_summary_for_steamid64,
    should_schedule_owned_games_refresh,
)
from .providers import get_plugin_providers
from .tasks import get_background_task_manager

try:
    from PIL import Image
except ImportError:
    Image = None


class SteamPluginProfileMixin:
    CONFIG = STEAMFLOW_CONFIG
    REQUIRED_PLUGIN_PROVIDERS = (
        "account",
        "owned_api",
        "settings",
    )
    REQUIRED_PLUGIN_ATTRS = (
        "avatar_cache_dir",
        "avatar_frame_cache_file",
        "profile_cache_file",
        "state_lock",
    )
    REQUIRED_PLUGIN_METHODS = (
        "_http_get",
        "log_exception",
        "log_slow_call",
    )

    @property
    def profile_providers(self):
        return get_plugin_providers(self)

    def load_profile_cache(self):
        if not self.profile_cache_file.exists():
            return {}
        cache_data = read_json_file(
            self.profile_cache_file,
            default={},
            logger=self.log_exception,
            error_message="Failed to load active Steam profile cache",
        )
        return cache_data if isinstance(cache_data, dict) else {}

    def save_profile_cache(self, cache_data):
        write_json_file(
            self.profile_cache_file,
            cache_data,
            logger=self.log_exception,
            error_message="Failed to save active Steam profile cache",
        )

    def ensure_active_profile_summary_loaded(self):
        with self.state_lock:
            if self.active_profile_summary_loaded:
                return
        cache_data = self.load_profile_cache()
        with self.state_lock:
            self.active_profile_summary = cache_data if isinstance(cache_data, dict) else {}
            self.active_profile_summary_loaded = True

    def active_profile_summary_is_fresh(self):
        account_provider = self.profile_providers.account
        if not account_provider.has_owned_api_key() or not account_provider.api_key_bound_to_active_user():
            return False

        self.ensure_active_profile_summary_loaded()
        steamid64 = account_provider.active_steamid64()
        if not steamid64:
            return False

        with self.state_lock:
            summary = dict(self.active_profile_summary)
        if not is_profile_summary_for_steamid64(summary, steamid64):
            return False
        return is_timestamp_fresh(summary.get("fetched_at", 0), self.CONFIG.cache.profile_summary_ttl_seconds)

    def fetch_active_profile_summary(self, steamid64):
        api_key = self.profile_providers.account.owned_api_key()
        if not api_key or not steamid64:
            return None

        try:
            return fetch_player_summary(
                api_key,
                steamid64,
                self._http_get,
                timeout=1.2,
            )
        except Exception:
            self.log_exception("Failed to fetch active Steam profile summary")
            return None

    def schedule_active_profile_summary_refresh(self, force=False):
        account_provider = self.profile_providers.account
        if not account_provider.has_owned_api_key() or not account_provider.api_key_bound_to_active_user():
            return

        self.ensure_active_profile_summary_loaded()
        with self.state_lock:
            if not force and self.active_profile_summary_is_fresh():
                return
        get_background_task_manager(self).start_flagged_refresh(
            self,
            "pending_profile_summary_refresh",
            self._refresh_active_profile_summary_worker,
        )

    def _refresh_active_profile_summary_worker(self):
        try:
            self.refresh_active_profile_summary()
        finally:
            get_background_task_manager(self).finish_flagged_refresh(self, "pending_profile_summary_refresh")

    def refresh_active_profile_summary(self):
        account_provider = self.profile_providers.account
        if not account_provider.has_owned_api_key() or not account_provider.api_key_bound_to_active_user():
            return

        steamid64 = account_provider.active_steamid64()
        if not steamid64:
            return

        summary = self.fetch_active_profile_summary(steamid64)
        if not summary:
            return

        with self.state_lock:
            self.active_profile_summary = summary
            self.active_profile_summary_loaded = True
        self.save_profile_cache(summary)

    def get_active_profile_summary(self):
        account_provider = self.profile_providers.account
        if not account_provider.has_owned_api_key() or not account_provider.api_key_bound_to_active_user():
            return None

        self.ensure_active_profile_summary_loaded()
        steamid64 = account_provider.active_steamid64()
        if not steamid64:
            return None

        with self.state_lock:
            summary = dict(self.active_profile_summary)

        if not is_profile_summary_for_steamid64(summary, steamid64):
            self.schedule_active_profile_summary_refresh(force=True)
            return None

        if not summary:
            self.schedule_active_profile_summary_refresh(force=True)
            return None

        if not self.active_profile_summary_is_fresh():
            self.schedule_active_profile_summary_refresh()
        return summary

    def get_active_profile_status(self):
        return get_profile_status_label(self.get_active_profile_summary(), tr=self.tr)

    def fetch_owned_app_ids_from_api(self, api_key, steamid64, timeout=3):
        return fetch_owned_app_ids(
            api_key,
            steamid64,
            self._http_get,
            normalize_api_key=self.profile_providers.owned_api.normalize_key,
            timeout=timeout,
        )

    def should_detect_owned_games_for_profile(self):
        return self.profile_providers.settings.should_detect_owned_games()

    def get_active_steam_avatar_icon(self):
        source_path = self.get_active_steam_avatar_path()
        if not source_path:
            return self.DEFAULT_ICON

        frame_path = self.get_active_steam_avatar_frame_path()
        if not frame_path:
            return str(source_path)

        composite_path = self.avatar_cache_dir / f"avatar_{source_path.stem}_framed.png"
        try:
            if (
                composite_path.exists()
                and composite_path.stat().st_mtime >= source_path.stat().st_mtime
                and composite_path.stat().st_mtime >= frame_path.stat().st_mtime
            ):
                return str(composite_path)
        except OSError:
            return str(source_path)

        if self.create_framed_avatar_icon(source_path, frame_path, composite_path):
            return str(composite_path)
        return str(source_path)

    def get_active_steam_avatar_path(self):
        if not self.steam_path:
            return None

        steamid64 = self.profile_providers.account.active_steamid64()
        if not steamid64:
            return None

        avatar_path = self.steam_path / "config" / "avatarcache" / f"{steamid64}.png"
        if avatar_path.exists():
            return avatar_path
        return None

    def load_avatar_frame_cache(self):
        if not self.avatar_frame_cache_file.exists():
            return {}
        cache_data = read_json_file(
            self.avatar_frame_cache_file,
            default={},
            logger=self.log_exception,
            error_message="Failed to load avatar frame cache",
        )
        return cache_data if isinstance(cache_data, dict) else {}

    def save_avatar_frame_cache(self, cache_data):
        write_json_file(
            self.avatar_frame_cache_file,
            cache_data,
            logger=self.log_exception,
            error_message="Failed to save avatar frame cache",
        )

    def get_active_steam_avatar_frame_path(self):
        account_provider = self.profile_providers.account
        if not account_provider.has_owned_api_key() or not account_provider.api_key_bound_to_active_user():
            return None

        steamid64 = account_provider.active_steamid64()
        if not steamid64:
            return None

        cache_data = self.load_avatar_frame_cache()
        cached_frame_path, cached_no_frame = get_cached_avatar_frame_state(
            cache_data,
            steamid64,
            self.avatar_cache_dir,
        )
        if cached_frame_path:
            return cached_frame_path
        if cached_no_frame:
            return None

        frame_data = self.fetch_active_avatar_frame_data(steamid64)
        if not frame_data:
            self.save_avatar_frame_cache(build_no_avatar_frame_cache_entry(steamid64))
            return None

        frame_name = f"avatar_frame_{frame_data['communityitemid']}.png"
        frame_path = self.avatar_cache_dir / frame_name
        if not frame_path.exists() and not self.download_avatar_frame_image(frame_data["image_url"], frame_path):
            return None

        self.save_avatar_frame_cache(build_avatar_frame_cache_entry(steamid64, frame_data, frame_name))
        return frame_path if frame_path.exists() else None

    def fetch_active_avatar_frame_data(self, steamid64):
        api_key = self.profile_providers.account.owned_api_key()
        if not api_key or not steamid64:
            return None

        try:
            return fetch_avatar_frame_data(api_key, steamid64, self._http_get, timeout=1.2)
        except Exception:
            self.log_exception("Failed to fetch active Steam avatar frame")
            return None

    def download_avatar_frame_image(self, image_url, save_path):
        try:
            return download_binary_file(self._http_get, image_url, save_path, timeout=2)
        except Exception:
            self.log_exception(f"Failed to download avatar frame: {image_url}")
            return False

    def create_framed_avatar_icon(self, avatar_path, frame_path, output_path):
        try:
            return compose_framed_avatar_icon(avatar_path, frame_path, output_path, Image)
        except Exception:
            self.log_exception(f"Failed to compose framed avatar icon from {avatar_path}")
            return False

    def owned_games_cache_is_fresh(self):
        account_provider = self.profile_providers.account
        if not account_provider.api_key_bound_to_active_user():
            return False
        with self.state_lock:
            return is_owned_games_cache_fresh(
                self.owned_games_cache_loaded,
                self.owned_games_steamid64,
                account_provider.active_steamid64(),
                self.owned_games_last_sync,
                self.CONFIG.cache.owned_games_cache_ttl_seconds,
                is_timestamp_fresh,
            )

    def schedule_owned_games_refresh(self, force=False):
        if not self.should_detect_owned_games_for_profile() or not self.profile_providers.account.api_key_bound_to_active_user():
            return

        now = time.time()
        with self.state_lock:
            should_schedule = should_schedule_owned_games_refresh(
                force,
                now,
                self.owned_games_last_attempt,
                self.CONFIG.cache.owned_games_retry_delay_seconds,
                self.owned_games_cache_is_fresh,
            )
            if not should_schedule:
                return
            self.owned_games_last_attempt = now
        get_background_task_manager(self).start_flagged_refresh(
            self,
            "pending_owned_games_refresh",
            self._refresh_owned_games_worker,
        )

    def _refresh_owned_games_worker(self):
        try:
            self.refresh_owned_games_cache()
        finally:
            get_background_task_manager(self).finish_flagged_refresh(self, "pending_owned_games_refresh")

    def refresh_owned_games_cache(self):
        account_provider = self.profile_providers.account
        if not self.should_detect_owned_games_for_profile() or not account_provider.api_key_bound_to_active_user():
            return

        steamid64 = account_provider.active_steamid64()
        api_key = account_provider.owned_api_key()
        if not steamid64:
            self.profile_providers.owned_api.clear_owned_games_cache()
            return
        if not api_key:
            return

        start_time = time.perf_counter()
        refresh_result = fetch_owned_games_refresh_result(
            self.fetch_owned_app_ids_from_api,
            api_key,
            steamid64,
            self.urllib3,
            timeout=3,
        )
        if refresh_result["should_log_error"]:
            self.log_exception("Failed to refresh owned Steam games")

        if refresh_result["success"]:
            with self.state_lock:
                self.owned_games_last_sync = time.time()
                self.owned_games_public_profile = True
                self.owned_games_steamid64 = steamid64
                self.owned_app_ids = refresh_result["owned_app_ids"]
                self.owned_game_playtimes = refresh_result["owned_game_playtimes"]
                self.owned_games_cache_loaded = True
            self.profile_providers.owned_api.save_owned_games_cache()
        else:
            with self.state_lock:
                if self.owned_games_steamid64 != steamid64:
                    self.owned_games_steamid64 = steamid64

        self.log_slow_call(
            "refresh_owned_games_cache",
            (time.perf_counter() - start_time) * 1000,
            build_owned_games_refresh_log_details(
                steamid64,
                refresh_result["owned_app_ids"],
                refresh_result["success"],
            ),
        )

    def is_owned_app(self, app_id):
        account_provider = self.profile_providers.account
        if not self.should_detect_owned_games_for_profile() or not app_id or not account_provider.api_key_bound_to_active_user():
            return False

        app_id = str(app_id)
        active_steamid64 = account_provider.active_steamid64()
        with self.state_lock:
            ownership_state = get_owned_app_state(
                app_id,
                self.owned_games_steamid64,
                active_steamid64,
                self.owned_app_ids,
                cache_is_fresh=False,
            )
        if ownership_state == "owned":
            return True

        if not self.owned_games_cache_is_fresh():
            self.schedule_owned_games_refresh()
        return False

    def get_active_account_ownership_state(self, app_id):
        account_provider = self.profile_providers.account
        if not self.should_detect_owned_games_for_profile() or not app_id or not account_provider.api_key_bound_to_active_user():
            return "unknown"

        app_id = str(app_id)
        active_steamid64 = account_provider.active_steamid64()
        with self.state_lock:
            cache_steamid64 = self.owned_games_steamid64
            owned_app_ids = set(self.owned_app_ids)

        ownership_state = get_owned_app_state(
            app_id,
            cache_steamid64,
            active_steamid64,
            owned_app_ids,
            cache_is_fresh=self.owned_games_cache_is_fresh(),
        )
        if ownership_state != "unknown":
            return ownership_state

        self.schedule_owned_games_refresh()
        return "unknown"
