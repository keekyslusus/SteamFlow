import time
from concurrent.futures import ThreadPoolExecutor, as_completed


class SteamPluginUIQueryMixin:
    def collect_local_matches(self, search_term):
        search_lower = search_term.lower()
        matches = []
        for app_id, name in self.get_installed_games_items():
            if search_lower in name.lower():
                matches.append((app_id, name))
        matches.sort(key=lambda item: (item[1].lower().find(search_lower), len(item[1])))
        return matches[: self.MAX_QUERY_RESULTS]

    def get_empty_query_local_games(self):
        games = self.get_installed_games_items()
        if self.should_sort_local_by_recent():
            games.sort(
                key=lambda item: (
                    -(self.get_last_played_timestamp(item[0]) or 0),
                    item[1].lower(),
                )
            )
        else:
            games.sort(key=lambda item: item[1].lower())
        return games[: self.MAX_EMPTY_QUERY_RESULTS]

    def process_local_results(self, local_matches, include_player_count=False):
        if not local_matches:
            return []

        if not include_player_count:
            return [self.build_local_result(app_id, name) for app_id, name in local_matches]

        with ThreadPoolExecutor(max_workers=min(len(local_matches), self.MAX_QUERY_RESULTS)) as executor:
            future_to_index = {}
            if self.should_show_player_count():
                future_to_index = {
                    executor.submit(self.get_current_players, app_id): index
                    for index, (app_id, _name) in enumerate(local_matches)
                }
            player_counts = [None] * len(local_matches)

            for future in as_completed(future_to_index):
                index = future_to_index[future]
                try:
                    player_counts[index] = future.result()
                except Exception:
                    self.log_exception("Failed to process local player count")

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

    def query(self, search_term):
        if self.is_help_query(search_term):
            self.ensure_startup_initialized()
            for result in self.build_help_results():
                self.add_result(result)
            return

        if self.is_wishlist_query(search_term):
            self.ensure_startup_initialized()
            for result in self.build_wishlist_results(self.get_wishlist_query_text(search_term) or ""):
                self.add_result(result)
            return

        if self.is_switch_account_query(search_term):
            self.ensure_startup_initialized()
            for result in self.build_switch_account_results():
                self.add_result(result)
            return

        if self.is_status_query(search_term):
            self.ensure_startup_initialized()
            for result in self.build_status_results():
                self.add_result(result)
            return

        if self.is_owned_api_query(search_term):
            self.ensure_startup_initialized()
            for result in self.build_owned_api_results():
                self.add_result(result)
            return

        self.ensure_startup_initialized()
        query_start_time = time.perf_counter()
        timings = []

        stage_start_time = time.perf_counter()
        self.refresh_user_scoped_local_state_if_needed()
        self.mark_timing(timings, "refresh_user_scoped_local_state_if_needed", stage_start_time)

        stage_start_time = time.perf_counter()
        self.update_installed_games()
        self.mark_timing(timings, "update_installed_games", stage_start_time)

        stage_start_time = time.perf_counter()
        self.cleanup_caches_if_needed()
        self.mark_timing(timings, "cleanup_caches_if_needed", stage_start_time)

        if not search_term:
            results = [self.build_launch_steam_result()]
            stage_start_time = time.perf_counter()
            games_to_show = self.get_empty_query_local_games()
            self.mark_timing(timings, "collect_empty_local_games", stage_start_time)

            stage_start_time = time.perf_counter()
            results.extend(self.process_local_results(games_to_show, include_player_count=False))
            self.mark_timing(timings, "process_empty_local_results", stage_start_time)
            if len(results) == 1:
                results.append(self.build_empty_state_result())
        else:
            stage_start_time = time.perf_counter()
            local_matches = self.collect_local_matches(search_term)
            self.mark_timing(timings, "collect_local_matches", stage_start_time)

            stage_start_time = time.perf_counter()
            local_results = self.process_local_results(local_matches, include_player_count=True)
            self.mark_timing(timings, "process_local_results", stage_start_time)

            stage_start_time = time.perf_counter()
            local_app_ids = {str(app_id) for app_id, _ in local_matches}
            self.mark_timing(timings, "build_local_app_ids", stage_start_time)

            stage_start_time = time.perf_counter()
            search_result = self.search_steam_api(search_term)
            self.mark_timing(timings, "search_steam_api", stage_start_time)

            stage_start_time = time.perf_counter()
            store_results = self.process_store_results(
                search_result["games"],
                skipped_app_ids=local_app_ids,
            )
            self.mark_timing(timings, "process_store_results", stage_start_time)

            stage_start_time = time.perf_counter()
            results = self.merge_search_results(local_matches, local_results, store_results)
            self.mark_timing(timings, "merge_search_results", stage_start_time)
            if not results:
                if search_result["error"]:
                    results.append(self.build_search_error_result(search_term, search_result["error"]))
                else:
                    results.append(self.build_empty_state_result(search_term))

        stage_start_time = time.perf_counter()
        for result in results:
            self.add_result(result)
        self.mark_timing(timings, "add_results", stage_start_time)
        self.save_metric_caches(force=True)

        self.log_query_profile(
            search_term,
            timings,
            (time.perf_counter() - query_start_time) * 1000,
            len(results),
        )
