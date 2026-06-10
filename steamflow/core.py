import re
import threading
import time
import traceback

from . import util_currency, util_steam_date
from .cache_utils import (
    cleanup_timestamped_cache_entries,
    get_timestamped_cache_entry_state,
    is_timestamp_fresh,
    update_timestamped_cache_entry,
)
from .constants import STEAMFLOW_CONFIG
from .http_client import http_get_json, http_pool_get, http_pool_request
from .localization import Localizer, resolve_configured_locale
from .providers import get_plugin_providers
from .secure_storage import (
    DATA_BLOB as SecureDataBlob,
    build_data_blob,
    protect_dpapi_bytes,
    read_protected_text,
    unprotect_dpapi_bytes,
    write_protected_text,
)
from .tasks import get_background_task_manager


class SteamPluginCoreMixin:
    CONFIG = STEAMFLOW_CONFIG
    DPAPI_ENTROPY = b"SteamFlow-OwnedGames-Key-v1"
    DATA_BLOB = SecureDataBlob
    STEAM_WEB_API_KEY_PATTERN = re.compile(r"^[A-Fa-f0-9]{32}$")
    REQUIRED_PLUGIN_ATTRS = (
        "store_collection_cache",
        "store_user_preferences_cache",
    )
    REQUIRED_PLUGIN_PROVIDERS = (
        "account",
        "owned_api",
        "runtime",
        "wishlist",
    )

    @property
    def core_providers(self):
        return get_plugin_providers(self)

    def configure_logger(self):
        self.logger_level("info")

    def log(self, level, message):
        getattr(self.logger, level.lower(), self.logger.info)(message)

    def log_exception(self, message):
        self.logger.error("%s\n%s", message, traceback.format_exc(limit=3).strip())

    def _http_get(self, url, timeout, headers=None):
        return http_pool_get(self.http_pool, self.urllib3, url, timeout=timeout, headers=headers)

    def _prewarm_connections(self):
        start_time = time.perf_counter()
        for url in ("https://store.steampowered.com/", "https://api.steampowered.com/"):
            try:
                http_pool_request(self.http_pool, self.urllib3, "HEAD", url, timeout=2)
            except Exception:
                pass
        self.log_slow_call("prewarm_connections", (time.perf_counter() - start_time) * 1000)

    def add_result(self, result):
        action = result.get("JsonRPCAction", {})
        self.add_item(
            title=result["Title"],
            subtitle=result.get("SubTitle", ""),
            icon=result.get("IcoPath", self.DEFAULT_ICON),
            method=action.get("method"),
            parameters=action.get("parameters"),
            context=result.get("ContextData"),
            score=result.get("Score", 0),
            dont_hide=action.get("dontHideAfterAction", False),
        )

    def build_action(self, method, *parameters):
        return {"method": method, "parameters": list(parameters)}

    def get_current_plugin_keyword(self):
        try:
            plugin_settings = self.app_settings.get("PluginSettings", {}).get("Plugins", {}).get(self.id, {})
        except Exception:
            plugin_settings = {}

        for setting_name in ("UserKeywords", "ActionKeywords"):
            keywords = plugin_settings.get(setting_name)
            if isinstance(keywords, list):
                for keyword in keywords:
                    normalized = str(keyword or "").strip()
                    if normalized:
                        return normalized
            else:
                normalized = str(keywords or "").strip()
                if normalized:
                    return normalized

        return str(getattr(self, "user_keyword", "") or getattr(self, "action_keyword", "") or "steam").strip()

    def build_plugin_query(self, *parts):
        keyword = self.get_current_plugin_keyword()
        suffix = " ".join(str(part).strip() for part in parts if str(part).strip())
        return f"{keyword} {suffix}".strip()

    def build_change_query_action(self, query, requery=True, keep_open=True):
        return {
            "method": "change_query",
            "parameters": [str(query or ""), bool(requery)],
            "dontHideAfterAction": bool(keep_open),
        }

    def build_result(self, title, subtitle, icon_path=None, action=None, context_data=None, **extra_fields):
        result = {
            "Title": title,
            "SubTitle": subtitle,
            "IcoPath": icon_path or self.DEFAULT_ICON,
        }
        if context_data is not None:
            result["ContextData"] = context_data
        if action is not None:
            result["JsonRPCAction"] = action
        result.update(extra_fields)
        return result

    def get_language(self):
        return resolve_configured_locale(self.settings.get("language", "auto"))

    def get_steam_language(self):
        return Localizer(self.get_language()).steam_language

    def tr(self, key, default=None, **values):
        return Localizer(self.get_language()).tr(key, default=default, **values)

    def build_context_data(
        self,
        app_id=None,
        name=None,
        install_path=None,
        is_owned=None,
        refund_state=None,
        playtime_minutes=None,
        has_current_account_local_data=None,
        coming_soon=None,
        result_source=None,
        store_type=None,
        is_free=None,
        has_price=None,
        is_wishlisted=None,
        wishlist_actions_enabled=None,
        steamid64=None,
    ):
        data = {}
        if app_id is not None:
            data["app_id"] = str(app_id)
        if name is not None:
            data["name"] = name
        if install_path:
            data["install_path"] = install_path
        if is_owned is not None:
            data["is_owned"] = bool(is_owned)
        if refund_state:
            data["refund_state"] = str(refund_state)
        if playtime_minutes is not None:
            data["playtime_minutes"] = int(playtime_minutes)
        if has_current_account_local_data is not None:
            data["has_current_account_local_data"] = bool(has_current_account_local_data)
        if coming_soon is not None:
            data["coming_soon"] = bool(coming_soon)
        if result_source:
            data["result_source"] = str(result_source)
        if store_type:
            data["store_type"] = str(store_type)
        if is_free is not None:
            data["is_free"] = bool(is_free)
        if has_price is not None:
            data["has_price"] = bool(has_price)
        if is_wishlisted is not None:
            data["is_wishlisted"] = bool(is_wishlisted)
        if wishlist_actions_enabled is not None:
            data["wishlist_actions_enabled"] = bool(wishlist_actions_enabled)
        if steamid64:
            data["steamid64"] = str(steamid64)
        return data

    def get_setting_bool(self, name, default):
        value = self.settings.get(name, default)
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return bool(value)

    def get_blacklisted_app_ids(self):
        raw_value = self.settings.get(
            "blacklisted_app_ids",
            ",".join(sorted(self.CONFIG.default_blacklisted_app_ids)),
        )
        if isinstance(raw_value, list):
            parts = raw_value
        else:
            parts = str(raw_value).replace("\n", ",").split(",")

        blacklist = set(self.CONFIG.default_blacklisted_app_ids)
        for part in parts:
            app_id = str(part).strip()
            if app_id:
                blacklist.add(app_id)
        if self.should_hide_hidden_games():
            blacklist.update(self.load_hidden_app_ids())
        return blacklist

    def should_show_platforms(self):
        return self.get_setting_bool("show_platforms", False)

    def should_show_player_count(self):
        return self.get_setting_bool("show_player_count", True)

    def should_show_positive_reviews(self):
        return self.get_setting_bool("show_positive_reviews", True)

    def should_sort_local_by_recent(self):
        return self.get_setting_bool("sort_local_by_recent", True)

    def should_hide_hidden_games(self):
        return self.get_setting_bool("hide_hidden_games", True)

    def should_show_prices(self):
        return self.get_setting_bool("show_prices", True)

    def should_show_playtime(self):
        return self.get_setting_bool("show_playtime", True)

    def should_show_last_played(self):
        return self.get_setting_bool("show_last_played", True)

    def should_show_achievements(self):
        return self.get_setting_bool("show_achievements", True)

    def should_offer_refund_shortcut(self):
        return True

    def should_log_performance(self):
        return self.get_setting_bool("enable_perf_logging", False)

    def should_detect_owned_games(self):
        return True

    def should_show_steamdb_context_menu(self):
        return self.get_setting_bool("show_steamdb_context_menu", True)

    def should_show_csrin_context_menu(self):
        return self.get_setting_bool("show_csrin_context_menu", True)

    def normalize_steam_web_api_key(self, value):
        normalized = str(value or "").strip()
        if self.STEAM_WEB_API_KEY_PATTERN.fullmatch(normalized):
            return normalized.upper()
        return ""

    def mark_timing(self, timings, stage_name, start_time):
        if timings is None:
            return
        timings.append((stage_name, (time.perf_counter() - start_time) * 1000))

    def log_slow_call(self, label, duration_ms, details=None):
        if not self.should_log_performance() or duration_ms < self.CONFIG.performance.stage_log_threshold_ms:
            return
        suffix = f" {details}" if details else ""
        self.log("info", f"Perf {label}={duration_ms:.1f}ms{suffix}")

    def log_query_profile(self, search_term, timings, total_ms, result_count):
        if not self.should_log_performance():
            return
        if total_ms < self.CONFIG.performance.query_log_threshold_ms and all(
            duration_ms < self.CONFIG.performance.stage_log_threshold_ms for _stage_name, duration_ms in timings
        ):
            return

        stage_summary = ", ".join(
            f"{stage_name}={duration_ms:.1f}ms"
            for stage_name, duration_ms in sorted(timings, key=lambda item: item[1], reverse=True)
        )
        query_label = search_term if search_term else "<empty>"
        self.log(
            "info",
            f"Perf query='{query_label}' total={total_ms:.1f}ms results={result_count}; {stage_summary}",
        )

    def is_timestamp_fresh(self, timestamp, ttl_seconds):
        return is_timestamp_fresh(timestamp, ttl_seconds)

    def get_country_code(self):
        with self.state_lock:
            return self.country_code

    def _build_data_blob(self, data):
        return build_data_blob(data)

    def _protect_dpapi_bytes(self, raw_bytes):
        return protect_dpapi_bytes(raw_bytes, self.DPAPI_ENTROPY)

    def _unprotect_dpapi_bytes(self, protected_bytes):
        return unprotect_dpapi_bytes(protected_bytes, self.DPAPI_ENTROPY)

    def get_owned_api_key(self):
        with self.state_lock:
            if self.owned_api_key_value:
                return self.owned_api_key_value

        if not self.owned_api_key_file.exists():
            return None

        try:
            api_key = self.normalize_steam_web_api_key(
                read_protected_text(self.owned_api_key_file, self.DPAPI_ENTROPY)
            )
            if not api_key:
                return None
            with self.state_lock:
                self.owned_api_key_value = api_key
            return api_key
        except Exception:
            self.log_exception("Failed to read Steam API key")
            return None

    def has_owned_api_key(self):
        return bool(self.get_owned_api_key())

    def save_owned_api_key(self, api_key, bound_steamid64, persona_name=None, account_name=None):
        normalized_key = self.normalize_steam_web_api_key(api_key)
        if not normalized_key:
            raise ValueError("Invalid Steam Web API key format")

        write_protected_text(self.owned_api_key_file, normalized_key, self.DPAPI_ENTROPY)

        with self.state_lock:
            self.owned_api_key_value = normalized_key
            self.owned_api_key_bound_steamid64 = str(bound_steamid64) if bound_steamid64 else None
            self.owned_api_key_persona_name = persona_name
            self.owned_api_key_account_name = account_name
            self.owned_api_key_last4 = normalized_key[-4:]
            self.owned_api_key_loaded = True
        self.save_owned_api_key_metadata()

    def clear_owned_games_cache(self):
        with self.state_lock:
            self.owned_games_last_attempt = 0
            self.owned_games_last_sync = 0
            self.owned_games_public_profile = None
            self.owned_games_steamid64 = None
            self.owned_app_ids = set()
            self.owned_game_playtimes = {}
            self.owned_games_cache_loaded = True
        self.core_providers.owned_api.save_owned_games_cache()

    def remove_owned_api_key(self):
        try:
            if self.owned_api_key_file.exists():
                self.owned_api_key_file.unlink()
            if self.owned_api_key_meta_file.exists():
                self.owned_api_key_meta_file.unlink()
        except Exception:
            self.log_exception("Failed to remove Steam API key files")

        with self.state_lock:
            self.owned_api_key_value = None
            self.owned_api_key_bound_steamid64 = None
            self.owned_api_key_persona_name = None
            self.owned_api_key_account_name = None
            self.owned_api_key_last4 = None
            self.owned_api_key_loaded = True
        self.clear_owned_games_cache()
        self.core_providers.wishlist.clear_cache()

    def is_owned_api_key_bound_to_active_user(self):
        active_steamid64 = self.core_providers.account.active_steamid64()
        with self.state_lock:
            bound_steamid64 = self.owned_api_key_bound_steamid64
        return bool(active_steamid64 and bound_steamid64 and active_steamid64 == bound_steamid64)

    def get_owned_games_status(self):
        account_provider = self.core_providers.account
        active_steamid64 = account_provider.active_steamid64()
        active_user_details = account_provider.user_details(active_steamid64)
        with self.state_lock:
            bound_steamid64 = self.owned_api_key_bound_steamid64
            persona_name = self.owned_api_key_persona_name
            account_name = self.owned_api_key_account_name
            last_sync = self.owned_games_last_sync

        if not account_provider.has_owned_api_key():
            return (
                self.tr("api.status_not_configured"),
                self.tr("api.not_configured_subtitle"),
            )

        account_label = persona_name or account_name or self.tr("api.steam_account")
        active_account_label = (
            active_user_details.get("persona_name")
            or active_user_details.get("account_name")
            or self.tr("api.steam_account")
        )
        if active_steamid64 and bound_steamid64 and active_steamid64 != bound_steamid64:
            return (
                self.tr("api.status_bound_other"),
                self.tr(
                    "api.bound_other_subtitle",
                    account_label=account_label,
                    active_account_label=active_account_label,
                ),
            )

        if last_sync:
            age_minutes = max(0, int((time.time() - last_sync) / 60))
            return (
                self.tr("api.status_connected"),
                self.tr(
                    "api.connected_last_sync",
                    account_label=account_label,
                    last_sync=util_steam_date.format_relative_minutes_ago(age_minutes, tr=self.tr),
                ),
            )

        return (
            self.tr("api.status_connected"),
            self.tr(
                "api.connected_first_sync",
                account_label=account_label,
            ),
        )

    def update_player_count_cache(self, app_id, player_count):
        if player_count is None:
            return
        self._update_metric_cache_entry(
            self.player_count_cache,
            app_id,
            player_count=player_count,
        )

    def update_review_score_cache(self, app_id, summary):
        if summary is None:
            return
        self._update_metric_cache_entry(
            self.review_score_cache,
            app_id,
            summary=summary,
        )

    def _update_metric_cache_entry(self, cache, key, **payload):
        with self.state_lock:
            updated = update_timestamped_cache_entry(cache, key, payload)
            if updated:
                self.metric_cache_dirty = True
        self.core_providers.runtime.save_metric_caches()

    def get_cache_entry_state(self, cache, key, ttl_seconds):
        with self.state_lock:
            return get_timestamped_cache_entry_state(cache, key, ttl_seconds)

    def start_daemon_task(self, target, *args, **kwargs):
        return get_background_task_manager(self).start(target, *args, **kwargs)

    def start_delayed_daemon_task(self, delay_seconds, target, *args, **kwargs):
        return get_background_task_manager(self).start_delayed(delay_seconds, target, *args, **kwargs)

    def start_flagged_refresh(self, pending_flag_name, refresh_method):
        return get_background_task_manager(self).start_flagged_refresh(self, pending_flag_name, refresh_method)

    def finish_flagged_refresh(self, pending_flag_name):
        get_background_task_manager(self).finish_flagged_refresh(self, pending_flag_name)

    def start_keyed_refresh(self, pending_set_name, key, refresh_method):
        return get_background_task_manager(self).start_keyed_refresh(self, pending_set_name, key, refresh_method)

    def finish_keyed_refresh(self, pending_set_name, key):
        get_background_task_manager(self).finish_keyed_refresh(self, pending_set_name, key)

    def start_metric_refresh(self, pending_set_name, key, refresh_method):
        self.start_keyed_refresh(pending_set_name, key, refresh_method)

    def finish_metric_refresh(self, pending_set_name, key):
        self.finish_keyed_refresh(pending_set_name, key)

    def _fetch_country_code(self, timeout=2):
        try:
            api_url = "http://ip-api.com/json/?fields=countryCode"
            data = http_get_json(self._http_get, api_url, timeout=timeout, headers=None)
            return util_currency.normalize_country_code(data.get("countryCode"))
        except Exception:
            self.log_exception("Failed to fetch country code")
            return None

    def _update_country_code_async(self):
        cc = self._fetch_country_code(timeout=2)
        if not cc:
            return
        with self.state_lock:
            self.country_code = cc
        self._save_country_code_cache(cc)

    def cleanup_image_cache(self):
        if not self.cache_dir.is_dir():
            return

        now = time.time()
        age_limit_seconds = 3 * 24 * 60 * 60
        try:
            for file_path in self.cache_dir.iterdir():
                if file_path.is_file() and (now - file_path.stat().st_mtime) > age_limit_seconds:
                    file_path.unlink()
        except Exception:
            self.log_exception("Failed to clean up image cache")

    def cleanup_cache_entries(self, cache, ttl_seconds):
        return cleanup_timestamped_cache_entries(cache, ttl_seconds)

    def cleanup_app_details_cache_files(self):
        return self.app_details_file_cache.cleanup()

    def cleanup_caches_if_needed(self):
        with self.state_lock:
            if time.time() - self.last_cache_cleanup < self.CONFIG.cache.cleanup_interval_seconds:
                return
            self.cleanup_cache_entries(self.search_cache, self.CONFIG.cache.search_ttl_seconds)
            self.cleanup_cache_entries(
                self.store_collection_cache,
                self.CONFIG.cache.store_collection_stale_ttl_seconds,
            )
            self.cleanup_cache_entries(
                self.store_user_preferences_cache,
                self.CONFIG.cache.store_user_preferences_ttl_seconds,
            )
            player_cache_changed = self.cleanup_cache_entries(
                self.player_count_cache,
                self.CONFIG.cache.player_count_ttl_seconds,
            )
            review_cache_changed = self.cleanup_cache_entries(
                self.review_score_cache,
                self.CONFIG.cache.review_score_ttl_seconds,
            )
            achievement_schema_cache_changed = self.cleanup_cache_entries(
                self.achievement_schema_cache,
                self.CONFIG.cache.achievement_schema_ttl_seconds,
            )
            achievement_progress_cache_changed = self.cleanup_cache_entries(
                self.achievement_progress_cache,
                self.CONFIG.cache.achievement_progress_ttl_seconds,
            )
            if (
                player_cache_changed
                or review_cache_changed
                or achievement_schema_cache_changed
                or achievement_progress_cache_changed
            ):
                self.metric_cache_dirty = True
            self.last_cache_cleanup = time.time()
        self.core_providers.runtime.save_metric_caches()
