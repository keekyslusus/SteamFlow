import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from . import util_currency


class SteamPluginStoreMetricsMixin:
    RELEASE_DATE_PLACEHOLDER_VALUES = {
        "coming soon",
        "to be announced",
        "tba",
        "tbd",
    }

    def format_release_date_text(self, release_date_text):
        release_date_text = str(release_date_text or "").strip()
        if not release_date_text:
            return ""
        return f" | {release_date_text}"

    def format_owned_playtime(self, playtime_minutes):
        if playtime_minutes is None:
            return ""
        if playtime_minutes < 60:
            return f" | {playtime_minutes}m"
        return f" | {playtime_minutes / 60:.1f}h"

    def format_store_achievement_progress(self, achievement_progress):
        if not achievement_progress:
            return ""
        unlocked_count, total_count = achievement_progress
        if total_count <= 0:
            return ""
        return f" | {unlocked_count}/{total_count}"

    def format_discount_percent(self, price_info):
        if not isinstance(price_info, dict):
            return ""

        try:
            initial_price = int(price_info.get("initial", 0))
            final_price = int(price_info.get("final", 0))
        except (TypeError, ValueError):
            return ""

        if initial_price <= 0 or final_price < 0 or final_price >= initial_price:
            return ""

        discount_percent = round(((initial_price - final_price) / initial_price) * 100)
        if discount_percent <= 0:
            return ""
        return f" -{discount_percent}%"

    def format_store_price_or_availability(self, game_data, is_owned=False):
        if not self.should_show_prices() or is_owned:
            return ""

        if game_data.get("is_free") is True:
            return " | Free"

        price_info = game_data.get("price")
        if price_info and "final" in price_info:
            return (
                f" | {util_currency.format_price(price_info['final'], self.get_country_code())}"
                f"{self.format_discount_percent(price_info)}"
            )

        if game_data.get("coming_soon"):
            return " | Coming Soon"

        return ""

    def should_show_release_date_text(self, game_data):
        release_date_text = str(game_data.get("release_date_text", "") or "").strip()
        if not release_date_text:
            return False

        if release_date_text.casefold() in self.RELEASE_DATE_PLACEHOLDER_VALUES:
            return False

        return True

    def _supports_live_metrics(self, game_data):
        store_type = str(game_data.get("store_type", "") or "").strip().lower()
        if store_type and store_type != "game":
            return False

        if game_data.get("type") != "app":
            return False

        name = str(game_data.get("name", "")).strip().lower()
        if not name:
            return False

        return not any(pattern in name for pattern in self.REVIEW_SCORE_EXCLUDED_NAME_PATTERNS)

    def _get_cached_metric(self, cache, app_id, ttl_seconds, pending_set_name, refresh_method, value_key, allow_network_on_miss):
        if not app_id:
            return None

        app_id = str(app_id)
        cached_entry, is_fresh = self.get_cache_entry_state(cache, app_id, ttl_seconds)
        if cached_entry and is_fresh:
            return cached_entry[value_key]
        if cached_entry:
            self.start_metric_refresh(pending_set_name, app_id, refresh_method)
            return cached_entry[value_key]
        if not allow_network_on_miss:
            return None
        return None

    def download_icon(self, image_url, save_path):
        start_time = time.perf_counter()
        try:
            response = self._http_get(image_url, timeout=2)
            with open(save_path, "wb") as out_file:
                out_file.write(response.data)
            self.log_slow_call("download_icon", (time.perf_counter() - start_time) * 1000, Path(save_path).name)
            return True
        except Exception:
            self.log_exception(f"Failed to download icon: {image_url}")
            self.log_slow_call("download_icon", (time.perf_counter() - start_time) * 1000, image_url)
            return False

    def fetch_current_players(self, app_id):
        start_time = time.perf_counter()
        app_id = str(app_id)
        try:
            api_url = f"https://api.steampowered.com/ISteamUserStats/GetNumberOfCurrentPlayers/v1/?appid={app_id}"
            response = self._http_get(api_url, timeout=1)
            data = json.loads(response.data.decode("utf-8"))
            if data.get("response", {}).get("result") == 1:
                player_count = data["response"].get("player_count")
                self.log_slow_call("get_current_players", (time.perf_counter() - start_time) * 1000, f"app_id={app_id}")
                return player_count
        except Exception:
            self.log_exception(f"Failed to fetch player count for app {app_id}")
        self.log_slow_call("get_current_players", (time.perf_counter() - start_time) * 1000, f"app_id={app_id}")
        return None

    def _refresh_player_count_worker(self, app_id):
        try:
            self.update_player_count_cache(app_id, self.fetch_current_players(app_id))
        finally:
            self.finish_metric_refresh("pending_player_count_refresh", app_id)

    def get_current_players(self, app_id, allow_network_on_miss=True):
        cached_value = self._get_cached_metric(
            self.player_count_cache,
            app_id,
            self.PLAYER_COUNT_CACHE_TTL_SECONDS,
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
        if player_count is None:
            return ""
        try:
            if int(player_count) <= 0:
                return ""
        except (TypeError, ValueError):
            return ""
        return f" | \U0001F465 {player_count:,}"

    def fetch_review_score(self, app_id):
        start_time = time.perf_counter()
        app_id = str(app_id)
        try:
            api_url = (
                f"https://store.steampowered.com/appreviews/{app_id}"
                "?json=1&language=all&purchase_type=all&num_per_page=0"
            )
            response = self._http_get(api_url, timeout=1, headers={"User-Agent": "Mozilla/5.0"})
            data = json.loads(response.data.decode("utf-8"))

            summary = data.get("query_summary", data)
            self.log_slow_call("get_review_score", (time.perf_counter() - start_time) * 1000, f"app_id={app_id}")
            return summary
        except Exception:
            self.log_exception(f"Failed to fetch review score for app {app_id}")
        self.log_slow_call("get_review_score", (time.perf_counter() - start_time) * 1000, f"app_id={app_id}")
        return None

    def _refresh_review_score_worker(self, app_id):
        try:
            self.update_review_score_cache(app_id, self.fetch_review_score(app_id))
        finally:
            self.finish_metric_refresh("pending_review_score_refresh", app_id)

    def get_review_score(self, app_id, allow_network_on_miss=True):
        cached_value = self._get_cached_metric(
            self.review_score_cache,
            app_id,
            self.REVIEW_SCORE_CACHE_TTL_SECONDS,
            "pending_review_score_refresh",
            self._refresh_review_score_worker,
            "summary",
            allow_network_on_miss,
        )
        if cached_value is not None or not allow_network_on_miss or not app_id:
            return cached_value

        summary = self.fetch_review_score(app_id)
        self.update_review_score_cache(app_id, summary)
        return summary

    def fetch_achievement_schema_total(self, app_id):
        start_time = time.perf_counter()
        app_id = str(app_id)
        api_key = self.get_owned_api_key()
        if not api_key:
            return None

        try:
            api_url = (
                "https://api.steampowered.com/ISteamUserStats/GetSchemaForGame/v2/"
                f"?key={api_key}&appid={app_id}&l=en"
            )
            response = self._http_get(api_url, timeout=1.2, headers={"User-Agent": "Mozilla/5.0"})
            data = json.loads(response.data.decode("utf-8"))
            achievements = (
                data.get("game", {})
                .get("availableGameStats", {})
                .get("achievements", [])
            )
            if isinstance(achievements, list):
                self.log_slow_call("get_achievement_schema_total", (time.perf_counter() - start_time) * 1000, f"app_id={app_id}")
                return len(achievements)
        except Exception:
            self.log_exception(f"Failed to fetch achievement schema for app {app_id}")

        self.log_slow_call("get_achievement_schema_total", (time.perf_counter() - start_time) * 1000, f"app_id={app_id}")
        return None

    def fetch_player_achievement_progress(self, app_id, steamid64):
        start_time = time.perf_counter()
        app_id = str(app_id)
        api_key = self.get_owned_api_key()
        if not api_key or not steamid64:
            return None

        try:
            api_url = (
                "https://api.steampowered.com/ISteamUserStats/GetPlayerAchievements/v1/"
                f"?key={api_key}&steamid={steamid64}&appid={app_id}&l=en"
            )
            response = self._http_get(api_url, timeout=1.2, headers={"User-Agent": "Mozilla/5.0"})
            data = json.loads(response.data.decode("utf-8"))
            achievements = data.get("playerstats", {}).get("achievements", [])
            if isinstance(achievements, list):
                unlocked_count = sum(1 for achievement in achievements if achievement.get("achieved"))
                self.log_slow_call("get_player_achievement_progress", (time.perf_counter() - start_time) * 1000, f"app_id={app_id}")
                return unlocked_count
        except Exception:
            self.log_exception(f"Failed to fetch player achievements for app {app_id}")

        self.log_slow_call("get_player_achievement_progress", (time.perf_counter() - start_time) * 1000, f"app_id={app_id}")
        return None

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
            not self.should_show_achievements()
            or not app_id
            or not self.has_owned_api_key()
            or not self.is_owned_api_key_bound_to_active_user()
        ):
            return None

        steamid64 = self.get_active_steam_user_steamid64()
        if not steamid64:
            return None

        app_id = str(app_id)
        progress_key = f"{steamid64}:{app_id}"
        schema_entry, schema_is_fresh = self.get_cache_entry_state(
            self.achievement_schema_cache,
            app_id,
            self.ACHIEVEMENT_SCHEMA_CACHE_TTL_SECONDS,
        )
        progress_entry, progress_is_fresh = self.get_cache_entry_state(
            self.achievement_progress_cache,
            progress_key,
            self.ACHIEVEMENT_PROGRESS_CACHE_TTL_SECONDS,
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
        if not review_summary:
            return ""

        try:
            total_positive = int(review_summary.get("total_positive", 0))
            total_reviews = int(review_summary.get("total_reviews", 0))
        except (TypeError, ValueError):
            return ""

        if total_reviews <= 0:
            return ""

        percentage = round((total_positive / total_reviews) * 100)
        review_score_desc = str(review_summary.get("review_score_desc", "")).strip()
        if review_score_desc:
            return f" | {percentage}% ({review_score_desc})"
        return f" | {percentage}%"

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

    def process_game_data(self, game_data, allow_cold_metric_fetch=True):
        app_id = game_data.get("id")
        name = game_data.get("name")
        is_owned = self.is_owned_app(app_id)
        metadata = self.get_app_details_metadata(app_id, allow_network_on_miss=allow_cold_metric_fetch) if app_id else None

        if metadata:
            name = metadata.get("name") or name
            game_data = {
                **game_data,
                "store_type": metadata.get("type") or game_data.get("store_type"),
                "name": name,
                "platforms": metadata.get("platforms") or game_data.get("platforms", {}),
                "tiny_image": metadata.get("capsule_image") or game_data.get("tiny_image"),
                "has_price": metadata.get("has_price", game_data.get("has_price", False)),
                "price": metadata.get("price") if metadata.get("price") is not None else game_data.get("price"),
                "is_free": metadata.get("is_free") if metadata.get("is_free") is not None else game_data.get("is_free"),
                "coming_soon": metadata.get("coming_soon", game_data.get("coming_soon", False)),
                "release_date_text": metadata.get("release_date_text") or game_data.get("release_date_text", ""),
            }

        image_url = game_data.get("tiny_image")
        should_fetch_review = self.should_show_positive_reviews() and self.should_fetch_review_score(game_data)
        should_fetch_players = self.should_show_player_count() and self.should_fetch_player_count(game_data)
        should_fetch_achievements = is_owned and self.should_show_achievements() and self.has_owned_api_key()

        with ThreadPoolExecutor(max_workers=4) as executor:
            icon_future = executor.submit(self._resolve_game_icon, app_id, image_url)
            review_future = (
                executor.submit(self.get_review_score, app_id, allow_cold_metric_fetch)
                if should_fetch_review
                else None
            )
            players_future = (
                executor.submit(self.get_current_players, app_id, allow_cold_metric_fetch)
                if should_fetch_players
                else None
            )
            achievements_future = (
                executor.submit(self.get_owned_store_achievement_progress, app_id, allow_cold_metric_fetch)
                if should_fetch_achievements
                else None
            )

            icon_path = icon_future.result()
            review_summary = review_future.result() if review_future else None
            player_count = players_future.result() if players_future else None
            achievement_progress = achievements_future.result() if achievements_future else None

        review_score_str = self.format_review_score(review_summary) if should_fetch_review else ""
        player_count_str = self.format_player_count(player_count) if should_fetch_players else ""
        owned_playtime_str = self.format_owned_playtime(self.get_owned_game_playtime_minutes(app_id)) if is_owned else ""
        achievement_progress_str = self.format_store_achievement_progress(achievement_progress) if should_fetch_achievements else ""

        price_str = self.format_store_price_or_availability(game_data, is_owned=is_owned)
        release_date_str = (
            self.format_release_date_text(game_data.get("release_date_text"))
            if self.should_show_release_date_text(game_data)
            else ""
        )

        ownership_suffix = " [Owned]" if is_owned else ""
        subtitle_prefix = "Owned game, open in Steam library" if is_owned else "Open in Steam store"
        action_method = "open_steam_library_game_details" if is_owned else "open_steam_store_page"
        title_prefix = "\U0001F3AE" if is_owned else "\U0001F6D2"

        return self.build_result(
            title=f"{title_prefix} {name}{ownership_suffix}",
            subtitle=(
                f"{subtitle_prefix}{self.get_platform_suffix(game_data.get('platforms', {}))}"
                f"{review_score_str}{player_count_str}{owned_playtime_str}{achievement_progress_str}{price_str}{release_date_str}"
            ),
            icon_path=icon_path,
            context_data=self.build_context_data(
                app_id=app_id,
                name=name,
                is_owned=is_owned,
                coming_soon=game_data.get("coming_soon"),
            ),
            action=self.build_action(action_method, app_id),
            AppID=str(app_id) if app_id is not None else None,
        )

    def process_store_results(self, api_results, skipped_app_ids=None):
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

        with ThreadPoolExecutor(max_workers=self.MAX_QUERY_RESULTS) as executor:
            future_to_index = {
                executor.submit(
                    self.process_game_data,
                    game_data,
                    index < self.STORE_COLD_METRIC_FETCH_LIMIT,
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
