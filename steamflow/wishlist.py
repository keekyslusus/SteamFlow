import json
import subprocess
import sys
import threading
import time
from pathlib import Path

from . import util_steam_date


class SteamPluginWishlistMixin:
    def ensure_wishlist_cache_loaded(self):
        with self.state_lock:
            if self.wishlist_cache_loaded:
                return
        self.load_wishlist_cache()

    def normalize_wishlist_items(self, items):
        normalized_items = []
        if not isinstance(items, list):
            return normalized_items

        for item in items:
            if not isinstance(item, dict):
                continue
            app_id = str(item.get("appid", "")).strip()
            if not app_id:
                continue
            try:
                date_added = int(item.get("date_added", 0) or 0)
            except (TypeError, ValueError):
                date_added = 0
            try:
                priority = int(item.get("priority", 0) or 0)
            except (TypeError, ValueError):
                priority = 0
            normalized_items.append(
                {
                    "appid": app_id,
                    "date_added": date_added,
                    "priority": priority,
                }
            )
        return normalized_items

    def clear_wishlist_cache(self):
        with self.state_lock:
            self.wishlist_last_attempt = 0
            self.wishlist_last_sync = 0
            self.wishlist_steamid64 = None
            self.wishlist_items = []
            self.wishlist_cache_loaded = True
        self.save_wishlist_cache()

    def wishlist_cache_is_fresh(self, steamid64):
        self.ensure_wishlist_cache_loaded()
        with self.state_lock:
            cached_steamid64 = self.wishlist_steamid64
            last_sync = self.wishlist_last_sync
        return bool(
            steamid64
            and cached_steamid64 == steamid64
            and last_sync
            and (time.time() - last_sync) < self.WISHLIST_CACHE_TTL_SECONDS
        )

    def fetch_wishlist_items_from_api(self, api_key, steamid64, timeout=3):
        api_key = self.normalize_steam_web_api_key(api_key)
        steamid64 = str(steamid64 or "").strip()
        if not api_key or not steamid64:
            raise ValueError("Missing Steam API credentials")

        api_url = (
            "https://api.steampowered.com/IWishlistService/GetWishlist/v1/"
            f"?key={api_key}&steamid={steamid64}"
        )
        response = self._http_get(api_url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0"})
        data = json.loads(response.data.decode("utf-8"))
        items = data.get("response", {}).get("items", [])
        if not isinstance(items, list):
            return []
        return self.normalize_wishlist_items(items)

    def _refresh_wishlist_worker(self):
        try:
            self.refresh_wishlist()
        finally:
            with self.state_lock:
                self.pending_wishlist_refresh = False

    def wishlist_worker_is_running(self):
        lock_file = getattr(self, "wishlist_worker_lock_file", None)
        if not lock_file or not Path(lock_file).exists():
            return False
        try:
            return (time.time() - Path(lock_file).stat().st_mtime) < 15 * 60
        except OSError:
            return False

    def start_wishlist_hydration_worker(self, wishlist_items):
        if not wishlist_items:
            return
        if self.wishlist_worker_is_running():
            return
        worker_script = self.plugin_dir / "steam_wishlist_worker.py"
        if not worker_script.exists():
            return

        app_ids = []
        seen_app_ids = set()
        for wishlist_item in wishlist_items:
            app_id = str(wishlist_item.get("appid", "")).strip()
            if app_id and app_id not in seen_app_ids:
                seen_app_ids.add(app_id)
                app_ids.append(app_id)
        if not app_ids:
            return

        startupinfo = None
        creationflags = 0
        if sys.platform == "win32":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
            creationflags = (
                subprocess.CREATE_NO_WINDOW
                | subprocess.DETACHED_PROCESS
                | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            )

        try:
            subprocess.Popen(
                [
                    sys.executable,
                    str(worker_script),
                    self.get_country_code(),
                    ",".join(app_ids),
                ],
                startupinfo=startupinfo,
                creationflags=creationflags,
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                cwd=str(self.plugin_dir),
            )
        except Exception:
            self.log_exception("Failed to start Steam wishlist worker")

    def schedule_wishlist_refresh(self, force=False):
        if not self.has_owned_api_key() or not self.is_owned_api_key_bound_to_active_user():
            return

        self.ensure_wishlist_cache_loaded()
        steamid64 = self.get_active_steam_user_steamid64()
        if not steamid64:
            return

        with self.state_lock:
            if self.pending_wishlist_refresh:
                return
            if not force and self.wishlist_cache_is_fresh(steamid64):
                return
            self.pending_wishlist_refresh = True

        threading.Thread(target=self._refresh_wishlist_worker, daemon=True).start()

    def refresh_wishlist(self):
        if not self.has_owned_api_key() or not self.is_owned_api_key_bound_to_active_user():
            return

        api_key = self.get_owned_api_key()
        steamid64 = self.get_active_steam_user_steamid64()
        if not api_key or not steamid64:
            return

        with self.state_lock:
            self.wishlist_last_attempt = time.time()
        try:
            items = self.fetch_wishlist_items_from_api(api_key, steamid64, timeout=3)
        except Exception:
            self.log_exception("Failed to fetch Steam wishlist")
            self.save_wishlist_cache()
            return

        with self.state_lock:
            self.wishlist_items = items
            self.wishlist_steamid64 = steamid64
            self.wishlist_last_sync = time.time()
            self.wishlist_last_attempt = self.wishlist_last_sync
            self.wishlist_cache_loaded = True
        self.save_wishlist_cache()

    def get_wishlist_items(self):
        if not self.has_owned_api_key():
            return [], "Steam API Not Configured"
        if not self.is_owned_api_key_bound_to_active_user():
            return [], "Steam API Bound to Another Account"

        self.ensure_wishlist_cache_loaded()
        steamid64 = self.get_active_steam_user_steamid64()
        if not steamid64:
            return [], "No active Steam account found"

        with self.state_lock:
            cached_items = list(self.wishlist_items)
            cached_steamid64 = self.wishlist_steamid64

        if cached_steamid64 == steamid64 and cached_items:
            if not self.wishlist_cache_is_fresh(steamid64):
                self.schedule_wishlist_refresh()
            return cached_items, None

        api_key = self.get_owned_api_key()
        with self.state_lock:
            self.wishlist_last_attempt = time.time()
        try:
            items = self.fetch_wishlist_items_from_api(api_key, steamid64, timeout=3)
        except Exception as error:
            self.log_exception("Failed to fetch Steam wishlist")
            if cached_steamid64 == steamid64 and cached_items:
                return cached_items, None
            error_message = str(error).strip()
            return [], error_message or "Steam wishlist request failed"

        with self.state_lock:
            self.wishlist_items = items
            self.wishlist_steamid64 = steamid64
            self.wishlist_last_sync = time.time()
            self.wishlist_last_attempt = self.wishlist_last_sync
            self.wishlist_cache_loaded = True
        self.save_wishlist_cache()
        return items, None

    def format_wishlist_added(self, date_added):
        formatted_age = util_steam_date.format_wishlisted_date(date_added)
        if not formatted_age:
            return ""
        return f" | Wishlisted {formatted_age}"

    def build_wishlist_result(self, wishlist_item, allow_cold_detail_fetch=True):
        app_id = wishlist_item["appid"]
        metadata = self.get_app_details_metadata(app_id, allow_network_on_miss=allow_cold_detail_fetch)
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
        }
        result = self.process_game_data(game_data, allow_cold_metric_fetch=allow_cold_detail_fetch)
        result["SubTitle"] = f"{result.get('SubTitle', '')}{self.format_wishlist_added(wishlist_item.get('date_added'))}"
        return result

    def build_wishlist_status_result(self, loaded_count, total_count, search_term="", matching_count=None):
        if search_term:
            title = f"Syncing Steam Wishlist For '{search_term}'"
        else:
            title = "Syncing Steam Wishlist"

        subtitle = f"Loaded details for {loaded_count} of {total_count} wishlist games"
        if matching_count is not None and search_term:
            subtitle += f" | {matching_count} matches loaded so far"
        subtitle += " | More titles will appear as the cache warms up"
        return self.build_result(
            title=title,
            subtitle=subtitle,
            icon_path=self.OWNED_ICON,
            action=self.build_action("open_my_steam_wishlist"),
            Score=20501,
        )

    def build_wishlist_empty_query_result(self, search_term):
        return self.build_result(
            title=f"No wishlist games found for '{search_term}'",
            subtitle="Try a different wishlist search term or wait for more wishlist details to finish loading",
            icon_path=self.OWNED_ICON,
            Score=20500,
        )

    def build_wishlist_results(self, search_term=""):
        normalized_search = str(search_term or "").strip().lower()
        wishlist_items, error = self.get_wishlist_items()
        if error:
            return [self.build_wishlist_unavailable_result(error)]
        if not wishlist_items:
            return [
                self.build_result(
                    title="Steam Wishlist",
                    subtitle="No wishlist items found for the active Steam account",
                    icon_path=self.OWNED_ICON,
                    Score=20500,
                )
            ]

        sorted_items = sorted(
            wishlist_items,
            key=lambda item: (-int(item.get("date_added", 0) or 0), item["appid"]),
        )

        for wishlist_item in sorted_items[: self.WISHLIST_COLD_DETAIL_FETCH_LIMIT]:
            self.get_app_details_metadata(wishlist_item["appid"], allow_network_on_miss=True)

        loaded_count = 0
        missing_items = []
        visible_results = []
        matching_loaded_count = 0

        for wishlist_item in sorted_items:
            metadata = self.get_app_details_metadata(wishlist_item["appid"], allow_network_on_miss=False)
            if metadata and metadata.get("name"):
                loaded_count += 1
                name_matches = not normalized_search or normalized_search in metadata["name"].lower()
                if name_matches:
                    matching_loaded_count += 1
                    if len(visible_results) < self.MAX_WISHLIST_RESULTS:
                        result = self.build_wishlist_result(wishlist_item, allow_cold_detail_fetch=False)
                        if result:
                            visible_results.append(result)
            else:
                missing_items.append(wishlist_item)

        if missing_items:
            self.start_wishlist_hydration_worker(missing_items)

        results = []
        if missing_items:
            results.append(
                self.build_wishlist_status_result(
                    loaded_count,
                    len(sorted_items),
                    search_term=search_term,
                    matching_count=matching_loaded_count if normalized_search else None,
                )
            )

        if visible_results:
            results.extend(visible_results)
            return results

        if normalized_search:
            if missing_items:
                return results
            return [self.build_wishlist_empty_query_result(search_term)]

        if results:
            return results

        return [
            self.build_result(
                title="Steam Wishlist",
                subtitle="No wishlist items found for the active Steam account",
                icon_path=self.OWNED_ICON,
                Score=20500,
            )
        ]

    def build_wishlist_unavailable_result(self, reason):
        api_query = self.build_plugin_query("api")
        subtitle_by_reason = {
            "Steam API Not Configured": f"Save a Steam Web API key first with `{api_query}`",
            "Steam API Bound to Another Account": "The saved Steam API key is bound to another Steam account",
            "No active Steam account found": "Sign into Steam to load your wishlist",
        }
        action = None
        if reason in {"Steam API Not Configured", "Steam API Bound to Another Account"}:
            action = {
                "method": "change_query",
                "parameters": [api_query, True],
                "dontHideAfterAction": True,
            }
        return self.build_result(
            title="Steam Wishlist Unavailable",
            subtitle=subtitle_by_reason.get(reason, reason or "Couldn't load the Steam wishlist"),
            icon_path=self.OWNED_ICON,
            action=action,
            Score=20500,
        )
