import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from .constants import STEAMFLOW_CONFIG
from .http_client import download_http_get_to_file
from .providers import get_plugin_providers
from .store_metrics_service import (
    RELEASE_DATE_PLACEHOLDER_VALUES,
    build_store_game_result_spec,
    fetch_achievement_schema_total_with_http_get,
    fetch_current_players_with_http_get,
    fetch_player_achievement_progress_with_http_get,
    fetch_review_score_with_http_get,
    format_discount_percent,
    format_owned_playtime,
    format_player_count,
    format_release_date_text,
    format_review_score,
    format_store_achievement_progress,
    format_store_price_or_availability,
    normalize_store_game_data,
    resolve_store_metric_bundle,
    should_show_release_date_text,
    supports_live_metrics,
)


class SteamPluginStoreMetricsMixin:
    CONFIG = STEAMFLOW_CONFIG
    RELEASE_DATE_PLACEHOLDER_VALUES = RELEASE_DATE_PLACEHOLDER_VALUES
    REQUIRED_PLUGIN_PROVIDERS = (
        "account",
        "profile",
        "results",
        "runtime",
        "settings",
        "store",
    )

    @property
    def store_metric_providers(self):
        return get_plugin_providers(self)

    def format_release_date_text(self, release_date_text):
        return format_release_date_text(release_date_text)

    def format_owned_playtime(self, playtime_minutes):
        return format_owned_playtime(playtime_minutes)

    def format_store_achievement_progress(self, achievement_progress):
        return format_store_achievement_progress(achievement_progress)

    def format_discount_percent(self, price_info):
        return format_discount_percent(price_info)

    def format_store_price_or_availability(self, game_data, is_owned=False):
        return format_store_price_or_availability(
            game_data,
            self.store_metric_providers.settings.country_code(),
            show_prices=self.store_metric_providers.settings.should_show_prices(),
            is_owned=is_owned,
        )

    def should_show_release_date_text(self, game_data):
        return should_show_release_date_text(
            game_data,
            placeholder_values=self.RELEASE_DATE_PLACEHOLDER_VALUES,
        )

    def _supports_live_metrics(self, game_data):
        return supports_live_metrics(game_data, self.CONFIG.review_score_excluded_name_patterns)

    def _get_cached_metric(self, cache, app_id, ttl_seconds, pending_set_name, refresh_method, value_key, allow_network_on_miss):
        if not app_id:
            return None

        app_id = str(app_id)
        cached_entry, is_fresh = self.get_cache_entry_state(cache, app_id, ttl_seconds)
        if cached_entry and is_fresh:
            return cached_entry[value_key]
        if cached_entry:
            self.store_metric_providers.runtime.start_metric_refresh(pending_set_name, app_id, refresh_method)
            return cached_entry[value_key]
        if not allow_network_on_miss:
            return None
        return None

    def download_icon(self, image_url, save_path):
        start_time = time.perf_counter()
        try:
            download_http_get_to_file(self._http_get, image_url, save_path, timeout=2, headers=None)
            self.log_slow_call("download_icon", (time.perf_counter() - start_time) * 1000, Path(save_path).name)
            return True
        except Exception:
            self.log_exception(f"Failed to download icon: {image_url}")
            self.log_slow_call("download_icon", (time.perf_counter() - start_time) * 1000, image_url)
            return False

    def _fetch_timed_metric(self, metric_name, app_id, fetcher, error_message):
        start_time = time.perf_counter()
        app_id = str(app_id)
        try:
            return fetcher(app_id)
        except Exception:
            self.log_exception(error_message.format(app_id=app_id))
            return None
        finally:
            self.log_slow_call(metric_name, (time.perf_counter() - start_time) * 1000, f"app_id={app_id}")

    def fetch_current_players(self, app_id):
        return self._fetch_timed_metric(
            "get_current_players",
            app_id,
            lambda normalized_app_id: fetch_current_players_with_http_get(self._http_get, normalized_app_id, timeout=1),
            "Failed to fetch player count for app {app_id}",
        )

    def _refresh_player_count_worker(self, app_id):
        try:
            self.update_player_count_cache(app_id, self.fetch_current_players(app_id))
        finally:
            self.store_metric_providers.runtime.finish_metric_refresh("pending_player_count_refresh", app_id)

    def get_current_players(self, app_id, allow_network_on_miss=True):
        cached_value = self._get_cached_metric(
            self.player_count_cache,
            app_id,
            self.CONFIG.cache.player_count_ttl_seconds,
            "pending_player_count_refresh",
            self._refresh_player_count_worker,
            "player_count",
            allow_network_on_miss,
        )
        if cached_value is not None or not allow_network_on_miss or not app_id:
            return cached_value

        player_count = self.fetch_current_players(app_id)
        self.update_player_count_cache(app_id, player_count)
        return player_count

    def format_player_count(self, player_count):
        return format_player_count(player_count)

    def _review_score_cache_key(self, app_id, steam_language=None):
        return f"{app_id}:{steam_language or self.store_metric_providers.settings.steam_language()}"

    def _review_score_app_id_from_cache_key(self, cache_key):
        return str(cache_key).split(":", 1)[0]

    def fetch_review_score(self, app_id, steam_language=None):
        steam_language = steam_language or self.store_metric_providers.settings.steam_language()
        return self._fetch_timed_metric(
            "get_review_score",
            app_id,
            lambda normalized_app_id: fetch_review_score_with_http_get(
                self._http_get,
                normalized_app_id,
                timeout=1,
                steam_language=steam_language,
            ),
            "Failed to fetch review score for app {app_id}",
        )

    def _refresh_review_score_worker(self, cache_key):
        try:
            app_id = self._review_score_app_id_from_cache_key(cache_key)
            steam_language = str(cache_key).split(":", 1)[1] if ":" in str(cache_key) else None
            self.update_review_score_cache(cache_key, self.fetch_review_score(app_id, steam_language=steam_language))
        finally:
            self.store_metric_providers.runtime.finish_metric_refresh("pending_review_score_refresh", cache_key)

    def get_review_score(self, app_id, allow_network_on_miss=True):
        if not app_id:
            return None

        steam_language = self.store_metric_providers.settings.steam_language()
        cache_key = self._review_score_cache_key(app_id, steam_language=steam_language)
        cached_value = self._get_cached_metric(
            self.review_score_cache,
            cache_key,
            self.CONFIG.cache.review_score_ttl_seconds,
            "pending_review_score_refresh",
            self._refresh_review_score_worker,
            "summary",
            allow_network_on_miss,
        )
        if cached_value is not None or not allow_network_on_miss or not app_id:
            return cached_value

        summary = self.fetch_review_score(app_id, steam_language=steam_language)
        self.update_review_score_cache(cache_key, summary)
        return summary

    def fetch_achievement_schema_total(self, app_id):
        api_key = self.store_metric_providers.account.owned_api_key()
        if not api_key:
            return None

        return self._fetch_timed_metric(
            "get_achievement_schema_total",
            app_id,
            lambda normalized_app_id: fetch_achievement_schema_total_with_http_get(
                self._http_get,
                api_key,
                normalized_app_id,
                timeout=1.2,
            ),
            "Failed to fetch achievement schema for app {app_id}",
        )

    def fetch_player_achievement_progress(self, app_id, steamid64):
        api_key = self.store_metric_providers.account.owned_api_key()
        if not api_key or not steamid64:
            return None

        return self._fetch_timed_metric(
            "get_player_achievement_progress",
            app_id,
            lambda normalized_app_id: fetch_player_achievement_progress_with_http_get(
                self._http_get,
                api_key,
                steamid64,
                normalized_app_id,
                timeout=1.2,
            ),
            "Failed to fetch player achievements for app {app_id}",
        )

    def update_achievement_schema_cache(self, app_id, total_count):
        if total_count is None:
            return
        self._update_metric_cache_entry(
            self.achievement_schema_cache,
            app_id,
            total_count=total_count,
        )

    def update_achievement_progress_cache(self, app_id, steamid64, unlocked_count):
        if unlocked_count is None or not steamid64:
            return
        self._update_metric_cache_entry(
            self.achievement_progress_cache,
            f"{steamid64}:{app_id}",
            unlocked_count=unlocked_count,
        )

    def get_owned_store_achievement_progress(self, app_id, allow_network_on_miss=True):
        if (
            not self.store_metric_providers.settings.should_show_achievements()
            or not app_id
            or not self.store_metric_providers.account.has_owned_api_key()
            or not self.store_metric_providers.account.api_key_bound_to_active_user()
        ):
            return None

        steamid64 = self.store_metric_providers.account.active_steamid64()
        if not steamid64:
            return None

        app_id = str(app_id)
        progress_key = f"{steamid64}:{app_id}"
        schema_entry, schema_is_fresh = self.get_cache_entry_state(
            self.achievement_schema_cache,
            app_id,
            self.CONFIG.cache.achievement_schema_ttl_seconds,
        )
        progress_entry, progress_is_fresh = self.get_cache_entry_state(
            self.achievement_progress_cache,
            progress_key,
            self.CONFIG.cache.achievement_progress_ttl_seconds,
        )

        total_count = schema_entry.get("total_count") if schema_entry else None
        unlocked_count = progress_entry.get("unlocked_count") if progress_entry else None

        if total_count is not None and unlocked_count is not None and schema_is_fresh and progress_is_fresh:
            return (unlocked_count, total_count)

        if not allow_network_on_miss:
            if total_count is not None and unlocked_count is not None:
                return (unlocked_count, total_count)
            return None

        if total_count is None or not schema_is_fresh:
            fetched_total_count = self.fetch_achievement_schema_total(app_id)
            if fetched_total_count is not None:
                total_count = fetched_total_count
                self.update_achievement_schema_cache(app_id, total_count)

        if unlocked_count is None or not progress_is_fresh:
            fetched_unlocked_count = self.fetch_player_achievement_progress(app_id, steamid64)
            if fetched_unlocked_count is not None:
                unlocked_count = fetched_unlocked_count
                self.update_achievement_progress_cache(app_id, steamid64, unlocked_count)

        if total_count is None or unlocked_count is None:
            return None
        return (unlocked_count, total_count)

    def format_review_score(self, review_summary):
        return format_review_score(review_summary)

    def should_fetch_review_score(self, game_data):
        return self._supports_live_metrics(game_data)

    def should_fetch_player_count(self, game_data):
        return self._supports_live_metrics(game_data)

    def _resolve_game_icon(self, app_id, image_url):
        if not image_url or not app_id:
            return self.DEFAULT_ICON
        cached_icon_path = self.cache_dir / f"{app_id}.png"
        if cached_icon_path.exists():
            return str(cached_icon_path)
        if self.download_icon(image_url, str(cached_icon_path)):
            return str(cached_icon_path)
        return self.DEFAULT_ICON

    def schedule_wishlist_refresh_for_store_results(self):
        schedule_refresh = getattr(self, "schedule_wishlist_refresh", None)
        if callable(schedule_refresh):
            schedule_refresh(force=False)

    def process_game_data(
        self,
        game_data,
        allow_cold_metric_fetch=True,
        allow_cold_appdetails_fetch=None,
        appdetails_timeout=1.5,
        require_appdetails=False,
        hide_hardware=False,
    ):
        app_id = game_data.get("id")
        providers = self.store_metric_providers
        is_owned = providers.profile.is_owned_app(app_id)
        if allow_cold_appdetails_fetch is None:
            allow_cold_appdetails_fetch = allow_cold_metric_fetch
        metadata = (
            providers.store.app_details_metadata(
                app_id,
                allow_network_on_miss=allow_cold_appdetails_fetch,
                fetch_timeout=appdetails_timeout,
            )
            if app_id
            else None
        )
        if require_appdetails and not metadata:
            return None
        game_data = normalize_store_game_data(game_data, metadata)
        if hide_hardware and str(game_data.get("store_type", "") or "").strip().lower() == "hardware":
            return None

        image_url = game_data.get("tiny_image")
        should_fetch_review = providers.settings.should_show_positive_reviews() and self.should_fetch_review_score(game_data)
        should_fetch_players = providers.settings.should_show_player_count() and self.should_fetch_player_count(game_data)
        should_fetch_achievements = is_owned and providers.settings.should_show_achievements() and providers.account.has_owned_api_key()
        metrics = resolve_store_metric_bundle(
            app_id,
            image_url,
            allow_cold_metric_fetch,
            self._resolve_game_icon,
            review_resolver=self.get_review_score if should_fetch_review else None,
            player_count_resolver=self.get_current_players if should_fetch_players else None,
            achievement_resolver=self.get_owned_store_achievement_progress if should_fetch_achievements else None,
        )
        result_spec = build_store_game_result_spec(
            game_data,
            is_owned,
            metrics["icon_path"],
            review_summary=metrics["review_summary"],
            player_count=metrics["player_count"],
            achievement_progress=metrics["achievement_progress"],
            owned_playtime_minutes=providers.profile.owned_game_playtime_minutes(app_id) if is_owned else None,
            platform_suffix=providers.settings.platform_suffix(game_data.get("platforms", {})),
            country_code=providers.settings.country_code(),
            show_prices=providers.settings.should_show_prices(),
            include_review_score=should_fetch_review,
            include_player_count=should_fetch_players,
            include_achievements=should_fetch_achievements,
            labels={
                "free": providers.settings.tr("store.availability.free"),
                "coming_soon": providers.settings.tr("store.availability.coming_soon"),
                "owned": providers.settings.tr("store.owned_suffix"),
                "library_subtitle": providers.settings.tr("store.subtitle.library"),
                "store_subtitle": providers.settings.tr("store.subtitle.store"),
            },
        )
        result_spec["context_data"]["steamid64"] = providers.account.active_steamid64()
        result_spec["context_data"]["wishlist_actions_enabled"] = (
            providers.account.has_owned_api_key()
            and providers.account.api_key_bound_to_active_user()
        )
        is_wishlisted_app = getattr(self, "is_wishlisted_app", None)
        if callable(is_wishlisted_app):
            result_spec["context_data"]["is_wishlisted"] = is_wishlisted_app(app_id)

        return providers.results.build_result(
            title=result_spec["title"],
            subtitle=result_spec["subtitle"],
            icon_path=result_spec["icon_path"],
            context_data=providers.results.build_context_data(
                **result_spec["context_data"],
            ),
            action=providers.results.build_action(result_spec["action_method"], app_id),
            AppID=str(app_id) if app_id is not None else None,
        )

    def process_store_results(
        self,
        api_results,
        skipped_app_ids=None,
        allow_cold_metric_fetch=True,
        allow_cold_appdetails_fetch=None,
        cold_metric_fetch_limit=None,
        appdetails_timeout=1.5,
        require_appdetails=False,
        hide_hardware=False,
    ):
        if not api_results:
            return []

        skipped_app_ids = skipped_app_ids or set()
        filtered_results = [
            game_data
            for game_data in api_results
            if str(game_data.get("id")) not in skipped_app_ids
        ]
        if not filtered_results:
            return []

        self.schedule_wishlist_refresh_for_store_results()

        if cold_metric_fetch_limit is None:
            cold_metric_fetch_limit = self.CONFIG.query.store_cold_metric_fetch_limit

        max_workers = min(
            len(filtered_results),
            max(self.CONFIG.query.max_results, self.CONFIG.query.max_store_collection_results),
        )
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_index = {
                executor.submit(
                    self.process_game_data,
                    game_data,
                    bool(allow_cold_metric_fetch)
                    and index < int(cold_metric_fetch_limit or 0),
                    allow_cold_appdetails_fetch=(
                        allow_cold_appdetails_fetch
                        if allow_cold_appdetails_fetch is not None
                        else None
                    ),
                    appdetails_timeout=appdetails_timeout,
                    require_appdetails=require_appdetails,
                    hide_hardware=hide_hardware,
                ): index
                for index, game_data in enumerate(filtered_results)
            }
            processed_results = [None] * len(filtered_results)

            for future in as_completed(future_to_index):
                try:
                    processed_results[future_to_index[future]] = future.result()
                except Exception:
                    self.log_exception("Failed to process Steam store result")

        return [result for result in processed_results if result]
