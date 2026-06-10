import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from .constants import STEAMFLOW_CONFIG
from .localization import plugin_tr
from .providers import get_plugin_providers
from .util_steam_date import format_relative_minutes_ago


class SteamPluginUIQueryMixin:
    CONFIG = STEAMFLOW_CONFIG
    REQUIRED_PLUGIN_PROVIDERS = (
        "commands",
        "local",
        "metrics",
        "results",
        "runtime",
        "settings",
        "store",
    )

    @property
    def ui_query_providers(self):
        return get_plugin_providers(self)

    def collect_local_matches(self, search_term):
        search_lower = search_term.lower()
        matches = []
        for app_id, name in self.ui_query_providers.local.installed_games_items():
            if search_lower in name.lower():
                matches.append((app_id, name))
        matches.sort(key=lambda item: (item[1].lower().find(search_lower), len(item[1])))
        return matches[: self.CONFIG.query.max_results]

    def get_empty_query_local_games(self):
        local_provider = self.ui_query_providers.local
        games = local_provider.installed_games_items()
        if self.ui_query_providers.settings.should_sort_local_by_recent():
            games.sort(
                key=lambda item: (
                    -(local_provider.last_played_timestamp(item[0]) or 0),
                    item[1].lower(),
                )
            )
        else:
            games.sort(key=lambda item: item[1].lower())
        return games[: self.CONFIG.query.max_empty_query_results]

    def process_local_results(self, local_matches, include_player_count=False):
        if not local_matches:
            return []

        if not include_player_count:
            return [self.build_local_result(app_id, name) for app_id, name in local_matches]

        with ThreadPoolExecutor(max_workers=min(len(local_matches), self.CONFIG.query.max_results)) as executor:
            future_to_index = {}
            if self.ui_query_providers.settings.should_show_player_count():
                future_to_index = {
                    executor.submit(self.ui_query_providers.metrics.current_players, app_id): index
                    for index, (app_id, _name) in enumerate(local_matches)
                }
            player_counts = [None] * len(local_matches)

            for future in as_completed(future_to_index):
                index = future_to_index[future]
                try:
                    player_counts[index] = future.result()
                except Exception:
                    self.ui_query_providers.runtime.log_exception("Failed to process local player count")

        return [
            self.build_local_result(
                app_id,
                name,
                include_player_count=True,
                player_count=player_counts[index],
                player_count_loaded=True,
            )
            for index, (app_id, name) in enumerate(local_matches)
        ]

    def merge_search_results(self, local_matches, local_results, store_results):
        results = list(local_results)
        local_app_ids = {str(app_id) for app_id, _name in local_matches}

        for result in store_results:
            app_id = result.get("AppID")
            if app_id and app_id in local_app_ids:
                continue
            results.append(result)

        return results

    def build_store_collection_results(self, collection_name):
        providers = self.ui_query_providers
        collection_result = providers.store.store_collection_games(collection_name)
        store_results = providers.store.process_store_results(
            collection_result["games"],
            allow_cold_metric_fetch=True,
            allow_cold_appdetails_fetch=True,
            cold_metric_fetch_limit=3,
            appdetails_timeout=2.0,
            require_appdetails=True,
            hide_hardware=True,
        )
        results = []
        if collection_result.get("stale") and store_results:
            age_seconds = collection_result.get("age_seconds")
            age_text = ""
            if age_seconds is not None:
                age_text = format_relative_minutes_ago(int(age_seconds / 60), tr=self.tr)
            subtitle = plugin_tr(self, "store.collection_stale.subtitle")
            if age_text:
                subtitle += f" | {plugin_tr(self, 'store.collection_stale.cached_age', age=age_text)}"
            results.append(
                providers.results.build_result(
                    title=plugin_tr(
                        self,
                        "store.collection_stale.title",
                        collection=providers.store.store_collection_label(collection_name),
                    ),
                    subtitle=subtitle,
                    icon_path=self.WARNING_ICON,
                    Score=25000,
                )
            )
        results.extend(store_results)
        if not results:
            error = collection_result.get("error")
            if error:
                results.append(self.build_search_error_result(collection_name, error))
            else:
                results.append(self.build_empty_state_result(collection_name))
        return results

    def query(self, search_term):
        providers = self.ui_query_providers
        if providers.commands.is_help_query(search_term):
            providers.runtime.ensure_startup_initialized()
            for result in providers.commands.build_help_results():
                providers.results.add_result(result)
            return

        if providers.commands.is_wishlist_query(search_term):
            providers.runtime.ensure_startup_initialized()
            for result in providers.commands.build_wishlist_results(providers.commands.get_wishlist_query_text(search_term) or ""):
                providers.results.add_result(result)
            return

        if providers.commands.is_switch_account_query(search_term):
            providers.runtime.ensure_startup_initialized()
            for result in providers.commands.build_switch_account_results():
                providers.results.add_result(result)
            return

        if providers.commands.is_status_query(search_term):
            providers.runtime.ensure_startup_initialized()
            for result in providers.commands.build_status_results():
                providers.results.add_result(result)
            return

        if providers.commands.is_owned_api_query(search_term):
            providers.runtime.ensure_startup_initialized()
            for result in providers.commands.build_owned_api_results():
                providers.results.add_result(result)
            return

        store_collection_name = providers.commands.get_store_collection_query(search_term)
        if store_collection_name:
            providers.runtime.ensure_startup_initialized()
            query_start_time = time.perf_counter()
            timings = []

            stage_start_time = time.perf_counter()
            results = self.build_store_collection_results(store_collection_name)
            providers.runtime.mark_timing(timings, "build_store_collection_results", stage_start_time)

            stage_start_time = time.perf_counter()
            for result in results:
                providers.results.add_result(result)
            providers.runtime.mark_timing(timings, "add_results", stage_start_time)
            providers.runtime.save_metric_caches(force=True)
            providers.runtime.log_query_profile(
                search_term,
                timings,
                (time.perf_counter() - query_start_time) * 1000,
                len(results),
            )
            return

        providers.runtime.ensure_startup_initialized()
        query_start_time = time.perf_counter()
        timings = []

        stage_start_time = time.perf_counter()
        providers.runtime.refresh_user_scoped_local_state_if_needed()
        providers.runtime.mark_timing(timings, "refresh_user_scoped_local_state_if_needed", stage_start_time)

        stage_start_time = time.perf_counter()
        providers.runtime.update_installed_games()
        providers.runtime.mark_timing(timings, "update_installed_games", stage_start_time)

        stage_start_time = time.perf_counter()
        providers.runtime.cleanup_caches_if_needed()
        providers.runtime.mark_timing(timings, "cleanup_caches_if_needed", stage_start_time)

        if not search_term:
            results = [self.build_launch_steam_result()]
            stage_start_time = time.perf_counter()
            games_to_show = self.get_empty_query_local_games()
            providers.runtime.mark_timing(timings, "collect_empty_local_games", stage_start_time)

            stage_start_time = time.perf_counter()
            results.extend(self.process_local_results(games_to_show, include_player_count=False))
            providers.runtime.mark_timing(timings, "process_empty_local_results", stage_start_time)
            if len(results) == 1:
                results.append(self.build_empty_state_result())
        else:
            stage_start_time = time.perf_counter()
            local_matches = self.collect_local_matches(search_term)
            providers.runtime.mark_timing(timings, "collect_local_matches", stage_start_time)

            stage_start_time = time.perf_counter()
            local_results = self.process_local_results(local_matches, include_player_count=True)
            providers.runtime.mark_timing(timings, "process_local_results", stage_start_time)

            stage_start_time = time.perf_counter()
            local_app_ids = {str(app_id) for app_id, _ in local_matches}
            providers.runtime.mark_timing(timings, "build_local_app_ids", stage_start_time)

            stage_start_time = time.perf_counter()
            search_result = providers.store.search_steam_api(search_term)
            providers.runtime.mark_timing(timings, "search_steam_api", stage_start_time)

            stage_start_time = time.perf_counter()
            store_results = providers.store.process_store_results(
                search_result["games"],
                skipped_app_ids=local_app_ids,
            )
            providers.runtime.mark_timing(timings, "process_store_results", stage_start_time)

            stage_start_time = time.perf_counter()
            results = self.merge_search_results(local_matches, local_results, store_results)
            providers.runtime.mark_timing(timings, "merge_search_results", stage_start_time)
            if not results:
                if search_result["error"]:
                    results.append(self.build_search_error_result(search_term, search_result["error"]))
                else:
                    results.append(self.build_empty_state_result(search_term))

        stage_start_time = time.perf_counter()
        for result in results:
            providers.results.add_result(result)
        providers.runtime.mark_timing(timings, "add_results", stage_start_time)
        providers.runtime.save_metric_caches(force=True)

        providers.runtime.log_query_profile(
            search_term,
            timings,
            (time.perf_counter() - query_start_time) * 1000,
            len(results),
        )
