import time

from .constants import STEAMFLOW_CONFIG
from .feature_health import (
    FEATURE_STEAM_FAVORITES,
    FEATURE_STEAM_SESSION_TOKEN,
    classify_feature_error,
)
from .friend_favorites_service import (
    build_friend_favorites_cache_payload,
    fetch_friend_favorite_accountids,
    get_cached_friend_favorites,
    is_friend_favorites_cache_fresh,
    normalize_friend_favorites_cache_payload,
)
from .friends_service import (
    FriendsListUnavailableError,
    build_friends_cache_payload,
    fetch_friends,
    group_playing_friends_by_app,
    is_friends_cache_fresh,
    is_friends_refresh_running,
    normalize_friends_cache_payload,
    release_friends_refresh_lock,
    should_schedule_friends_refresh,
    start_friends_refresh_worker_process,
    try_acquire_friends_refresh_lock,
    wait_for_friends_cache_update,
)
from .friends_ui_service import build_friends_results as build_friends_ui_results
from .localization import plugin_tr
from .providers import get_plugin_providers
from .session_token import SteamSessionTokenProvider


class SteamPluginFriendsMixin:
    CONFIG = STEAMFLOW_CONFIG
    REQUIRED_PLUGIN_PROVIDERS = ("account", "friends", "results")
    REQUIRED_PLUGIN_ATTRS = (
        "FRIENDS_ICON",
        "ONLINE_ICON",
        "OFFLINE_ICON",
        "INVISIBLE_ICON",
        "friends_cache_file",
        "friend_favorites_cache_file",
        "plugin_dir",
        "secure_settings_dir",
        "state_lock",
    )
    REQUIRED_PLUGIN_METHODS = (
        "_http_get",
        "_read_json_file",
        "_write_json_file",
        "feature_enabled",
        "log_exception",
        "record_feature_failure",
        "record_feature_success",
    )

    @property
    def friends_providers(self):
        return get_plugin_providers(self)

    def load_friends_cache(self):
        if not self.friends_cache_file.exists():
            return
        payload = self._read_json_file(self.friends_cache_file, "Failed to load friends cache")
        normalized = normalize_friends_cache_payload(payload)
        if not normalized:
            return
        with self.state_lock:
            self.friends_last_attempt = normalized["last_attempt"]
            self.friends_last_sync = normalized["last_sync"]
            self.friends_steamid64 = normalized["steamid64"]
            self.friends_items = normalized["items"]
            self.friends_last_error = normalized["error"]
            self.friends_cache_loaded = True

    def save_friends_cache(self):
        with self.state_lock:
            payload = build_friends_cache_payload(
                self.friends_last_attempt,
                self.friends_last_sync,
                self.friends_steamid64,
                self.friends_items,
                self.friends_last_error,
            )
        self._write_json_file(self.friends_cache_file, payload, "Failed to save friends cache")

    def load_friend_favorites_cache(self):
        payload = None
        if self.friend_favorites_cache_file.exists():
            payload = self._read_json_file(
                self.friend_favorites_cache_file,
                "Failed to load friend favorites cache",
            )
        normalized = normalize_friend_favorites_cache_payload(payload)
        with self.state_lock:
            self.friend_favorites_by_steamid = normalized
            self.friend_favorites_cache_loaded = True

    def save_friend_favorites_cache(self):
        with self.state_lock:
            payload = build_friend_favorites_cache_payload(
                self.friend_favorites_by_steamid
            )
        self._write_json_file(
            self.friend_favorites_cache_file,
            payload,
            "Failed to save friend favorites cache",
        )

    def ensure_friend_favorites_cache_loaded(self):
        with self.state_lock:
            if self.friend_favorites_cache_loaded:
                return
        self.load_friend_favorites_cache()

    def get_steam_session_token_for_favorites(self, steamid64):
        provider = SteamSessionTokenProvider(
            self.secure_settings_dir,
            steamid64,
            logger=getattr(self, "logger", None),
        )
        return provider.get_saved_or_htmlcache_token()

    def fetch_friend_favorites_from_api(self, access_token, timeout=3):
        return fetch_friend_favorite_accountids(
            access_token,
            self._http_get,
            timeout=timeout,
        )

    def get_friend_favorite_accountids(self):
        steamid64 = self.friends_providers.account.active_steamid64()
        if not steamid64:
            return set()
        self.ensure_friend_favorites_cache_loaded()
        with self.state_lock:
            cached_accounts = dict(self.friend_favorites_by_steamid)
        cached_accountids, _timestamp = get_cached_friend_favorites(
            cached_accounts,
            steamid64,
        )
        if is_friend_favorites_cache_fresh(
            cached_accounts,
            steamid64,
            self.CONFIG.cache.friend_favorites_ttl_seconds,
        ):
            return cached_accountids
        if not self.feature_enabled(FEATURE_STEAM_FAVORITES) or not self.feature_enabled(
            FEATURE_STEAM_SESSION_TOKEN
        ):
            return cached_accountids

        try:
            access_token = self.get_steam_session_token_for_favorites(steamid64)
            if not access_token:
                raise RuntimeError(
                    f"No matching Steam webapi_token found for {steamid64}"
                )
            accountids = set(
                self.fetch_friend_favorites_from_api(access_token, timeout=3)
            )
        except Exception as error:
            self.record_feature_failure(
                FEATURE_STEAM_FAVORITES,
                error,
                reason=classify_feature_error(error, FEATURE_STEAM_FAVORITES),
            )
            self.log_exception("Failed to fetch Steam friend favorites")
            return cached_accountids

        with self.state_lock:
            accounts = dict(self.friend_favorites_by_steamid)
            accounts[str(steamid64)] = {
                "timestamp": time.time(),
                "accountids": accountids,
            }
            self.friend_favorites_by_steamid = accounts
        self.save_friend_favorites_cache()
        self.record_feature_success(FEATURE_STEAM_FAVORITES)
        return accountids

    def ensure_friends_cache_loaded(self):
        with self.state_lock:
            if self.friends_cache_loaded:
                return
        self.friends_providers.friends.load_cache()
        with self.state_lock:
            self.friends_cache_loaded = True

    def clear_friends_cache(self):
        with self.state_lock:
            self.friends_last_attempt = 0
            self.friends_last_sync = 0
            self.friends_steamid64 = None
            self.friends_items = []
            self.friends_last_error = ""
            self.friends_cache_loaded = True
        self.friends_providers.friends.save_cache()

    def friends_cache_is_fresh(self, steamid64):
        self.ensure_friends_cache_loaded()
        with self.state_lock:
            return is_friends_cache_fresh(
                steamid64,
                self.friends_steamid64,
                self.friends_last_sync,
                self.CONFIG.cache.friends_ttl_seconds,
            )

    def fetch_friends_from_api(self, api_key, steamid64, timeout=3):
        return fetch_friends(api_key, steamid64, self._http_get, timeout=timeout)

    def start_friends_refresh_worker(self):
        return start_friends_refresh_worker_process(self.plugin_dir)

    def schedule_friends_refresh(self):
        account = self.friends_providers.account
        if not account.has_owned_api_key() or not account.api_key_bound_to_active_user():
            return False
        steamid64 = account.active_steamid64()
        if not steamid64:
            return False

        self.ensure_friends_cache_loaded()
        with self.state_lock:
            cached_steamid64 = self.friends_steamid64
            last_sync = self.friends_last_sync
            last_attempt = self.friends_last_attempt
            error = self.friends_last_error
        if not should_schedule_friends_refresh(
            steamid64,
            cached_steamid64,
            last_sync,
            last_attempt,
            error,
            self.CONFIG.cache.friends_ttl_seconds,
            self.CONFIG.cache.friends_retry_delay_seconds,
        ):
            return False
        if is_friends_refresh_running(self.friends_cache_file):
            return False
        try:
            return self.start_friends_refresh_worker() is not None
        except Exception:
            self.log_exception("Failed to start Steam friends refresh worker")
            return False

    def refresh_friends(self):
        account = self.friends_providers.account
        if not account.has_owned_api_key() or not account.api_key_bound_to_active_user():
            return False
        api_key = account.owned_api_key()
        steamid64 = account.active_steamid64()
        if not api_key or not steamid64:
            return False
        refresh_lock = try_acquire_friends_refresh_lock(self.friends_cache_file)
        if refresh_lock is None:
            return None
        try:
            with self.state_lock:
                self.friends_steamid64 = steamid64
                self.friends_cache_loaded = True
                self.friends_last_attempt = time.time()
                self.friends_last_error = ""
            self.friends_providers.friends.save_cache()
            try:
                items = self.fetch_friends_from_api(api_key, steamid64, timeout=3)
            except FriendsListUnavailableError:
                with self.state_lock:
                    self.friends_last_error = "private"
                self.friends_providers.friends.save_cache()
                return False
            except Exception:
                self.log_exception("Failed to fetch Steam friends")
                with self.state_lock:
                    self.friends_last_error = "request_failed"
                self.friends_providers.friends.save_cache()
                return False
            with self.state_lock:
                self.friends_items = items
                self.friends_steamid64 = steamid64
                self.friends_last_sync = time.time()
                self.friends_last_attempt = self.friends_last_sync
                self.friends_last_error = ""
                self.friends_cache_loaded = True
            self.friends_providers.friends.save_cache()
            return True
        finally:
            release_friends_refresh_lock(refresh_lock)

    def get_friends(self):
        account = self.friends_providers.account
        reasons = self.CONFIG.availability_reasons
        if not account.has_owned_api_key():
            return [], reasons.api_not_configured
        if not account.api_key_bound_to_active_user():
            return [], reasons.api_bound_to_another_account
        steamid64 = account.active_steamid64()
        if not steamid64:
            return [], reasons.no_active_account

        self.ensure_friends_cache_loaded()
        with self.state_lock:
            items = list(self.friends_items)
            cached_steamid64 = self.friends_steamid64
            error = self.friends_last_error
            last_attempt = self.friends_last_attempt
        if cached_steamid64 == steamid64 and self.friends_cache_is_fresh(steamid64):
            return ([], error) if error else (items, None)
        if (
            cached_steamid64 == steamid64
            and error
            and time.time() - last_attempt < self.CONFIG.cache.friends_retry_delay_seconds
        ):
            return [], error

        refreshed = self.refresh_friends()
        if refreshed is None:
            updated_cache = wait_for_friends_cache_update(
                self.friends_cache_file,
                steamid64,
                last_attempt,
            )
            if not updated_cache:
                return [], "loading"
            with self.state_lock:
                self.friends_last_attempt = updated_cache["last_attempt"]
                self.friends_last_sync = updated_cache["last_sync"]
                self.friends_steamid64 = updated_cache["steamid64"]
                self.friends_items = updated_cache["items"]
                self.friends_last_error = updated_cache["error"]
                self.friends_cache_loaded = True
            if updated_cache["error"]:
                return [], updated_cache["error"]
            if is_friends_cache_fresh(
                steamid64,
                updated_cache["steamid64"],
                updated_cache["last_sync"],
                self.CONFIG.cache.friends_ttl_seconds,
            ):
                return list(updated_cache["items"]), None
            return [], "request_failed"
        with self.state_lock:
            refreshed_items = list(self.friends_items)
            refreshed_error = self.friends_last_error
        if refreshed:
            return refreshed_items, None
        return [], refreshed_error or "request_failed"

    def get_fresh_friends_playing_by_app(self):
        steamid64 = self.friends_providers.account.active_steamid64()
        if not steamid64:
            return {}
        self.ensure_friends_cache_loaded()
        with self.state_lock:
            cached_steamid64 = self.friends_steamid64
            items = list(self.friends_items)
        self.schedule_friends_refresh()
        if str(cached_steamid64 or "") != str(steamid64):
            return {}
        return group_playing_friends_by_app(items)

    def build_friends_results(self, search_term=""):
        items, error = self.get_friends()
        favorite_accountids = (
            self.get_friend_favorite_accountids() if not error else set()
        )
        return build_friends_ui_results(
            items,
            error,
            search_term,
            self.CONFIG.availability_reasons,
            self.friends_providers.results,
            {
                "friends": self.FRIENDS_ICON,
                "online": self.ONLINE_ICON,
                "away": self.INVISIBLE_ICON,
                "offline": self.OFFLINE_ICON,
            },
            self.CONFIG.query.max_friends_results,
            tr=getattr(self, "tr", None),
            favorite_accountids=favorite_accountids,
        )

    def refresh_steam_friends(self):
        ensure_startup = getattr(self, "ensure_startup_initialized", None)
        if callable(ensure_startup):
            ensure_startup()
        refreshed = self.refresh_friends()
        if refreshed is True:
            return plugin_tr(self, "friends.refresh_started")
        if refreshed is None:
            return plugin_tr(self, "friends.refresh_running")
        return plugin_tr(self, "friends.request_failed")
