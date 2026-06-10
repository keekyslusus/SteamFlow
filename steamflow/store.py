import time
from functools import cached_property

from .app_details import AppDetailsFileCache, fetch_app_details_metadata_with_http_get
from .cache_utils import build_timestamped_cache_entry, is_timestamp_fresh
from .constants import STEAMFLOW_CONFIG
from .localization import plugin_tr
from .providers import get_plugin_providers
from .session_token import SteamSessionTokenProvider
from .store_collections import (
    build_store_collection_cache_entry,
    fetch_featured_collections_games,
    fetch_ignored_app_ids,
    normalize_store_collection_name,
)
from .store_search import fetch_store_search_games


class SteamPluginStoreMixin:
    CONFIG = STEAMFLOW_CONFIG
    REQUIRED_PLUGIN_ATTRS = (
        "app_details_cache_dir",
        "app_details_cache",
        "secure_settings_dir",
        "search_cache",
        "state_lock",
        "store_collection_cache",
        "store_user_preferences_cache",
    )
    REQUIRED_PLUGIN_METHODS = (
        "_http_get",
        "_update_metric_cache_entry",
        "log_exception",
        "log_slow_call",
    )
    REQUIRED_PLUGIN_PROVIDERS = (
        "account",
        "runtime",
        "settings",
    )

    @property
    def store_providers(self):
        return get_plugin_providers(self)

    @cached_property
    def app_details_file_cache(self):
        return AppDetailsFileCache(self.app_details_cache_dir)

    def update_app_details_cache(self, app_id, metadata, success, country_code=None, steam_language=None):
        if not app_id:
            return
        if country_code is None:
            settings_provider = self.store_providers.settings
            country_code = settings_provider.country_code() if settings_provider.should_show_prices() else "us"
        if steam_language is None:
            steam_language = self.store_providers.settings.steam_language()
        entry = self.app_details_file_cache.write_entry(
            app_id,
            metadata,
            success=success,
            country_code=country_code,
            steam_language=steam_language,
        )
        if entry:
            with self.state_lock:
                self.app_details_cache[str(app_id)] = {
                    **entry,
                    "country_code": country_code,
                    "steam_language": steam_language,
                }

    def fetch_app_details_metadata(self, app_id, timeout=1.5):
        start_time = time.perf_counter()
        app_id = str(app_id or "").strip()
        try:
            settings_provider = self.store_providers.settings
            country_code = settings_provider.country_code() if settings_provider.should_show_prices() else "us"
            steam_language = settings_provider.steam_language()
            metadata = fetch_app_details_metadata_with_http_get(
                self._http_get,
                app_id,
                country_code=country_code,
                language=steam_language,
                timeout=timeout,
            )
            if not metadata:
                self.log_slow_call("fetch_app_details_metadata", (time.perf_counter() - start_time) * 1000, f"app_id={app_id} success=false")
                return None
            self.log_slow_call("fetch_app_details_metadata", (time.perf_counter() - start_time) * 1000, f"app_id={app_id}")
            return metadata
        except Exception:
            self.log_exception(f"Failed to fetch app details for app {app_id}")
            self.log_slow_call("fetch_app_details_metadata", (time.perf_counter() - start_time) * 1000, f"app_id={app_id}")
            return None

    def _refresh_app_details_worker(self, app_id):
        try:
            metadata = self.fetch_app_details_metadata(app_id)
            self.update_app_details_cache(app_id, metadata, success=metadata is not None)
        finally:
            self.store_providers.runtime.finish_metric_refresh("pending_app_details_refresh", app_id)

    def get_app_details_metadata(self, app_id, allow_network_on_miss=True, fetch_timeout=1.5):
        if not app_id:
            return None

        app_id = str(app_id)
        settings_provider = self.store_providers.settings
        country_code = settings_provider.country_code() if settings_provider.should_show_prices() else "us"
        steam_language = settings_provider.steam_language()
        with self.state_lock:
            cached_entry = self.app_details_cache.get(app_id)
        def entry_matches_language(entry):
            entry_language = entry.get("steam_language")
            return entry_language == steam_language or (steam_language == "english" and entry_language is None)

        if not cached_entry or cached_entry.get("country_code") != country_code or not entry_matches_language(cached_entry):
            cached_entry = self.app_details_file_cache.read_entry(app_id, country_code)
            if cached_entry and entry_matches_language(cached_entry):
                cached_entry = {**cached_entry, "country_code": country_code, "steam_language": steam_language}
                with self.state_lock:
                    self.app_details_cache[app_id] = cached_entry
            else:
                cached_entry = None

        if (
            cached_entry
            and cached_entry.get("country_code") == country_code
            and entry_matches_language(cached_entry)
        ):
            try:
                self.app_details_file_cache.touch_entry(app_id, country_code)
            except OSError:
                pass
            ttl_seconds = (
                self.CONFIG.cache.app_details_ttl_seconds
                if cached_entry.get("success")
                else self.CONFIG.cache.app_details_failure_ttl_seconds
            )
            is_fresh = is_timestamp_fresh(cached_entry.get("timestamp", 0), ttl_seconds)
            metadata = cached_entry.get("metadata") if cached_entry.get("success") else None
            if is_fresh:
                return metadata
            self.store_providers.runtime.start_metric_refresh("pending_app_details_refresh", app_id, self._refresh_app_details_worker)
            return metadata

        if not allow_network_on_miss:
            self.store_providers.runtime.start_metric_refresh("pending_app_details_refresh", app_id, self._refresh_app_details_worker)
            return None

        metadata = self.fetch_app_details_metadata(app_id, timeout=fetch_timeout)
        self.update_app_details_cache(
            app_id,
            metadata,
            success=metadata is not None,
            country_code=country_code,
            steam_language=steam_language,
        )
        return metadata

    def is_paid_base_game(self, app_id, allow_network_on_miss=True):
        metadata = self.get_app_details_metadata(app_id, allow_network_on_miss=allow_network_on_miss)
        if not metadata:
            return False
        return metadata.get("type") == "game" and metadata.get("is_free") is False

    def get_search_error_message(self, error):
        if isinstance(error, self.urllib3.exceptions.TimeoutError):
            return plugin_tr(self, "store.search_timeout")
        if isinstance(error, self.urllib3.exceptions.HTTPError):
            return plugin_tr(self, "store.search_http_error")
        return plugin_tr(self, "store.search_failed")

    def search_steam_api(self, search_term):
        providers = self.store_providers
        providers.runtime.cleanup_caches_if_needed()
        start_time = time.perf_counter()
        try:
            search_term = search_term.strip()
            if not search_term:
                return {"games": [], "error": None}

            settings_provider = providers.settings
            country_code = settings_provider.country_code() if settings_provider.should_show_prices() else "us"
            steam_language = settings_provider.steam_language()
            cache_key = (
                (search_term.lower(), country_code)
                if steam_language == "english"
                else (search_term.lower(), country_code, steam_language)
            )
            with self.state_lock:
                cached_entry = self.search_cache.get(cache_key)
            if cached_entry and is_timestamp_fresh(
                cached_entry.get("timestamp", 0),
                self.CONFIG.cache.search_ttl_seconds,
            ):
                return {"games": cached_entry["games"], "error": None}

            games = fetch_store_search_games(
                self._http_get,
                search_term,
                country_code=country_code,
                language=steam_language,
                blacklist=settings_provider.blacklisted_app_ids(),
                max_results=self.CONFIG.query.max_results,
                timeout=0.7,
            )

            with self.state_lock:
                self.search_cache[cache_key] = build_timestamped_cache_entry({"games": games})
            self.log_slow_call("search_steam_api", (time.perf_counter() - start_time) * 1000, f"query='{search_term}'")
            return {"games": games, "error": None}
        except Exception as error:
            self.log_exception(f"Steam search request failed for query: {search_term}")
            self.log_slow_call("search_steam_api", (time.perf_counter() - start_time) * 1000, f"query='{search_term}'")
            return {"games": [], "error": self.get_search_error_message(error)}

    def get_store_collection_ttl_seconds(self, collection_name):
        collection_name = normalize_store_collection_name(collection_name)
        if collection_name == "specials":
            return self.CONFIG.cache.store_specials_ttl_seconds
        if collection_name == "top_sellers":
            return self.CONFIG.cache.store_top_sellers_ttl_seconds
        return self.CONFIG.cache.store_top_sellers_ttl_seconds

    def get_store_collection_label(self, collection_name):
        collection_name = normalize_store_collection_name(collection_name)
        if collection_name == "top_sellers":
            return plugin_tr(self, "store.collection.top_sellers")
        if collection_name == "specials":
            return plugin_tr(self, "store.collection.specials")
        return plugin_tr(self, "store.collection_default")

    def get_store_user_ignored_app_ids(self):
        providers = self.store_providers
        steamid64 = providers.account.active_steamid64()
        if not steamid64:
            return set()

        cache_key = str(steamid64)
        with self.state_lock:
            cached_entry = self.store_user_preferences_cache.get(cache_key)
        if cached_entry and is_timestamp_fresh(
            cached_entry.get("timestamp", 0),
            self.CONFIG.cache.store_user_preferences_ttl_seconds,
        ):
            return set(cached_entry.get("ignored_app_ids", []))

        try:
            token_provider = SteamSessionTokenProvider(
                self.secure_settings_dir,
                steamid64,
                logger=getattr(self, "logger", None),
            )
            access_token = token_provider.get_saved_or_htmlcache_token()
            ignored_app_ids = (
                fetch_ignored_app_ids(self._http_get, access_token, timeout=1.2)
                if access_token
                else set()
            )
        except Exception:
            ignored_app_ids = set()

        with self.state_lock:
            self.store_user_preferences_cache[cache_key] = build_timestamped_cache_entry(
                {"ignored_app_ids": sorted(ignored_app_ids)}
            )
        return set(ignored_app_ids)

    def get_store_collection_blacklisted_app_ids(self):
        providers = self.store_providers
        blacklisted_app_ids = set(providers.settings.blacklisted_app_ids())
        owned_app_ids = getattr(self, "owned_app_ids", set()) or set()
        blacklisted_app_ids.update(str(app_id) for app_id in owned_app_ids)
        return blacklisted_app_ids

    def fetch_store_collection_games_by_name(self):
        providers = self.store_providers
        settings_provider = providers.settings
        country_code = settings_provider.country_code() if settings_provider.should_show_prices() else "us"
        return fetch_featured_collections_games(
            self._http_get,
            country_code=country_code,
            language=settings_provider.steam_language(),
            blacklist=self.get_store_collection_blacklisted_app_ids(),
            ignored_app_ids=self.get_store_user_ignored_app_ids(),
            max_results=self.CONFIG.query.max_store_collection_results,
            timeout=1.2,
        )

    def get_store_collection_games(self, collection_name):
        providers = self.store_providers
        providers.runtime.cleanup_caches_if_needed()
        collection_name = normalize_store_collection_name(collection_name)
        if not collection_name:
            return {
                "games": [],
                "error": plugin_tr(self, "store.collection_unknown"),
                "stale": False,
            }

        settings_provider = providers.settings
        country_code = settings_provider.country_code() if settings_provider.should_show_prices() else "us"
        steam_language = settings_provider.steam_language()
        cache_key = (collection_name, country_code, steam_language)
        fresh_ttl_seconds = self.get_store_collection_ttl_seconds(collection_name)
        now = time.time()

        with self.state_lock:
            cached_entry = self.store_collection_cache.get(cache_key)

        if cached_entry:
            cached_timestamp = float(cached_entry.get("timestamp", 0) or 0)
            cache_age = now - cached_timestamp if cached_timestamp else 0
            if cached_timestamp and cache_age < fresh_ttl_seconds:
                return {
                    "games": cached_entry.get("games", []),
                    "error": None,
                    "stale": False,
                    "age_seconds": cache_age,
                }
            if (
                cached_entry.get("error")
                and cached_timestamp
                and now - float(cached_entry.get("error_timestamp", 0) or 0)
                < self.CONFIG.cache.store_collection_failure_ttl_seconds
            ):
                return {
                    "games": cached_entry.get("games", []),
                    "error": cached_entry.get("error"),
                    "stale": bool(cached_entry.get("games")),
                    "age_seconds": cache_age,
                }

        try:
            games_by_collection = self.fetch_store_collection_games_by_name()
            with self.state_lock:
                for fetched_name, games in games_by_collection.items():
                    self.store_collection_cache[(fetched_name, country_code, steam_language)] = (
                        build_store_collection_cache_entry(games)
                    )
            games = games_by_collection.get(collection_name, [])
            return {"games": games, "error": None, "stale": False, "age_seconds": 0}
        except Exception as error:
            self.log_exception(f"Steam store collection request failed for {collection_name}")
            error_message = self.get_search_error_message(error)
            cached_games = cached_entry.get("games", []) if cached_entry else []
            cached_timestamp = float(cached_entry.get("timestamp", 0) or 0) if cached_entry else 0
            cache_age = now - cached_timestamp if cached_timestamp else None
            can_use_stale = bool(
                cached_games
                and cached_timestamp
                and cache_age < self.CONFIG.cache.store_collection_stale_ttl_seconds
            )
            with self.state_lock:
                self.store_collection_cache[cache_key] = build_store_collection_cache_entry(
                    cached_games,
                    error=error_message,
                    now=cached_timestamp or now,
                )
            return {
                "games": cached_games if can_use_stale else [],
                "error": error_message,
                "stale": can_use_stale,
                "age_seconds": cache_age,
            }
