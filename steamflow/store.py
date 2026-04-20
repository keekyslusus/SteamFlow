import json
import time
import urllib.parse


class SteamPluginStoreMixin:
    def update_app_details_cache(self, app_id, metadata, success):
        if not app_id:
            return
        self._update_metric_cache_entry(
            self.app_details_cache,
            app_id,
            success=bool(success),
            metadata=dict(metadata or {}),
        )

    def fetch_app_details_metadata(self, app_id):
        start_time = time.perf_counter()
        app_id = str(app_id)
        try:
            country_code = self.get_country_code() if self.should_show_prices() else "us"
            api_url = f"https://store.steampowered.com/api/appdetails?appids={app_id}&cc={country_code}&l=en"
            response = self._http_get(api_url, timeout=1.5, headers={"User-Agent": "Mozilla/5.0"})
            data = json.loads(response.data.decode("utf-8"))
            app_details = data.get(app_id, {})
            if not isinstance(app_details, dict) or not app_details.get("success"):
                self.log_slow_call("fetch_app_details_metadata", (time.perf_counter() - start_time) * 1000, f"app_id={app_id} success=false")
                return None

            details = app_details.get("data", {})
            if not isinstance(details, dict):
                self.log_slow_call("fetch_app_details_metadata", (time.perf_counter() - start_time) * 1000, f"app_id={app_id} invalid-data")
                return None

            raw_is_free = details.get("is_free")
            if isinstance(raw_is_free, bool):
                is_free = raw_is_free
            elif raw_is_free in (0, 1):
                is_free = bool(raw_is_free)
            else:
                is_free = None

            metadata = {
                "type": str(details.get("type", "") or "").strip().lower(),
                "is_free": is_free,
                "name": str(details.get("name", "") or "").strip(),
                "capsule_image": details.get("capsule_image") or details.get("header_image"),
                "platforms": details.get("platforms") if isinstance(details.get("platforms"), dict) else {},
                "has_price": isinstance(details.get("price_overview"), dict),
                "price": details.get("price_overview") if isinstance(details.get("price_overview"), dict) else None,
                "coming_soon": bool((details.get("release_date") or {}).get("coming_soon")),
                "release_date_text": str((details.get("release_date") or {}).get("date", "") or "").strip(),
            }
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
            self.finish_metric_refresh("pending_app_details_refresh", app_id)

    def get_app_details_metadata(self, app_id, allow_network_on_miss=True):
        if not app_id:
            return None

        app_id = str(app_id)
        with self.state_lock:
            cached_entry = self.app_details_cache.get(app_id)

        if cached_entry:
            ttl_seconds = (
                self.APP_DETAILS_CACHE_TTL_SECONDS
                if cached_entry.get("success")
                else self.APP_DETAILS_FAILURE_CACHE_TTL_SECONDS
            )
            is_fresh = (time.time() - cached_entry.get("timestamp", 0)) < ttl_seconds
            metadata = cached_entry.get("metadata") if cached_entry.get("success") else None
            if is_fresh:
                return metadata
            self.start_metric_refresh("pending_app_details_refresh", app_id, self._refresh_app_details_worker)
            return metadata

        if not allow_network_on_miss:
            self.start_metric_refresh("pending_app_details_refresh", app_id, self._refresh_app_details_worker)
            return None

        metadata = self.fetch_app_details_metadata(app_id)
        self.update_app_details_cache(app_id, metadata, success=metadata is not None)
        return metadata

    def is_paid_base_game(self, app_id, allow_network_on_miss=True):
        metadata = self.get_app_details_metadata(app_id, allow_network_on_miss=allow_network_on_miss)
        if not metadata:
            return False
        return metadata.get("type") == "game" and metadata.get("is_free") is False

    def get_search_error_message(self, error):
        if isinstance(error, self.urllib3.exceptions.TimeoutError):
            return "Steam store request timed out. Try again."
        if isinstance(error, self.urllib3.exceptions.HTTPError):
            return "Couldn't reach Steam store. Check your connection."
        return "Steam store search failed. Try again."

    def search_steam_api(self, search_term):
        self.cleanup_caches_if_needed()
        start_time = time.perf_counter()
        try:
            search_term = search_term.strip()
            if not search_term:
                return {"games": [], "error": None}

            country_code = self.get_country_code() if self.should_show_prices() else "us"
            cache_key = (search_term.lower(), country_code)
            with self.state_lock:
                cached_entry = self.search_cache.get(cache_key)
            if cached_entry and (time.time() - cached_entry["timestamp"]) < self.SEARCH_CACHE_TTL_SECONDS:
                return {"games": cached_entry["games"], "error": None}

            encoded_term = urllib.parse.quote(search_term)
            api_url = f"https://store.steampowered.com/api/storesearch/?term={encoded_term}&cc={country_code}&l=en"
            response = self._http_get(api_url, timeout=0.7, headers={"User-Agent": "Mozilla/5.0"})
            data = json.loads(response.data.decode("utf-8"))

            blacklist = self.get_blacklisted_app_ids()
            games = []
            if "items" in data:
                for item in data["items"][: self.MAX_QUERY_RESULTS]:
                    app_id = item.get("id")
                    if str(app_id) in blacklist:
                        continue
                    games.append(
                        {
                            "type": item.get("type"),
                            "id": app_id,
                            "name": item.get("name", "Unknown Game"),
                            "platforms": item.get("platforms", {}),
                            "tiny_image": item.get("tiny_image"),
                            "has_price": "price" in item,
                            "price": item.get("price"),
                            "is_free": item.get("is_free", False),
                        }
                    )

            with self.state_lock:
                self.search_cache[cache_key] = {"timestamp": time.time(), "games": games}
            self.log_slow_call("search_steam_api", (time.perf_counter() - start_time) * 1000, f"query='{search_term}'")
            return {"games": games, "error": None}
        except Exception as error:
            self.log_exception(f"Steam search request failed for query: {search_term}")
            self.log_slow_call("search_steam_api", (time.perf_counter() - start_time) * 1000, f"query='{search_term}'")
            return {"games": [], "error": self.get_search_error_message(error)}
