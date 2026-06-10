import time

from . import util_steam_date
from .cache_utils import is_timestamp_fresh
from .constants import STEAMFLOW_CONFIG
from .hooks import get_secure_settings_dir
from .providers import get_plugin_providers
from .localization import plugin_tr
from .tasks import get_background_task_manager
from .wishlist_mutation_service import start_steam_wishlist_mutation_worker_process
from .wishlist_service import (
    add_wishlist_cache_item,
    fetch_wishlist_items,
    fetch_wishlist_result,
    get_wishlist_fetch_error_message,
    is_wishlist_cache_fresh,
    is_wishlist_worker_running,
    build_wishlist_results_plan,
    normalize_wishlist_items,
    remove_wishlist_cache_item,
    select_wishlist_prewarm_items,
    sort_wishlist_items,
    start_wishlist_hydration_worker_process,
    wishlist_contains_app_id,
)


def _summarize_wishlist_app_ids(wishlist_items, max_items=20):
    app_ids = [str((item or {}).get("appid", "")).strip() for item in wishlist_items or []]
    app_ids = [app_id for app_id in app_ids if app_id]
    if len(app_ids) <= max_items:
        return ", ".join(app_ids)
    shown_app_ids = ", ".join(app_ids[:max_items])
    return f"{shown_app_ids}, ... (+{len(app_ids) - max_items} more)"


