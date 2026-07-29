import time

from .cache_utils import read_json_file, write_json_file
from .constants import STEAMFLOW_CONFIG
from .localization import plugin_tr
from .providers import get_plugin_providers
from .steam_deck_service import (
    STEAM_DECK_COMPATIBILITY_LABEL_KEYS,
    fetch_deck_compatibility_categories,
    fetch_last_played_times,
    get_latest_deck_playtime,
    get_next_history_check_interval,
    is_deck_activity_recent,
    normalize_app_ids,
    normalize_steam_deck_cache_payload,
)
from .tasks import get_background_task_manager


class SteamPluginSteamDeckMixin:
    CONFIG = STEAMFLOW_CONFIG
    REQUIRED_PLUGIN_ATTRS = (
        "pending_steam_deck_history_refresh",
        "steam_deck_account_states",
        "steam_deck_cache_loaded",
        "steam_deck_cache_file",
        "steam_deck_compatibility_cache",
        "steam_deck_compatibility_last_failure",
        "state_lock",
    )
    REQUIRED_PLUGIN_METHODS = (
        "_http_get",
        "log_exception",
        "log_slow_call",
    )
    REQUIRED_PLUGIN_PROVIDERS = (
        "account",
        "settings",
    )

    @property
    def steam_deck_providers(self):
        return get_plugin_providers(self)

    def load_steam_deck_cache(self):
        cache_data = read_json_file(
            self.steam_deck_cache_file,
            default={},
            logger=self.log_exception,
            error_message="Failed to load Steam Deck cache",
        )
        normalized = normalize_steam_deck_cache_payload(cache_data)
        with self.state_lock:
            self.steam_deck_account_states = normalized["accounts"]
            self.steam_deck_compatibility_cache = normalized["compatibility"]
            self.steam_deck_compatibility_last_failure = normalized[
                "compatibility_last_failure"
            ]
            self.steam_deck_cache_loaded = True

    def ensure_steam_deck_cache_loaded(self):
        with self.state_lock:
            if self.steam_deck_cache_loaded:
                return
        self.load_steam_deck_cache()

    def save_steam_deck_cache(self):
        with self.state_lock:
            payload = {
                "accounts": dict(self.steam_deck_account_states),
                "compatibility": dict(self.steam_deck_compatibility_cache),
                "compatibility_last_failure": self.steam_deck_compatibility_last_failure,
            }
        write_json_file(
            self.steam_deck_cache_file,
            payload,
            logger=self.log_exception,
            error_message="Failed to save Steam Deck cache",
        )

    def _get_active_steam_deck_credentials(self):
        account_provider = self.steam_deck_providers.account
        if (
            not account_provider.has_owned_api_key()
            or not account_provider.api_key_bound_to_active_user()
        ):
            return None, None
        steamid64 = account_provider.active_steamid64()
        api_key = account_provider.owned_api_key()
        if not steamid64 or not api_key:
            return None, None
        return str(steamid64), api_key

    def get_steam_deck_account_state(self, steamid64=None):
        self.ensure_steam_deck_cache_loaded()
        if steamid64 is None:
            steamid64 = self.steam_deck_providers.account.active_steamid64()
        steamid64 = str(steamid64 or "").strip()
        if not steamid64:
            return {}
        with self.state_lock:
            return dict(self.steam_deck_account_states.get(steamid64, {}))

    def is_steam_deck_active(self, now=None, schedule_refresh=True):
        steamid64, api_key = self._get_active_steam_deck_credentials()
        if not steamid64 or not api_key:
            return False

        now = time.time() if now is None else float(now)
        account_state = self.get_steam_deck_account_state(steamid64)
        if schedule_refresh and now >= float(account_state.get("next_check_at", 0) or 0):
            self.schedule_steam_deck_history_refresh()
        return is_deck_activity_recent(
            account_state.get("last_deck_playtime"),
            now=now,
            activity_window_seconds=self.CONFIG.cache.steam_deck_activity_window_seconds,
        )

    def schedule_steam_deck_history_refresh(self, force=False):
        steamid64, api_key = self._get_active_steam_deck_credentials()
        if not steamid64 or not api_key:
            return False

        self.ensure_steam_deck_cache_loaded()
        now = time.time()
        account_state = self.get_steam_deck_account_state(steamid64)
        if not force and now < float(account_state.get("next_check_at", 0) or 0):
            return False
        return get_background_task_manager(self).start_flagged_refresh(
            self,
            "pending_steam_deck_history_refresh",
            self._refresh_steam_deck_history_worker,
        )

    def _refresh_steam_deck_history_worker(self):
        try:
            self.refresh_steam_deck_history()
        finally:
            get_background_task_manager(self).finish_flagged_refresh(
                self,
                "pending_steam_deck_history_refresh",
            )

    def refresh_steam_deck_history(self, now=None):
        steamid64, api_key = self._get_active_steam_deck_credentials()
        if not steamid64 or not api_key:
            return False

        self.ensure_steam_deck_cache_loaded()
        now = time.time() if now is None else float(now)
        with self.state_lock:
            previous_state = dict(self.steam_deck_account_states.get(steamid64, {}))
            self.steam_deck_account_states[steamid64] = {
                **previous_state,
                "last_attempt_at": now,
            }

        start_time = time.perf_counter()
        try:
            games = fetch_last_played_times(
                self._http_get,
                api_key,
                timeout=3,
            )
        except Exception:
            with self.state_lock:
                self.steam_deck_account_states[steamid64] = {
                    **self.steam_deck_account_states.get(steamid64, {}),
                    "next_check_at": now
                    + self.CONFIG.cache.steam_deck_failure_retry_seconds,
                }
            self.save_steam_deck_cache()
            self.log_exception("Failed to refresh Steam Deck play history")
            return False
        finally:
            self.log_slow_call(
                "refresh_steam_deck_history",
                (time.perf_counter() - start_time) * 1000,
                f"steamid64={steamid64}",
            )

        latest_deck_playtime = max(
            int(previous_state.get("last_deck_playtime", 0) or 0),
            get_latest_deck_playtime(games),
        )
        ever_detected = bool(
            previous_state.get("ever_detected")
            or latest_deck_playtime > 0
        )
        negative_check_count = (
            0
            if ever_detected
            else int(previous_state.get("negative_check_count", 0) or 0) + 1
        )
        interval_seconds = get_next_history_check_interval(
            ever_detected,
            negative_check_count,
            initial_intervals_seconds=self.CONFIG.cache.steam_deck_initial_check_intervals_seconds,
            detected_interval_seconds=self.CONFIG.cache.steam_deck_detected_check_interval_seconds,
        )
        with self.state_lock:
            self.steam_deck_account_states[steamid64] = {
                "last_attempt_at": now,
                "last_checked_at": now,
                "next_check_at": now + interval_seconds,
                "last_deck_playtime": latest_deck_playtime,
                "ever_detected": ever_detected,
                "negative_check_count": negative_check_count,
            }
        self.save_steam_deck_cache()
        return True

    def get_steam_deck_compatibility_categories(self, app_ids, now=None):
        if not self.is_steam_deck_active(now=now):
            return {}

        self.ensure_steam_deck_cache_loaded()
        app_ids = normalize_app_ids(app_ids)
        if not app_ids:
            return {}
        now = time.time() if now is None else float(now)
        ttl_seconds = self.CONFIG.cache.steam_deck_compatibility_ttl_seconds

        with self.state_lock:
            cached_entries = {
                app_id: dict(self.steam_deck_compatibility_cache.get(app_id, {}))
                for app_id in app_ids
            }
            last_failure = self.steam_deck_compatibility_last_failure

        categories = {
            app_id: int(entry.get("category", 0) or 0)
            for app_id, entry in cached_entries.items()
            if entry
        }
        missing_app_ids = [
            app_id
            for app_id, entry in cached_entries.items()
            if not entry
            or now - float(entry.get("timestamp", 0) or 0) >= ttl_seconds
        ]
        if not missing_app_ids:
            return categories
        if (
            last_failure
            and now - float(last_failure)
            < self.CONFIG.cache.steam_deck_compatibility_failure_retry_seconds
        ):
            return categories

        settings_provider = self.steam_deck_providers.settings
        start_time = time.perf_counter()
        try:
            fetched = fetch_deck_compatibility_categories(
                self._http_get,
                missing_app_ids,
                country_code=settings_provider.country_code(),
                language=settings_provider.steam_language(),
                timeout=1.2,
            )
        except Exception:
            with self.state_lock:
                self.steam_deck_compatibility_last_failure = now
            self.save_steam_deck_cache()
            self.log_exception("Failed to fetch Steam Deck compatibility")
            return categories
        finally:
            self.log_slow_call(
                "fetch_steam_deck_compatibility",
                (time.perf_counter() - start_time) * 1000,
                f"count={len(missing_app_ids)}",
            )

        with self.state_lock:
            for app_id, category in fetched.items():
                self.steam_deck_compatibility_cache[app_id] = {
                    "category": int(category),
                    "timestamp": now,
                }
            self.steam_deck_compatibility_last_failure = 0
        categories.update(fetched)
        self.save_steam_deck_cache()
        return categories

    def get_steam_deck_compatibility_label(self, category):
        if not self.is_steam_deck_active():
            return ""
        try:
            category = int(category)
        except (TypeError, ValueError):
            return ""
        key = STEAM_DECK_COMPATIBILITY_LABEL_KEYS.get(category)
        return plugin_tr(self, key) if key else ""
