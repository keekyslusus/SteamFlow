import ctypes
import json
import re
import threading
import time
import traceback
from ctypes import wintypes

from . import util_currency, util_steam_date


class SteamPluginCoreMixin:
    DPAPI_ENTROPY = b"SteamFlow-OwnedGames-Key-v1"
    STEAM_WEB_API_KEY_PATTERN = re.compile(r"^[A-Fa-f0-9]{32}$")

    def configure_logger(self):
        self.logger_level("info")

    def log(self, level, message):
        getattr(self.logger, level.lower(), self.logger.info)(message)

    def log_exception(self, message):
        self.logger.error("%s\n%s", message, traceback.format_exc(limit=3).strip())

    def _http_get(self, url, timeout, headers=None):
        response = self.http_pool.request(
            "GET",
            url,
            headers=headers,
            timeout=timeout,
            retries=False,
        )
        if response.status >= 400:
            raise self.urllib3.exceptions.HTTPError(f"HTTP {response.status}")
        return response

    def _prewarm_connections(self):
        start_time = time.perf_counter()
        for url in ("https://store.steampowered.com/", "https://api.steampowered.com/"):
            try:
                self.http_pool.request("HEAD", url, timeout=2, retries=False)
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
        return data

    def get_setting_bool(self, name, default):
        value = self.settings.get(name, default)
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return bool(value)

    def get_blacklisted_app_ids(self):
        raw_value = self.settings.get("blacklisted_app_ids", ",".join(sorted(self.DEFAULT_BLACKLISTED_APP_IDS)))
        if isinstance(raw_value, list):
            parts = raw_value
        else:
            parts = str(raw_value).replace("\n", ",").split(",")

        blacklist = set(self.DEFAULT_BLACKLISTED_APP_IDS)
        for part in parts:
            app_id = str(part).strip()
            if app_id:
                blacklist.add(app_id)
        if self.should_hide_hidden_games():
            blacklist.update(self.load_hidden_app_ids())
        return blacklist

    def should_show_platforms(self):
        return self.get_setting_bool("show_platforms", True)

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
        return self.get_setting_bool("detect_owned_games", True)

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
        if not self.should_log_performance() or duration_ms < self.PERF_STAGE_LOG_THRESHOLD_MS:
            return
        suffix = f" {details}" if details else ""
        self.log("info", f"Perf {label}={duration_ms:.1f}ms{suffix}")

    def log_query_profile(self, search_term, timings, total_ms, result_count):
        if not self.should_log_performance():
            return
        if total_ms < self.PERF_QUERY_LOG_THRESHOLD_MS and all(
            duration_ms < self.PERF_STAGE_LOG_THRESHOLD_MS for _stage_name, duration_ms in timings
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

    def get_country_code(self):
        with self.state_lock:
            return self.country_code

    def _build_data_blob(self, data):
        if not data:
            return self.DATA_BLOB(0, None), None
        buffer = ctypes.create_string_buffer(data, len(data))
        return self.DATA_BLOB(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte))), buffer

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [
            ("cbData", wintypes.DWORD),
            ("pbData", ctypes.POINTER(ctypes.c_byte)),
        ]

    def _protect_dpapi_bytes(self, raw_bytes):
        if not raw_bytes:
            return b""

        blob_in, buffer_in = self._build_data_blob(raw_bytes)
        blob_entropy, buffer_entropy = self._build_data_blob(self.DPAPI_ENTROPY)
        blob_out = self.DATA_BLOB()

        result = ctypes.windll.crypt32.CryptProtectData(
            ctypes.byref(blob_in),
            None,
            ctypes.byref(blob_entropy),
            None,
            None,
            0,
            ctypes.byref(blob_out),
        )
        if not result:
            raise ctypes.WinError()

        try:
            return ctypes.string_at(blob_out.pbData, blob_out.cbData)
        finally:
            ctypes.windll.kernel32.LocalFree(blob_out.pbData)

    def _unprotect_dpapi_bytes(self, protected_bytes):
        if not protected_bytes:
            return b""

        blob_in, buffer_in = self._build_data_blob(protected_bytes)
        blob_entropy, buffer_entropy = self._build_data_blob(self.DPAPI_ENTROPY)
        blob_out = self.DATA_BLOB()

        result = ctypes.windll.crypt32.CryptUnprotectData(
            ctypes.byref(blob_in),
            None,
            ctypes.byref(blob_entropy),
            None,
            None,
            0,
            ctypes.byref(blob_out),
        )
        if not result:
            raise ctypes.WinError()

        try:
            return ctypes.string_at(blob_out.pbData, blob_out.cbData)
        finally:
            ctypes.windll.kernel32.LocalFree(blob_out.pbData)

    def get_owned_api_key(self):
        with self.state_lock:
            if self.owned_api_key_value:
                return self.owned_api_key_value

        if not self.owned_api_key_file.exists():
            return None

        try:
            protected_bytes = self.owned_api_key_file.read_bytes()
            raw_bytes = self._unprotect_dpapi_bytes(protected_bytes)
            api_key = self.normalize_steam_web_api_key(raw_bytes.decode("utf-8", errors="ignore"))
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

        protected_bytes = self._protect_dpapi_bytes(normalized_key.encode("utf-8"))
        self.owned_api_key_file.write_bytes(protected_bytes)

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
        self.save_owned_games_cache()

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
        clear_wishlist_cache = getattr(self, "clear_wishlist_cache", None)
        if callable(clear_wishlist_cache):
            clear_wishlist_cache()

    def is_owned_api_key_bound_to_active_user(self):
        active_steamid64 = self.get_active_steam_user_steamid64()
        with self.state_lock:
            bound_steamid64 = self.owned_api_key_bound_steamid64
        return bool(active_steamid64 and bound_steamid64 and active_steamid64 == bound_steamid64)

    def get_owned_games_status(self):
        active_steamid64 = self.get_active_steam_user_steamid64()
        active_user_details = self.get_steam_user_details(active_steamid64)
        with self.state_lock:
            bound_steamid64 = self.owned_api_key_bound_steamid64
            persona_name = self.owned_api_key_persona_name
            account_name = self.owned_api_key_account_name
            last_sync = self.owned_games_last_sync

        if not self.has_owned_api_key():
            return "Steam API Not Configured", "Save a Steam Web API key from the clipboard to enable Steam account features"

        account_label = persona_name or account_name or "Steam account"
        active_account_label = (
            active_user_details.get("persona_name")
            or active_user_details.get("account_name")
            or "Steam account"
        )
        if active_steamid64 and bound_steamid64 and active_steamid64 != bound_steamid64:
            return (
                "Steam API Bound to Another Account",
                f"Saved for {account_label}. Active account is {active_account_label}",
            )

        if last_sync:
            age_minutes = max(0, int((time.time() - last_sync) / 60))
            return (
                "Steam API Connected",
                f"Bound to {account_label}, last sync {util_steam_date.format_relative_minutes_ago(age_minutes)}",
            )

        return (
            "Steam API Connected",
            f"Bound to {account_label}, waiting for first sync",
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
        if key is None:
            return
        with self.state_lock:
            cache[str(key)] = {
                "timestamp": time.time(),
                **payload,
            }
            self.metric_cache_dirty = True
        self.save_metric_caches()

    def get_cache_entry_state(self, cache, key, ttl_seconds):
        with self.state_lock:
            cached_entry = cache.get(str(key))
        if not cached_entry:
            return None, False
        is_fresh = (time.time() - cached_entry.get("timestamp", 0)) < ttl_seconds
        return cached_entry, is_fresh

    def start_metric_refresh(self, pending_set_name, key, refresh_method):
        key = str(key)
        with self.state_lock:
            pending_refreshes = getattr(self, pending_set_name)
            if key in pending_refreshes:
                return
            pending_refreshes.add(key)
        threading.Thread(target=refresh_method, args=(key,), daemon=True).start()

    def finish_metric_refresh(self, pending_set_name, key):
        with self.state_lock:
            getattr(self, pending_set_name).discard(str(key))

    def _fetch_country_code(self, timeout=2):
        try:
            api_url = "http://ip-api.com/json/?fields=countryCode"
            response = self._http_get(api_url, timeout=timeout)
            data = json.loads(response.data.decode("utf-8"))
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
        now = time.time()
        expired_keys = [
            key
            for key, value in cache.items()
            if now - value.get("timestamp", 0) >= ttl_seconds
        ]
        for key in expired_keys:
            cache.pop(key, None)
        return bool(expired_keys)

    def cleanup_app_details_cache_entries(self):
        now = time.time()
        expired_keys = []
        for key, value in self.app_details_cache.items():
            ttl_seconds = (
                self.APP_DETAILS_CACHE_TTL_SECONDS
                if value.get("success")
                else self.APP_DETAILS_FAILURE_CACHE_TTL_SECONDS
            )
            if now - value.get("timestamp", 0) >= ttl_seconds:
                expired_keys.append(key)

        for key in expired_keys:
            self.app_details_cache.pop(key, None)
        return bool(expired_keys)

    def cleanup_caches_if_needed(self):
        with self.state_lock:
            if time.time() - self.last_cache_cleanup < self.CACHE_CLEANUP_INTERVAL_SECONDS:
                return
            self.cleanup_cache_entries(self.search_cache, self.SEARCH_CACHE_TTL_SECONDS)
            player_cache_changed = self.cleanup_cache_entries(self.player_count_cache, self.PLAYER_COUNT_CACHE_TTL_SECONDS)
            review_cache_changed = self.cleanup_cache_entries(self.review_score_cache, self.REVIEW_SCORE_CACHE_TTL_SECONDS)
            achievement_schema_cache_changed = self.cleanup_cache_entries(
                self.achievement_schema_cache,
                self.ACHIEVEMENT_SCHEMA_CACHE_TTL_SECONDS,
            )
            achievement_progress_cache_changed = self.cleanup_cache_entries(
                self.achievement_progress_cache,
                self.ACHIEVEMENT_PROGRESS_CACHE_TTL_SECONDS,
            )
            app_details_cache_changed = self.cleanup_app_details_cache_entries()
            if (
                player_cache_changed
                or review_cache_changed
                or achievement_schema_cache_changed
                or achievement_progress_cache_changed
                or app_details_cache_changed
            ):
                self.metric_cache_dirty = True
            self.last_cache_cleanup = time.time()
        self.save_metric_caches()
