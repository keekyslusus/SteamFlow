import time

from . import util_currency
from .cache_utils import is_timestamp_fresh, read_json_file, write_json_file
from .constants import STEAMFLOW_CONFIG
from .providers import get_plugin_providers
from .profile_service import build_owned_games_cache_payload, normalize_owned_games_cache_payload
from .tasks import get_background_task_manager
from .wishlist_service import build_wishlist_cache_payload, normalize_wishlist_cache_payload


class SteamPluginStorageMixin:
    CONFIG = STEAMFLOW_CONFIG
    REQUIRED_PLUGIN_ATTRS = (
        "app_details_cache_dir",
        "country_cache_file",
        "metric_cache_file",
        "owned_api_key_meta_file",
        "owned_games_cache_file",
        "state_lock",
        "wishlist_cache_file",
    )
    REQUIRED_PLUGIN_METHODS = (
        "_fetch_country_code",
        "log_exception",
    )
    REQUIRED_PLUGIN_PROVIDERS = ("settings",)

    @property
    def storage_providers(self):
        return get_plugin_providers(self)

    def _read_json_file(self, path, error_message):
        return read_json_file(path, default=None, logger=self.log_exception, error_message=error_message)

    def _write_json_file(self, path, payload, error_message, indent=None):
        return write_json_file(
            path,
            payload,
            logger=self.log_exception,
            error_message=error_message,
            indent=indent,
        )

    def load_metric_caches(self):
        if not self.metric_cache_file.exists():
            return

        cache_data = self._read_json_file(self.metric_cache_file, "Failed to load metric cache")
        if not isinstance(cache_data, dict):
            return

        player_count_cache = cache_data.get("player_count_cache", {})
        review_score_cache = cache_data.get("review_score_cache", {})
        achievement_schema_cache = cache_data.get("achievement_schema_cache", {})
        achievement_progress_cache = cache_data.get("achievement_progress_cache", {})
        legacy_app_details_cache = cache_data.get("app_details_cache", {})
        if not isinstance(player_count_cache, dict):
            player_count_cache = {}
        if not isinstance(review_score_cache, dict):
            review_score_cache = {}
        if not isinstance(achievement_schema_cache, dict):
            achievement_schema_cache = {}
        if not isinstance(achievement_progress_cache, dict):
            achievement_progress_cache = {}
        if not isinstance(legacy_app_details_cache, dict):
            legacy_app_details_cache = {}

        with self.state_lock:
            self.player_count_cache = player_count_cache
            self.review_score_cache = review_score_cache
            self.achievement_schema_cache = achievement_schema_cache
            self.achievement_progress_cache = achievement_progress_cache
            self.app_details_cache = {}

        if "app_details_cache" in cache_data:
            if self.app_details_file_cache.migrate_legacy_entries(legacy_app_details_cache):
                cache_data.pop("app_details_cache", None)
                self._write_json_file(self.metric_cache_file, cache_data, "Failed to migrate app details cache")

    def load_owned_games_cache(self):
        if not self.owned_games_cache_file.exists():
            return

        cache_data = self._read_json_file(self.owned_games_cache_file, "Failed to load owned games cache")
        normalized_cache = normalize_owned_games_cache_payload(cache_data)
        if not normalized_cache:
            return

        with self.state_lock:
            self.owned_games_last_attempt = normalized_cache["last_attempt"]
            self.owned_games_last_sync = normalized_cache["last_sync"]
            self.owned_games_public_profile = normalized_cache["public_profile"]
            self.owned_games_steamid64 = normalized_cache["steamid64"]
            self.owned_app_ids = normalized_cache["owned_app_ids"]
            self.owned_game_playtimes = normalized_cache["owned_game_playtimes"]
            self.owned_games_cache_loaded = True

    def save_owned_games_cache(self):
        with self.state_lock:
            cache_data = build_owned_games_cache_payload(
                self.owned_games_last_attempt,
                self.owned_games_last_sync,
                self.owned_games_public_profile,
                self.owned_games_steamid64,
                self.owned_app_ids,
                self.owned_game_playtimes,
            )

        self._write_json_file(self.owned_games_cache_file, cache_data, "Failed to save owned games cache")

    def load_owned_api_key_metadata(self):
        if not self.owned_api_key_meta_file.exists():
            return

        metadata = self._read_json_file(self.owned_api_key_meta_file, "Failed to load Steam API key metadata")
        if not isinstance(metadata, dict):
            return

        with self.state_lock:
            self.owned_api_key_bound_steamid64 = str(metadata.get("bound_steamid64", "") or "") or None
            self.owned_api_key_persona_name = metadata.get("persona_name")
            self.owned_api_key_account_name = metadata.get("account_name")
            self.owned_api_key_last4 = metadata.get("key_last4")
            self.owned_api_key_loaded = True

    def save_owned_api_key_metadata(self):
        with self.state_lock:
            metadata = {
                "bound_steamid64": self.owned_api_key_bound_steamid64,
                "persona_name": self.owned_api_key_persona_name,
                "account_name": self.owned_api_key_account_name,
                "key_last4": self.owned_api_key_last4,
                "saved_at": int(time.time()),
            }

        self._write_json_file(self.owned_api_key_meta_file, metadata, "Failed to save Steam API key metadata", indent=2)

    def load_wishlist_cache(self):
        if not self.wishlist_cache_file.exists():
            return

        cache_data = self._read_json_file(self.wishlist_cache_file, "Failed to load wishlist cache")
        normalized_cache = normalize_wishlist_cache_payload(cache_data)
        if not normalized_cache:
            return

        with self.state_lock:
            self.wishlist_last_attempt = normalized_cache["last_attempt"]
            self.wishlist_last_sync = normalized_cache["last_sync"]
            self.wishlist_steamid64 = normalized_cache["steamid64"]
            self.wishlist_items = normalized_cache["items"]
            self.wishlist_cache_loaded = True

    def save_wishlist_cache(self):
        with self.state_lock:
            cache_data = build_wishlist_cache_payload(
                self.wishlist_last_attempt,
                self.wishlist_last_sync,
                self.wishlist_steamid64,
                self.wishlist_items,
            )

        self._write_json_file(self.wishlist_cache_file, cache_data, "Failed to save wishlist cache")

    def save_metric_caches(self, force=False):
        with self.state_lock:
            if not self.metric_cache_dirty:
                return
            if not force and (
                time.time() - self.last_metric_cache_save
            ) < self.CONFIG.cache.metric_cache_save_interval_seconds:
                return
            cache_data = {
                "player_count_cache": dict(self.player_count_cache),
                "review_score_cache": dict(self.review_score_cache),
                "achievement_schema_cache": dict(self.achievement_schema_cache),
                "achievement_progress_cache": dict(self.achievement_progress_cache),
            }

        if self._write_json_file(self.metric_cache_file, cache_data, "Failed to save metric cache"):
            with self.state_lock:
                self.metric_cache_dirty = False
                self.last_metric_cache_save = time.time()

    def load_cached_country_code(self):
        if not self.storage_providers.settings.should_show_prices():
            return "us"

        if self.country_cache_file.exists():
            cache_data = self._read_json_file(self.country_cache_file, "Failed to read country cache")
            if isinstance(cache_data, dict):
                if is_timestamp_fresh(cache_data.get("timestamp", 0), 7 * 24 * 60 * 60):
                    cached_country_code = util_currency.normalize_country_code(
                        cache_data.get("country_code"),
                        default=None,
                    )
                    if cached_country_code:
                        return cached_country_code

        cc = self._fetch_country_code(timeout=1.5)
        if cc:
            self._save_country_code_cache(cc)
            return cc

        get_background_task_manager(self).start(self._update_country_code_async)
        return "us"

    def _save_country_code_cache(self, cc):
        self._write_json_file(
            self.country_cache_file,
            {"country_code": cc, "timestamp": time.time()},
            "Failed to save country code cache",
        )
