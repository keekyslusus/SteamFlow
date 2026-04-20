import json
import threading
import time

from . import util_currency


class SteamPluginStorageMixin:
    def _read_json_file(self, path, error_message):
        try:
            with open(path, "r", encoding="utf-8") as file_obj:
                return json.load(file_obj)
        except Exception:
            self.log_exception(error_message)
            return None

    def _write_json_file(self, path, payload, error_message, indent=None):
        try:
            with open(path, "w", encoding="utf-8") as file_obj:
                json.dump(payload, file_obj, indent=indent)
            return True
        except Exception:
            self.log_exception(error_message)
            return False

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
        app_details_cache = cache_data.get("app_details_cache", {})
        if not isinstance(player_count_cache, dict):
            player_count_cache = {}
        if not isinstance(review_score_cache, dict):
            review_score_cache = {}
        if not isinstance(achievement_schema_cache, dict):
            achievement_schema_cache = {}
        if not isinstance(achievement_progress_cache, dict):
            achievement_progress_cache = {}
        if not isinstance(app_details_cache, dict):
            app_details_cache = {}

        with self.state_lock:
            self.player_count_cache = player_count_cache
            self.review_score_cache = review_score_cache
            self.achievement_schema_cache = achievement_schema_cache
            self.achievement_progress_cache = achievement_progress_cache
            self.app_details_cache = app_details_cache

    def load_owned_games_cache(self):
        if not self.owned_games_cache_file.exists():
            return

        cache_data = self._read_json_file(self.owned_games_cache_file, "Failed to load owned games cache")
        if not isinstance(cache_data, dict):
            return

        owned_app_ids = cache_data.get("owned_app_ids", [])
        owned_game_playtimes = cache_data.get("owned_game_playtimes", {})
        if not isinstance(owned_app_ids, list):
            owned_app_ids = []
        if not isinstance(owned_game_playtimes, dict):
            owned_game_playtimes = {}

        with self.state_lock:
            self.owned_games_last_attempt = float(cache_data.get("last_attempt", 0) or 0)
            self.owned_games_last_sync = float(cache_data.get("timestamp", 0) or 0)
            self.owned_games_public_profile = cache_data.get("public_profile")
            self.owned_games_steamid64 = str(cache_data.get("steamid64", "") or "") or None
            self.owned_app_ids = {str(app_id) for app_id in owned_app_ids if str(app_id).strip()}
            self.owned_game_playtimes = {
                str(app_id): int(playtime_minutes or 0)
                for app_id, playtime_minutes in owned_game_playtimes.items()
                if str(app_id).strip()
            }
            self.owned_games_cache_loaded = True

    def save_owned_games_cache(self):
        with self.state_lock:
            cache_data = {
                "last_attempt": self.owned_games_last_attempt,
                "timestamp": self.owned_games_last_sync,
                "public_profile": self.owned_games_public_profile,
                "steamid64": self.owned_games_steamid64,
                "owned_app_ids": sorted(self.owned_app_ids),
                "owned_game_playtimes": dict(self.owned_game_playtimes),
            }

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
        if not isinstance(cache_data, dict):
            return

        items = self.normalize_wishlist_items(cache_data.get("items", []))
        with self.state_lock:
            self.wishlist_last_attempt = float(cache_data.get("last_attempt", 0) or 0)
            self.wishlist_last_sync = float(cache_data.get("timestamp", 0) or 0)
            self.wishlist_steamid64 = str(cache_data.get("steamid64", "") or "") or None
            self.wishlist_items = items
            self.wishlist_cache_loaded = True

    def save_wishlist_cache(self):
        with self.state_lock:
            cache_data = {
                "last_attempt": self.wishlist_last_attempt,
                "timestamp": self.wishlist_last_sync,
                "steamid64": self.wishlist_steamid64,
                "items": list(self.wishlist_items),
            }

        self._write_json_file(self.wishlist_cache_file, cache_data, "Failed to save wishlist cache")

    def save_metric_caches(self, force=False):
        with self.state_lock:
            if not self.metric_cache_dirty:
                return
            if not force and (time.time() - self.last_metric_cache_save) < self.METRIC_CACHE_SAVE_INTERVAL_SECONDS:
                return
            cache_data = {
                "player_count_cache": dict(self.player_count_cache),
                "review_score_cache": dict(self.review_score_cache),
                "achievement_schema_cache": dict(self.achievement_schema_cache),
                "achievement_progress_cache": dict(self.achievement_progress_cache),
                "app_details_cache": dict(self.app_details_cache),
            }

        if self._write_json_file(self.metric_cache_file, cache_data, "Failed to save metric cache"):
            with self.state_lock:
                self.metric_cache_dirty = False
                self.last_metric_cache_save = time.time()

    def load_cached_country_code(self):
        if not self.should_show_prices():
            return "us"

        if self.country_cache_file.exists():
            cache_data = self._read_json_file(self.country_cache_file, "Failed to read country cache")
            if isinstance(cache_data, dict):
                cache_time = cache_data.get("timestamp", 0)
                if time.time() - cache_time < 7 * 24 * 60 * 60:
                    return util_currency.normalize_country_code(cache_data.get("country_code"))

        cc = self._fetch_country_code(timeout=1.5)
        if cc:
            self._save_country_code_cache(cc)
            return cc

        threading.Thread(target=self._update_country_code_async, daemon=True).start()
        return "us"

    def _save_country_code_cache(self, cc):
        self._write_json_file(
            self.country_cache_file,
            {"country_code": cc, "timestamp": time.time()},
            "Failed to save country code cache",
        )
