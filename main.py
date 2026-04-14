import sys
from pathlib import Path

plugindir = Path(__file__).parent.resolve()
if str(plugindir) not in sys.path:
    sys.path.insert(0, str(plugindir))
lib_path = plugindir / "lib"
if str(lib_path) not in sys.path:
    sys.path.insert(0, str(lib_path))

import json
import os
import subprocess
import threading
import time
import traceback
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

import vdf

import currency_util

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

try:
    import winreg
except ImportError:
    import _winreg as winreg


class SteamPlugin:
    DEFAULT_ICON = "steam.png"
    LOCATION_ICON = "location.png"
    STEAMDB_ICON = "steamdb.png"
    MAX_LOG_SIZE_BYTES = 10 * 1024
    MAX_QUERY_RESULTS = 5
    MAX_EMPTY_QUERY_RESULTS = 67
    SEARCH_CACHE_TTL_SECONDS = 30
    PLAYER_COUNT_CACHE_TTL_SECONDS = 120
    BLACKLISTED_APP_IDS = {
        "228980",  # Steamworks Common Redistributables
    }
    PLATFORM_LABELS = {
        "windows": "Win",
        "mac": "Mac",
        "linux": "Linux",
    }

    def __init__(self):
        plugin_dir = Path(__file__).parent
        self.cache_dir = plugin_dir / "img_cache"
        self.country_cache_file = plugin_dir / "country_cache.json"
        self.log_file = plugin_dir / "steamflow.log"
        self.log_lock = threading.Lock()
        self.cache_dir.mkdir(exist_ok=True)

        self.steam_path = self.get_steam_path()
        self.country_code = self.load_cached_country_code()
        self.installed_games = {}
        self.installed_game_paths = {}
        self.last_update = 0
        self.search_cache = {}
        self.player_count_cache = {}
        self.update_installed_games()
        self.steam_icon_cache = (self.steam_path / "appcache" / "librarycache") if self.steam_path else None
        threading.Thread(target=self.cleanup_image_cache, daemon=True).start()

    def log(self, level, message):
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{timestamp}] [{level}] {message}\n"
        encoded = line.encode("utf-8", errors="replace")

        with self.log_lock:
            try:
                with open(self.log_file, "ab") as f:
                    f.write(encoded)

                if self.log_file.stat().st_size > self.MAX_LOG_SIZE_BYTES:
                    data = self.log_file.read_bytes()
                    trimmed = data[-self.MAX_LOG_SIZE_BYTES :]
                    newline_index = trimmed.find(b"\n")
                    if newline_index != -1 and newline_index + 1 < len(trimmed):
                        trimmed = trimmed[newline_index + 1 :]
                    self.log_file.write_bytes(trimmed)
            except Exception:
                pass

    def log_exception(self, message):
        self.log("ERROR", f"{message}\n{traceback.format_exc(limit=3).strip()}")

    def build_action(self, method, *parameters):
        return {"method": method, "parameters": list(parameters)}

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

    def build_context_data(self, app_id=None, name=None, install_path=None):
        data = {}
        if app_id is not None:
            data["app_id"] = str(app_id)
        if name is not None:
            data["name"] = name
        if install_path:
            data["install_path"] = install_path
        return data

    def is_blacklisted_app(self, app_id):
        return str(app_id) in self.BLACKLISTED_APP_IDS

    def load_cached_country_code(self):
        if self.country_cache_file.exists():
            try:
                with open(self.country_cache_file, "r", encoding="utf-8") as f:
                    cache_data = json.load(f)
                    cache_time = cache_data.get("timestamp", 0)
                    if time.time() - cache_time < 7 * 24 * 60 * 60:
                        return cache_data.get("country_code", "us")
            except Exception:
                self.log_exception("Failed to read country cache")

        threading.Thread(target=self._update_country_code_async, daemon=True).start()
        return "us"

    def _update_country_code_async(self):
        try:
            api_url = "http://ip-api.com/json/?fields=countryCode"
            with urllib.request.urlopen(api_url, timeout=2) as response:
                data = json.loads(response.read().decode("utf-8"))
                cc = data.get("countryCode", "us").lower()
                if cc in currency_util.CURRENCY_DATA:
                    self.country_code = cc
                    cache_data = {
                        "country_code": cc,
                        "timestamp": time.time(),
                    }
                    with open(self.country_cache_file, "w", encoding="utf-8") as f:
                        json.dump(cache_data, f)
        except Exception:
            self.log_exception("Failed to update country code asynchronously")

    def cleanup_image_cache(self):
        if not self.cache_dir.is_dir():
            return

        now = time.time()
        age_limit_seconds = 3 * 24 * 60 * 60
        try:
            for file_path in self.cache_dir.iterdir():
                if file_path.is_file():
                    file_mod_time = file_path.stat().st_mtime
                    if (now - file_mod_time) > age_limit_seconds:
                        file_path.unlink()
        except Exception:
            self.log_exception("Failed to clean up image cache")

    def get_steam_path(self):
        paths_to_try = [
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam"),
            (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Valve\Steam"),
        ]
        for hkey, path in paths_to_try:
            try:
                with winreg.OpenKey(hkey, path) as key:
                    steam_path, _ = winreg.QueryValueEx(key, "InstallPath")
                    steam_path = Path(steam_path)
                    if steam_path.exists():
                        return steam_path
            except Exception:
                continue
        return None

    def get_all_steam_library_paths(self):
        library_paths = []
        if not self.steam_path:
            return library_paths

        main_library_path = self.steam_path / "steamapps"
        if main_library_path.exists():
            library_paths.append(main_library_path)

        library_folders_vdf_path = main_library_path / "libraryfolders.vdf"
        try:
            if library_folders_vdf_path.exists():
                with open(library_folders_vdf_path, "r", encoding="utf-8") as f:
                    data = vdf.load(f)
                for key in data.get("libraryfolders", {}):
                    if key.isdigit():
                        folder_info = data["libraryfolders"][key]
                        if "path" in folder_info:
                            alt_path = Path(folder_info["path"]) / "steamapps"
                            if alt_path.exists() and alt_path not in library_paths:
                                library_paths.append(alt_path)
        except Exception:
            self.log_exception("Failed to load Steam library folders")
        return library_paths

    def update_installed_games(self):
        if time.time() - self.last_update < 300:
            return

        self.installed_games = {}
        self.installed_game_paths = {}
        if not self.steam_path:
            return

        all_library_paths = self.get_all_steam_library_paths()
        for steamapps_path in all_library_paths:
            try:
                if steamapps_path.exists():
                    for acf_file in steamapps_path.glob("appmanifest_*.acf"):
                        try:
                            with open(acf_file, "r", encoding="utf-8", errors="ignore") as f:
                                acf_data = vdf.load(f).get("AppState", {})
                            app_id = acf_data.get("appid")
                            name = acf_data.get("name")
                            install_dir = acf_data.get("installdir")
                            if app_id and name:
                                app_id = str(app_id)
                                if self.is_blacklisted_app(app_id):
                                    continue
                                self.installed_games[app_id] = name
                                if install_dir:
                                    self.installed_game_paths[app_id] = str(steamapps_path / "common" / install_dir)
                        except Exception:
                            self.log_exception(f"Failed to parse manifest: {acf_file}")
                            continue
            except Exception:
                self.log_exception(f"Failed to scan Steam library: {steamapps_path}")
                continue

        self.last_update = time.time()

    def search_steam_api(self, search_term):
        try:
            search_term = search_term.strip()
            if not search_term:
                return []

            cache_key = (search_term.lower(), self.country_code)
            cached_entry = self.search_cache.get(cache_key)
            if cached_entry and (time.time() - cached_entry["timestamp"]) < self.SEARCH_CACHE_TTL_SECONDS:
                return cached_entry["games"]

            encoded_term = urllib.parse.quote(search_term)
            api_url = f"https://store.steampowered.com/api/storesearch/?term={encoded_term}&cc={self.country_code}&l=en"
            req = urllib.request.Request(api_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=0.7) as response:
                data = json.loads(response.read().decode("utf-8"))

            games = []
            if "items" in data:
                for item in data["items"][:5]:
                    if self.is_blacklisted_app(item.get("id")):
                        continue
                    games.append(
                        {
                            "type": item.get("type"),
                            "id": item.get("id"),
                            "name": item.get("name", "Unknown Game"),
                            "platforms": item.get("platforms", {}),
                            "tiny_image": item.get("tiny_image"),
                            "has_price": "price" in item,
                            "price": item.get("price"),
                            "is_free": item.get("is_free", False),
                        }
                    )

            self.search_cache[cache_key] = {"timestamp": time.time(), "games": games}
            return games
        except Exception:
            self.log_exception(f"Steam search request failed for query: {search_term}")
            return []

    def get_local_game_icon(self, app_id):
        if not self.steam_icon_cache or not self.steam_icon_cache.exists():
            return "steam.png"

        icon_cache_path = self.steam_icon_cache / str(app_id)
        if not icon_cache_path.is_dir():
            return "steam.png"

        try:
            files = [f for f in icon_cache_path.iterdir() if f.suffix.lower() == ".jpg" and f.is_file()]
            filtered_files = [
                f
                for f in files
                if not (
                    f.name.lower().startswith("header")
                    or f.name.lower().startswith("library")
                    or f.name.lower().startswith("logo")
                )
            ]
            if filtered_files:
                return str(filtered_files[0])
        except Exception:
            self.log_exception(f"Failed to resolve local icon for app {app_id}")

        return "steam.png"

    def download_icon(self, image_url, save_path):
        try:
            with urllib.request.urlopen(image_url, timeout=2) as response:
                with open(save_path, "wb") as out_file:
                    out_file.write(response.read())
            return True
        except Exception:
            self.log_exception(f"Failed to download icon: {image_url}")
            return False

    def get_current_players(self, app_id):
        if not app_id:
            return None

        app_id = str(app_id)
        cached_entry = self.player_count_cache.get(app_id)
        if cached_entry and (time.time() - cached_entry["timestamp"]) < self.PLAYER_COUNT_CACHE_TTL_SECONDS:
            return cached_entry["player_count"]

        try:
            api_url = f"https://api.steampowered.com/ISteamUserStats/GetNumberOfCurrentPlayers/v1/?appid={app_id}"
            with urllib.request.urlopen(api_url, timeout=1) as response:
                data = json.loads(response.read().decode("utf-8"))
                if data.get("response", {}).get("result") == 1:
                    player_count = data["response"].get("player_count")
                    self.player_count_cache[app_id] = {
                        "timestamp": time.time(),
                        "player_count": player_count,
                    }
                    return player_count
        except Exception:
            self.log_exception(f"Failed to fetch player count for app {app_id}")
            return None

    def format_player_count(self, player_count):
        if player_count is None:
            return ""
        return f" | \U0001F465 {player_count:,}"

    def get_platform_labels(self, platforms):
        return [label for key, label in self.PLATFORM_LABELS.items() if platforms.get(key)]

    def get_platform_suffix(self, platforms):
        labels = self.get_platform_labels(platforms)
        if not labels:
            return ""
        return f" ({'/'.join(labels)})"

    def build_empty_state_result(self, search_term=None):
        if search_term:
            return self.build_result(
                title=f"No games found for '{search_term}'",
                subtitle="Try a different search term",
            )
        return self.build_result(
            title="SteamFlow",
            subtitle="No installed games found. Type to search Steam store...",
        )

    def build_store_context_data(self, app_id, name):
        return self.build_context_data(app_id=app_id, name=name)

    def build_launch_steam_result(self):
        return self.build_result(
            title="Launch Steam",
            subtitle="Open Steam",
            action=self.build_action("open_steam"),
            Score=10000,
        )

    def build_local_result(self, app_id, name, include_player_count=False):
        subtitle = f"Launch installed game (ID: {app_id})"
        if include_player_count:
            subtitle += self.format_player_count(self.get_current_players(app_id))

        return self.build_result(
            title=f"\U0001F3AE {name}",
            subtitle=subtitle,
            icon_path=self.get_local_game_icon(app_id),
            context_data=self.build_context_data(
                app_id=app_id,
                name=name,
                install_path=self.installed_game_paths.get(str(app_id)),
            ),
            action=self.build_action("launch_game", app_id),
        )

    def build_context_menu_item(self, title, subtitle, method, *parameters, icon_path=None):
        return self.build_result(
            title=title,
            subtitle=subtitle,
            icon_path=icon_path or self.DEFAULT_ICON,
            action=self.build_action(method, *parameters),
        )

    def context_menu(self, data):
        if not isinstance(data, dict):
            return []

        app_id = str(data.get("app_id", ""))
        name = data.get("name", "Game")
        install_path = data.get("install_path") or self.installed_game_paths.get(app_id)
        items = []

        if app_id:
            items.append(self.build_context_menu_item("Open in Steam Store", f"Open store page for {name}", "open_steam_store_page", app_id))
            items.append(
                self.build_context_menu_item(
                    "Open in SteamDB",
                    f"Open SteamDB page for {name}",
                    "open_steamdb_page",
                    app_id,
                    icon_path=self.STEAMDB_ICON,
                )
            )

        if install_path:
            items.append(
                self.build_context_menu_item(
                    "Browse local files",
                    f"Open installation folder for {name}",
                    "open_local_files",
                    install_path,
                    icon_path=self.LOCATION_ICON,
                )
            )

        return items

    def process_game_data(self, game_data):
        app_id = game_data.get("id")
        name = game_data.get("name")

        image_url = game_data.get("tiny_image")
        icon_path = "steam.png"
        if image_url and app_id:
            cached_icon_path = self.cache_dir / f"{app_id}.png"
            if cached_icon_path.exists():
                icon_path = str(cached_icon_path)
            elif self.download_icon(image_url, str(cached_icon_path)):
                icon_path = str(cached_icon_path)

        player_count_str = self.format_player_count(self.get_current_players(app_id))

        platforms = game_data.get("platforms", {})
        platform_str = self.get_platform_suffix(platforms)

        price_info = game_data.get("price")
        price_str = ""
        if game_data.get("is_free"):
            price_str = " | Free"
        elif game_data.get("type") == "app" and not game_data.get("has_price", False):
            price_str = " | Free"
        elif price_info and "final" in price_info:
            formatted_price = currency_util.format_price(price_info["final"], self.country_code)
            price_str = f" | {formatted_price}"

        return self.build_result(
            title=f"\U0001F6D2 {name}",
            subtitle=f"Open in Steam store{platform_str}{player_count_str}{price_str}",
            icon_path=icon_path,
            context_data=self.build_store_context_data(app_id, name),
            action=self.build_action("open_steam_store_page", app_id),
            AppID=str(app_id) if app_id is not None else None,
        )

    def collect_local_matches(self, search_term):
        search_lower = search_term.lower()
        matching_games = []
        for app_id, name in self.installed_games.items():
            if search_lower in name.lower():
                matching_games.append((app_id, name))
        matching_games.sort(key=lambda item: (item[1].lower().find(search_lower), len(item[1])))
        return matching_games[: self.MAX_QUERY_RESULTS]

    def process_store_results(self, api_results):
        if not api_results:
            return []

        with ThreadPoolExecutor(max_workers=self.MAX_QUERY_RESULTS) as executor:
            future_to_index = {
                executor.submit(self.process_game_data, game_data): index
                for index, game_data in enumerate(api_results)
            }
            processed_results = [None] * len(api_results)

            for future in as_completed(future_to_index):
                try:
                    processed_results[future_to_index[future]] = future.result()
                except Exception:
                    self.log_exception("Failed to process Steam store result")

        return [result for result in processed_results if result]

    def merge_search_results(self, local_matches, store_results):
        results = []
        local_app_ids = set()

        for app_id, name in local_matches:
            local_app_ids.add(str(app_id))
            results.append(self.build_local_result(app_id, name, include_player_count=True))

        for result in store_results:
            app_id = result.pop("AppID", None)
            if app_id and app_id in local_app_ids:
                continue
            results.append(result)

        return results

    def query(self, search_term):
        self.update_installed_games()
        if not search_term:
            results = [self.build_launch_steam_result()]
            games_to_show = sorted(self.installed_games.items(), key=lambda item: item[1].lower())[: self.MAX_EMPTY_QUERY_RESULTS]
            for app_id, name in games_to_show:
                results.append(self.build_local_result(app_id, name))
            if len(results) == 1:
                results.append(self.build_empty_state_result())
            return results

        local_matches = self.collect_local_matches(search_term)
        store_results = self.process_store_results(self.search_steam_api(search_term))
        results = self.merge_search_results(local_matches, store_results)
        if not results:
            results.append(self.build_empty_state_result(search_term))
        return results

    def launch_game(self, app_id):
        uri = f"steam://rungameid/{app_id}"
        try:
            os.startfile(uri)
            return "Game launched"
        except Exception as original_error:
            try:
                subprocess.run(["start", uri], shell=True)
                return "Game launched"
            except Exception:
                self.log("ERROR", f"Failed to launch game {app_id}: {original_error}")
                return f"Failed to launch game: {str(original_error)}"

    def open_steam_store_page(self, app_id):
        uri = f"steam://store/{app_id}"
        try:
            os.startfile(uri)
            return f"Steam store page opened for App ID: {app_id}"
        except Exception:
            try:
                import webbrowser

                webbrowser.open(f"https://store.steampowered.com/app/{app_id}/")
                return f"Steam store page opened in browser for App ID: {app_id}"
            except Exception as e:
                self.log("ERROR", f"Failed to open Steam store page for app {app_id}: {e}")
                return f"Failed to open Steam store page: {str(e)}"

    def open_steam(self):
        try:
            os.startfile("steam://open/main")
            return "Steam opened"
        except Exception:
            if self.steam_path:
                steam_exe = self.steam_path / "steam.exe"
                if steam_exe.exists():
                    try:
                        subprocess.run([str(steam_exe)])
                        return "Steam opened"
                    except Exception:
                        self.log_exception("Failed to launch steam.exe directly")
                        pass
            return "Failed to open Steam"

    def open_local_files(self, install_path):
        try:
            if install_path and Path(install_path).exists():
                os.startfile(install_path)
                return "Local files opened"
            return "Local files folder not found"
        except Exception as e:
            self.log("ERROR", f"Failed to open local files '{install_path}': {e}")
            return f"Failed to open local files: {str(e)}"

    def open_steamdb_page(self, app_id):
        try:
            import webbrowser

            webbrowser.open(f"https://steamdb.info/app/{app_id}/")
            return f"SteamDB page opened for App ID: {app_id}"
        except Exception as e:
            self.log("ERROR", f"Failed to open SteamDB page for app {app_id}: {e}")
            return f"Failed to open SteamDB page: {str(e)}"

    def safe_print_json(self, data):
        try:
            json_str = json.dumps(data, ensure_ascii=True)
            print(json_str)
            sys.stdout.flush()
        except Exception as e:
            fallback = {
                "result": [
                    {
                        "Title": "Encoding Error",
                        "SubTitle": f"Failed to encode output: {str(e)}",
                        "IcoPath": "steam.png",
                    }
                ]
            }
            print(json.dumps(fallback, ensure_ascii=True))
            sys.stdout.flush()

    def dispatch(self, method, parameters):
        parameter = parameters[0] if parameters else None
        handlers = {
            "query": lambda: self.query(parameter or ""),
            "context_menu": lambda: self.context_menu(parameter or {}),
            "launch_game": lambda: self.launch_game(parameter or ""),
            "open_steam_store_page": lambda: self.open_steam_store_page(parameter or ""),
            "open_steam": self.open_steam,
            "open_local_files": lambda: self.open_local_files(parameter or ""),
            "open_steamdb_page": lambda: self.open_steamdb_page(parameter or ""),
        }
        handler = handlers.get(method)
        if not handler:
            self.log("ERROR", f"Unknown method requested: {method}")
            return None
        return handler()


def main():
    plugin = SteamPlugin()
    try:
        input_data = (
            sys.stdin.read()
            if sys.stdin and not sys.stdin.isatty()
            else (sys.argv[1] if len(sys.argv) > 1 else '{"method": "query", "parameters": [""]}')
        )
        request = json.loads(input_data.strip() or "{}")
        method = request.get("method", "query")
        parameters = request.get("parameters", [""])

        result = plugin.dispatch(method, parameters)
        if result is not None:
            plugin.safe_print_json({"result": result})

    except Exception as e:
        plugin.log_exception("Unhandled plugin error")
        plugin.safe_print_json(
            {
                "result": [
                    {
                        "Title": "Steam Plugin Error",
                        "SubTitle": f"Critical error: {str(e)}",
                        "IcoPath": "steam.png",
                    }
                ]
            }
        )


if __name__ == "__main__":
    main()
