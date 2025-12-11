import sys
from pathlib import Path
from io import BytesIO

plugindir = Path(__file__).parent.resolve()
if str(plugindir) not in sys.path:
    sys.path.insert(0, str(plugindir))
lib_path = plugindir / 'lib'
if str(lib_path) not in sys.path:
    sys.path.insert(0, str(lib_path))

import json
import urllib.parse
import urllib.request
import subprocess
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import vdf

import currency_util

if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

try:
    import winreg
except ImportError:
    import _winreg as winreg

class SteamPlugin:
    def __init__(self):
        self.steam_path = self.get_steam_path()
        self.country_code = self.load_cached_country_code()
        self.installed_games = {}
        self.last_update = 0
        self.update_installed_games()
        plugin_dir = Path(__file__).parent
        self.cache_dir = plugin_dir / "img_cache"
        self.country_cache_file = plugin_dir / "country_cache.json"
        self.steam_icon_cache = (self.steam_path / "appcache" / "librarycache") if self.steam_path else None
        self.cache_dir.mkdir(exist_ok=True)
        threading.Thread(target=self.cleanup_image_cache, daemon=True).start()

    def load_cached_country_code(self):
        cache_file = Path(__file__).parent / "country_cache.json"
        if cache_file.exists():
            try:
                with open(cache_file, 'r') as f:
                    cache_data = json.load(f)
                    cache_time = cache_data.get('timestamp', 0)
                    if time.time() - cache_time < 7 * 24 * 60 * 60:
                        return cache_data.get('country_code', 'us')
            except:
                pass

        threading.Thread(target=self._update_country_code_async, daemon=True).start()
        return 'us'

    def _update_country_code_async(self):
        try:
            api_url = "http://ip-api.com/json/?fields=countryCode"
            with urllib.request.urlopen(api_url, timeout=2) as response:
                data = json.loads(response.read().decode('utf-8'))
                cc = data.get('countryCode', 'us').lower()
                if cc in currency_util.CURRENCY_DATA:
                    self.country_code = cc
                    cache_data = {
                        'country_code': cc,
                        'timestamp': time.time()
                    }
                    with open(self.country_cache_file, 'w') as f:
                        json.dump(cache_data, f)
        except:
            pass

    def cleanup_image_cache(self):
        if not self.cache_dir.is_dir(): return
        now = time.time()
        age_limit_seconds = 3 * 24 * 60 * 60
        try:
            for file_path in self.cache_dir.iterdir():
                if file_path.is_file():
                    file_mod_time = file_path.stat().st_mtime
                    if (now - file_mod_time) > age_limit_seconds:
                        file_path.unlink()
        except Exception: pass

    def get_steam_path(self):
        paths_to_try = [
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam"),
            (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Valve\Steam")
        ]
        for hkey, path in paths_to_try:
            try:
                with winreg.OpenKey(hkey, path) as key:
                    steam_path, _ = winreg.QueryValueEx(key, "InstallPath")
                    steam_path = Path(steam_path)
                    if steam_path.exists(): return steam_path
            except: continue
        return None

    def get_all_steam_library_paths(self):
        library_paths = []
        if not self.steam_path: return library_paths
        main_library_path = self.steam_path / "steamapps"
        if main_library_path.exists(): library_paths.append(main_library_path)
        library_folders_vdf_path = main_library_path / "libraryfolders.vdf"
        try:
            if library_folders_vdf_path.exists():
                with open(library_folders_vdf_path, 'r', encoding='utf-8') as f:
                    data = vdf.load(f)
                for key in data.get('libraryfolders', {}):
                    if key.isdigit():
                        folder_info = data['libraryfolders'][key]
                        if 'path' in folder_info:
                            alt_path = Path(folder_info['path']) / "steamapps"
                            if alt_path.exists() and alt_path not in library_paths:
                                library_paths.append(alt_path)
        except Exception: pass
        return library_paths

    def update_installed_games(self):
        if time.time() - self.last_update < 300: return
        self.installed_games = {}
        if not self.steam_path: return
        all_library_paths = self.get_all_steam_library_paths()
        for steamapps_path in all_library_paths:
            try:
                if steamapps_path.exists():
                    for acf_file in steamapps_path.glob("appmanifest_*.acf"):
                        try:
                            with open(acf_file, 'r', encoding='utf-8', errors='ignore') as f:
                                acf_data = vdf.load(f).get('AppState', {})
                            app_id = acf_data.get('appid')
                            name = acf_data.get('name')
                            if app_id and name: self.installed_games[app_id] = name
                        except Exception: continue
            except Exception: continue
        self.last_update = time.time()

    def search_steam_api(self, search_term):
        try:
            search_term = search_term.strip()
            if not search_term: return []
            encoded_term = urllib.parse.quote(search_term)
            api_url = f"https://store.steampowered.com/api/storesearch/?term={encoded_term}&cc={self.country_code}&l=en"
            req = urllib.request.Request(api_url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=0.7) as response:
                data = json.loads(response.read().decode('utf-8'))
            games = []
            if 'items' in data:
                for item in data['items'][:5]:
                    games.append({
                        'id': item.get('id'), 'name': item.get('name', 'Unknown Game'),
                        'platforms': item.get('platforms', {}), 'tiny_image': item.get('tiny_image'),
                        'price': item.get('price')
                    })
            return games
        except Exception: return []
    
    def get_local_game_icon(self, app_id):
        if not self.steam_icon_cache or not self.steam_icon_cache.exists():
            return "steam.png"

        icon_cache_path = self.steam_icon_cache / str(app_id)

        if not icon_cache_path.is_dir():
            return "steam.png"

        try:
            files = [
                f for f in icon_cache_path.iterdir()
                if f.suffix.lower() == '.jpg' and f.is_file()
            ]

            filtered_files = [
                f for f in files
                if not (f.name.lower().startswith('header') or
                       f.name.lower().startswith('library') or
                       f.name.lower().startswith('logo'))
            ]

            if filtered_files:
                return str(filtered_files[0])
        except Exception:
            pass

        return "steam.png"

    def download_icon(self, image_url, save_path):
        try:
            with urllib.request.urlopen(image_url, timeout=2) as response:
                with open(save_path, 'wb') as out_file:
                    out_file.write(response.read())
            return True
        except:
            return False

    def get_current_players(self, app_id):
        if not app_id: return None
        try:
            api_url = f"https://api.steampowered.com/ISteamUserStats/GetNumberOfCurrentPlayers/v1/?appid={app_id}"
            with urllib.request.urlopen(api_url, timeout=1) as response:
                data = json.loads(response.read().decode('utf-8'))
                if data.get('response', {}).get('result') == 1:
                    return data['response'].get('player_count')
        except Exception: return None

    def process_game_data(self, game_data):
        app_id = game_data.get('id')
        name = game_data.get('name')

        image_url = game_data.get('tiny_image')
        icon_path = "steam.png"
        if image_url and app_id:
            cached_icon_path = self.cache_dir / f"{app_id}.png"
            if cached_icon_path.exists():
                icon_path = str(cached_icon_path)
            else:
                if self.download_icon(image_url, str(cached_icon_path)):
                    icon_path = str(cached_icon_path)
        
        player_count = self.get_current_players(app_id)
        player_count_str = ""
        if player_count is not None:
            player_count_str = f" | 👥 {player_count:,}"
        
        platforms = game_data.get('platforms', {})
        platform_text = []
        if platforms.get('windows'): platform_text.append('Win')
        if platforms.get('mac'): platform_text.append('Mac')
        if platforms.get('linux'): platform_text.append('Linux')
        platform_str = f" ({'/'.join(platform_text)})" if platform_text else ""
        
        price_info = game_data.get('price')
        price_str = ""
        if price_info and 'final' in price_info:
            formatted_price = currency_util.format_price(price_info['final'], self.country_code)
            price_str = f" | {formatted_price}"
            
        return {
            "Title": f"🛒 {name}",
            "SubTitle": f"Open in Steam store{platform_str}{player_count_str}{price_str}",
            "IcoPath": icon_path,
            "JsonRPCAction": {"method": "open_steam_store_page", "parameters": [app_id]}
        }

    def query(self, search_term):
        self.update_installed_games()
        results = []
        if not search_term:
            return [{"Title": "SteamFlow", "SubTitle": f"Found {len(self.installed_games)} installed games. Type to search...", "IcoPath": "steam.png"}]
        
        search_lower = search_term.lower()
        matching_games = []
        for app_id, name in self.installed_games.items():
            if search_lower in name.lower():
                matching_games.append((app_id, name))
        matching_games.sort(key=lambda x: (x[1].lower().find(search_lower), len(x[1])))
        
        for app_id, name in matching_games[:5]:
            local_icon = self.get_local_game_icon(app_id)
            results.append({
                "Title": f"🎮 {name}",
                "SubTitle": f"Launch installed game (ID: {app_id})",
                "IcoPath": local_icon,
                "JsonRPCAction": {"method": "launch_game", "parameters": [app_id]}
            })
        
        api_results = self.search_steam_api(search_term)
        
        if api_results:
            with ThreadPoolExecutor(max_workers=5) as executor:
                future_to_game = {
                    executor.submit(self.process_game_data, game_data): game_data 
                    for game_data in api_results
                }
                
                for future in as_completed(future_to_game):
                    try:
                        result = future.result()
                        if result:
                            results.append(result)
                    except:
                        pass
        
        if not results:
            results.append({
                "Title": f"No games found for '{search_term}'", 
                "SubTitle": "Try a different search term",
                "IcoPath": "steam.png"
            })
        
        return results
    
    def launch_game(self, app_id):
        try: subprocess.run(['start', f"steam://rungameid/{app_id}"], shell=True); return "Game launched"
        except Exception as e: return f"Failed to launch game: {str(e)}"

    def open_steam_store_page(self, app_id):
        try: subprocess.run(['start', f"steam://store/{app_id}"], shell=True, check=True); return f"Steam store page opened for App ID: {app_id}"
        except Exception:
            try: import webbrowser; webbrowser.open(f"https://store.steampowered.com/app/{app_id}/"); return f"Steam store page opened in browser for App ID: {app_id}"
            except Exception as e: return f"Failed to open Steam store page: {str(e)}"

    def open_steam(self):
        try: subprocess.run(['start', 'steam://open/main'], shell=True); return "Steam opened"
        except:
            if self.steam_path:
                steam_exe = self.steam_path / "steam.exe"
                if steam_exe.exists():
                    try: subprocess.run([str(steam_exe)]); return "Steam opened"
                    except: pass
            return "Failed to open Steam"

    def safe_print_json(self, data):
        try:
            json_str = json.dumps(data, ensure_ascii=True)
            print(json_str)
            sys.stdout.flush()
        except Exception as e:
            fallback = {"result": [{"Title": "Encoding Error", "SubTitle": f"Failed to encode output: {str(e)}", "IcoPath": "steam.png"}]}
            print(json.dumps(fallback, ensure_ascii=True))
            sys.stdout.flush()

def main():
    plugin = SteamPlugin()
    try:
        input_data = sys.stdin.read() if sys.stdin and not sys.stdin.isatty() else (sys.argv[1] if len(sys.argv) > 1 else '{"method": "query", "parameters": [""]}')
        request = json.loads(input_data.strip() or '{}')
        method = request.get("method", "query")
        parameters = request.get("parameters", [""])
        
        result = None
        if method == "query": result = plugin.query(parameters[0] if parameters else "")
        elif method == "launch_game": result = plugin.launch_game(parameters[0] if parameters else "")
        elif method == "open_steam_store_page": result = plugin.open_steam_store_page(parameters[0] if parameters else "")
        elif method == "open_steam": result = plugin.open_steam()
        
        if result: plugin.safe_print_json({"result": result})
            
    except Exception as e:
        plugin.safe_print_json({"result": [{"Title": "Steam Plugin Error", "SubTitle": f"Critical error: {str(e)}", "IcoPath": "steam.png"}]})

if __name__ == "__main__":
    main()