class SteamPluginWishlistMixin:
    CONFIG = STEAMFLOW_CONFIG
    REQUIRED_PLUGIN_PROVIDERS = (
        "account",
        "owned_api",
        "results",
        "settings",
        "store",
        "wishlist",
    )
    REQUIRED_PLUGIN_ATTRS = (
        "OWNED_ICON",
        "plugin_dir",
        "state_lock",
        "wishlist_worker_lock_file",
    )
    REQUIRED_PLUGIN_METHODS = (
        "_http_get",
        "log_exception",
    )

    @property
    def wishlist_providers(self):
        return get_plugin_providers(self)

    def ensure_wishlist_cache_loaded(self):
        with self.state_lock:
            if self.wishlist_cache_loaded:
                return
        self.wishlist_providers.wishlist.load_cache()

    def normalize_wishlist_items(self, items):
        return normalize_wishlist_items(items)

    def is_wishlisted_app(self, app_id):
        app_id = str(app_id or "").strip()
        if not app_id:
            return False

        account_provider = self.wishlist_providers.account
        if not account_provider.has_owned_api_key() or not account_provider.api_key_bound_to_active_user():
            return False

        self.ensure_wishlist_cache_loaded()
        steamid64 = account_provider.active_steamid64()
        with self.state_lock:
            if str(self.wishlist_steamid64 or "") != str(steamid64 or ""):
                return False
            return wishlist_contains_app_id(self.wishlist_items, app_id)

    def clear_wishlist_cache(self):
        with self.state_lock:
            self.wishlist_last_attempt = 0
            self.wishlist_last_sync = 0
            self.wishlist_steamid64 = None
            self.wishlist_items = []
            self.wishlist_cache_loaded = True
        self.wishlist_providers.wishlist.save_cache()

    def update_wishlist_cache_for_mutation(self, app_id, action):
        account_provider = self.wishlist_providers.account
        steamid64 = account_provider.active_steamid64()
        if not steamid64:
            return

        self.ensure_wishlist_cache_loaded()
        with self.state_lock:
            if self.wishlist_steamid64 and str(self.wishlist_steamid64) != str(steamid64):
                self.wishlist_items = []
            if str(action or "").strip().lower() == "add":
                self.wishlist_items = add_wishlist_cache_item(self.wishlist_items, app_id)
            elif str(action or "").strip().lower() == "remove":
                self.wishlist_items = remove_wishlist_cache_item(self.wishlist_items, app_id)
            else:
                return
            self.wishlist_steamid64 = steamid64
            self.wishlist_last_sync = time.time()
            self.wishlist_last_attempt = self.wishlist_last_sync
            self.wishlist_cache_loaded = True
        self.wishlist_providers.wishlist.save_cache()

    def start_steam_wishlist_mutation_worker(self, steamid64, app_id, action):
        start_steam_wishlist_mutation_worker_process(
            self.plugin_dir,
            get_secure_settings_dir(self),
            steamid64,
            app_id,
            action,
        )

    def mutate_steam_wishlist(self, app_id, action, steamid64=None):
        app_id = str(app_id or "").strip()
        action = str(action or "").strip().lower()
        if not app_id:
            return plugin_tr(self, "action.missing_app_id")
        if action not in {"add", "remove"}:
            return plugin_tr(self, "wishlist.mutation_failed", error=f"Unsupported action: {action}")

        feature_enabled = getattr(self, "feature_enabled", None)
        if callable(feature_enabled) and (
            not feature_enabled("steam_session_token") or not feature_enabled("steam_wishlist")
        ):
            return plugin_tr(self, "wishlist.mutation_unavailable")

        account_provider = self.wishlist_providers.account
        steamid64 = steamid64 or account_provider.active_steamid64()
        if not steamid64:
            return plugin_tr(self, "action.no_active_account")
        if action == "add" and self.is_wishlisted_app(app_id):
            return plugin_tr(self, "wishlist.already_added")

        try:
            self.start_steam_wishlist_mutation_worker(steamid64, app_id, action)
            self.update_wishlist_cache_for_mutation(app_id, action)
            self.schedule_wishlist_refresh(force=True)
            if action == "add":
                return plugin_tr(self, "wishlist.adding", app_id=app_id)
            return plugin_tr(self, "wishlist.removing", app_id=app_id)
        except Exception as error:
            self.log_exception(f"Failed to start Steam wishlist worker for app {app_id}")
            return plugin_tr(self, "wishlist.mutation_failed", error=str(error))

    def add_to_steam_wishlist(self, app_id, steamid64=None):
        return self.mutate_steam_wishlist(app_id, "add", steamid64=steamid64)

    def remove_from_steam_wishlist(self, app_id, steamid64=None):
        return self.mutate_steam_wishlist(app_id, "remove", steamid64=steamid64)

    def wishlist_cache_is_fresh(self, steamid64):
        self.ensure_wishlist_cache_loaded()
        with self.state_lock:
            cached_steamid64 = self.wishlist_steamid64
            last_sync = self.wishlist_last_sync
        return is_wishlist_cache_fresh(
            steamid64,
            cached_steamid64,
            last_sync,
            self.CONFIG.cache.wishlist_ttl_seconds,
            is_timestamp_fresh,
        )

    def fetch_wishlist_items_from_api(self, api_key, steamid64, timeout=3):
        return fetch_wishlist_items(
            api_key,
            steamid64,
            self._http_get,
            normalize_api_key=self.wishlist_providers.owned_api.normalize_key,
            timeout=timeout,
        )

    def _refresh_wishlist_worker(self):
        try:
            self.refresh_wishlist()
        finally:
            get_background_task_manager(self).finish_flagged_refresh(self, "pending_wishlist_refresh")

    def wishlist_worker_is_running(self):
        return is_wishlist_worker_running(getattr(self, "wishlist_worker_lock_file", None))

    def start_wishlist_hydration_worker(self, wishlist_items, force=False):
        if not wishlist_items:
            return False
        if self.wishlist_worker_is_running():
            log = getattr(self, "log", None)
            if callable(log):
                log(
                    "info",
                    "Steam wishlist hydration worker already running; "
                    f"missing_app_ids={_summarize_wishlist_app_ids(wishlist_items)}",
                )
            return False
        try:
            log = getattr(self, "log", None)
            if callable(log):
                log(
                    "info",
                    "Starting Steam wishlist hydration worker for "
                    f"{len(wishlist_items)} missing appdetails entries: "
                    f"{_summarize_wishlist_app_ids(wishlist_items)}; force={force}",
                )
            process = start_wishlist_hydration_worker_process(
                self.plugin_dir,
                self.wishlist_providers.settings.country_code,
                wishlist_items,
                steam_language=self.wishlist_providers.settings.steam_language(),
                force=force,
            )
            return process is not None
        except Exception:
            self.log_exception("Failed to start Steam wishlist worker")
            return False

    def get_wishlist_missing_appdetails_items(self, wishlist_items):
        plan = build_wishlist_results_plan(
            wishlist_items,
            "",
            lambda app_id: self.wishlist_providers.store.app_details_metadata(
                app_id,
                allow_network_on_miss=False,
            ),
            len(wishlist_items or []),
        )
        return plan["missing_items"]

    def sync_steam_wishlist_details(self):
        ensure_startup_initialized = getattr(self, "ensure_startup_initialized", None)
        if callable(ensure_startup_initialized):
            ensure_startup_initialized()

        wishlist_items, error = self.get_wishlist_items()
        if error:
            return plugin_tr(self, "wishlist.sync.unavailable")

        missing_items = self.get_wishlist_missing_appdetails_items(wishlist_items)
        if not missing_items:
            return plugin_tr(self, "wishlist.sync.complete")

        started = self.start_wishlist_hydration_worker(missing_items, force=True)
        if started:
            return plugin_tr(self, "wishlist.sync.started", count=len(missing_items))
        return plugin_tr(self, "wishlist.sync.running", count=len(missing_items))

    def schedule_wishlist_refresh(self, force=False):
        account_provider = self.wishlist_providers.account
        if not account_provider.has_owned_api_key() or not account_provider.api_key_bound_to_active_user():
            return

        self.ensure_wishlist_cache_loaded()
        steamid64 = account_provider.active_steamid64()
        if not steamid64:
            return

        with self.state_lock:
            if not force and self.wishlist_cache_is_fresh(steamid64):
                return
        get_background_task_manager(self).start_flagged_refresh(
            self,
            "pending_wishlist_refresh",
            self._refresh_wishlist_worker,
        )

    def refresh_wishlist(self):
        account_provider = self.wishlist_providers.account
        if not account_provider.has_owned_api_key() or not account_provider.api_key_bound_to_active_user():
            return

        api_key = account_provider.owned_api_key()
        steamid64 = account_provider.active_steamid64()
        if not api_key or not steamid64:
            return

        with self.state_lock:
            self.wishlist_last_attempt = time.time()
        fetch_result = fetch_wishlist_result(self.fetch_wishlist_items_from_api, api_key, steamid64, timeout=3)
        if not fetch_result["success"]:
            self.log_exception("Failed to fetch Steam wishlist")
            self.wishlist_providers.wishlist.save_cache()
            return

        with self.state_lock:
            self.wishlist_items = fetch_result["items"]
            self.wishlist_steamid64 = steamid64
            self.wishlist_last_sync = time.time()
            self.wishlist_last_attempt = self.wishlist_last_sync
            self.wishlist_cache_loaded = True
        self.wishlist_providers.wishlist.save_cache()

    def get_wishlist_items(self):
        account_provider = self.wishlist_providers.account
        reasons = self.CONFIG.availability_reasons
        if not account_provider.has_owned_api_key():
            return [], reasons.api_not_configured
        if not account_provider.api_key_bound_to_active_user():
            return [], reasons.api_bound_to_another_account

        self.ensure_wishlist_cache_loaded()
        steamid64 = account_provider.active_steamid64()
        if not steamid64:
            return [], reasons.no_active_account

        with self.state_lock:
            cached_items = list(self.wishlist_items)
            cached_steamid64 = self.wishlist_steamid64

        if cached_steamid64 == steamid64 and cached_items:
            if not self.wishlist_cache_is_fresh(steamid64):
                self.schedule_wishlist_refresh()
            return cached_items, None

        api_key = account_provider.owned_api_key()
        with self.state_lock:
            self.wishlist_last_attempt = time.time()
        fetch_result = fetch_wishlist_result(self.fetch_wishlist_items_from_api, api_key, steamid64, timeout=3)
        if not fetch_result["success"]:
            self.log_exception("Failed to fetch Steam wishlist")
            if cached_steamid64 == steamid64 and cached_items:
                return cached_items, None
            return [], get_wishlist_fetch_error_message(fetch_result["error"])

        with self.state_lock:
            self.wishlist_items = fetch_result["items"]
            self.wishlist_steamid64 = steamid64
            self.wishlist_last_sync = time.time()
            self.wishlist_last_attempt = self.wishlist_last_sync
            self.wishlist_cache_loaded = True
        self.wishlist_providers.wishlist.save_cache()
        return fetch_result["items"], None

    def format_wishlist_added(self, date_added):
        formatted_age = util_steam_date.format_wishlisted_date(date_added, tr=getattr(self, "tr", None))
        if not formatted_age:
            return ""
        return f" | {plugin_tr(self, 'wishlist.added', date=formatted_age)}"

    def build_wishlist_result(self, wishlist_item, allow_cold_detail_fetch=True):
        app_id = wishlist_item["appid"]
        store_provider = self.wishlist_providers.store
        metadata = store_provider.app_details_metadata(
            app_id,
            allow_network_on_miss=allow_cold_detail_fetch,
        )
        if not metadata or not metadata.get("name"):
            return None

        game_data = {
            "type": "app",
            "store_type": metadata.get("type"),
            "id": app_id,
            "name": metadata.get("name"),
            "platforms": metadata.get("platforms", {}),
            "tiny_image": metadata.get("capsule_image"),
            "has_price": metadata.get("has_price", False),
            "price": metadata.get("price"),
            "is_free": metadata.get("is_free", False),
            "coming_soon": metadata.get("coming_soon", False),
            "release_date_text": metadata.get("release_date_text", ""),
            "result_source": "wishlist",
        }
        result = store_provider.process_game_data(
            game_data,
            allow_cold_metric_fetch=allow_cold_detail_fetch,
        )
        result["SubTitle"] = f"{result.get('SubTitle', '')}{self.format_wishlist_added(wishlist_item.get('date_added'))}"
        return result

    def build_wishlist_status_result(self, loaded_count, total_count, search_term="", matching_count=None):
        if search_term:
            title = plugin_tr(
                self,
                "wishlist.status.sync_search",
                search_term=search_term,
            )
        else:
            title = plugin_tr(self, "wishlist.status.sync")

        subtitle = plugin_tr(
            self,
            "wishlist.status.loaded",
            loaded_count=loaded_count,
            total_count=total_count,
        )
        if matching_count is not None and search_term:
            subtitle += f" | {plugin_tr(self, 'wishlist.status.matches', matching_count=matching_count)}"
        subtitle += f" | {plugin_tr(self, 'wishlist.status.more')}"
        result_provider = self.wishlist_providers.results
        action = result_provider.build_action("sync_steam_wishlist_details")
        action["dontHideAfterAction"] = True
        return result_provider.build_result(
            title=title,
            subtitle=subtitle,
            icon_path=self.OWNED_ICON,
            action=action,
            Score=20501,
        )

    def build_wishlist_empty_query_result(self, search_term):
        return self.wishlist_providers.results.build_result(
            title=plugin_tr(
                self,
                "wishlist.empty_search.title",
                search_term=search_term,
            ),
            subtitle=plugin_tr(self, "wishlist.empty_search.subtitle"),
            icon_path=self.OWNED_ICON,
            Score=20500,
        )

    def build_wishlist_results(self, search_term=""):
        wishlist_items, error = self.get_wishlist_items()
        if error:
            return [self.build_wishlist_unavailable_result(error)]
        if not wishlist_items:
            return [
                self.wishlist_providers.results.build_result(
                    title=plugin_tr(self, "wishlist.title"),
                    subtitle=plugin_tr(self, "wishlist.empty_account"),
                    icon_path=self.OWNED_ICON,
                    Score=20500,
                )
            ]

        sorted_items = sort_wishlist_items(wishlist_items)
        for wishlist_item in select_wishlist_prewarm_items(
            sorted_items,
            self.CONFIG.query.wishlist_cold_detail_fetch_limit,
        ):
            self.wishlist_providers.store.app_details_metadata(
                wishlist_item["appid"],
                allow_network_on_miss=True,
            )

        plan = build_wishlist_results_plan(
            wishlist_items,
            search_term,
            lambda app_id: self.wishlist_providers.store.app_details_metadata(
                app_id,
                allow_network_on_miss=False,
            ),
            self.CONFIG.query.max_wishlist_results,
        )
        sorted_items = plan["sorted_items"]
        missing_items = plan["missing_items"]
        visible_results = [
            result
            for result in (
                self.build_wishlist_result(wishlist_item, allow_cold_detail_fetch=False)
                for wishlist_item in plan["visible_items"]
            )
            if result
        ]

        if missing_items:
            self.start_wishlist_hydration_worker(missing_items)

        results = []
        if missing_items:
            results.append(
                self.build_wishlist_status_result(
                    plan["loaded_count"],
                    len(sorted_items),
                    search_term=search_term,
                    matching_count=plan["matching_loaded_count"] if plan["normalized_search"] else None,
                )
            )

        if visible_results:
            results.extend(visible_results)
            return results

        if plan["normalized_search"]:
            if missing_items:
                return results
            return [self.build_wishlist_empty_query_result(search_term)]

        if results:
            return results

        return [
            self.wishlist_providers.results.build_result(
                title=plugin_tr(self, "wishlist.title"),
                subtitle=plugin_tr(self, "wishlist.empty_account"),
                icon_path=self.OWNED_ICON,
                Score=20500,
            )
        ]

    def build_wishlist_unavailable_result(self, reason):
        result_provider = self.wishlist_providers.results
        api_query = result_provider.build_plugin_query("api")
        reasons = self.CONFIG.availability_reasons
        subtitle_by_reason = {
            reasons.api_not_configured: plugin_tr(
                self,
                "wishlist.unavailable_api",
                api_query=api_query,
            ),
            reasons.api_bound_to_another_account: plugin_tr(
                self,
                "wishlist.unavailable_bound",
            ),
            reasons.no_active_account: plugin_tr(
                self,
                "wishlist.unavailable_no_account",
            ),
        }
        action = None
        if reason in {reasons.api_not_configured, reasons.api_bound_to_another_account}:
            action = {
                "method": "change_query",
                "parameters": [api_query, True],
                "dontHideAfterAction": True,
            }
        return result_provider.build_result(
            title=plugin_tr(self, "wishlist.unavailable"),
            subtitle=subtitle_by_reason.get(
                reason,
                reason or plugin_tr(self, "wishlist.unavailable_default"),
            ),
            icon_path=self.OWNED_ICON,
            action=action,
            Score=20500,
        )
