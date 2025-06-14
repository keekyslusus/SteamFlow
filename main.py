import sys

from pathlib import Path

plugindir = Path.absolute(Path(__file__).parent)
lib_path = plugindir / 'lib'
if str(lib_path) not in sys.path:
    sys.path.insert(0, str(lib_path))

import json
import os
import re
import urllib.parse
import urllib.request
import subprocess
import time
import datetime
from io import BytesIO

try:
    from PIL import Image
except ImportError:
    print(json.dumps({
        "result": [{
            "Title": "Error: 'Pillow' library not found",
            "SubTitle": "Please run 'pip install Pillow' in your command prompt.",
            "IcoPath": "steam.png"
        }]
    }))
    sys.exit()

try:
    import vdf 
except ImportError:
    print(json.dumps({
        "result": [{
            "Title": "Error: 'vdf' library not found",
            "SubTitle": "Please run 'pip install vdf' in your command prompt.",
            "IcoPath": "steam.png"
        }]
    }))
    sys.exit()

if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

try:
    import winreg
except ImportError:
    import _winreg as winreg

class SteamPlugin:
    def __init__(self):
        self.steam_path = self.get_steam_path()
        self.installed_games = {}
        self.last_update = 0
        self.update_installed_games()
        plugin_dir = os.path.dirname(__file__)
        self.cache_dir = os.path.join(plugin_dir, "img_cache")
        if not os.path.exists(self.cache_dir):
            os.makedirs(self.cache_dir)
            

        self.cleanup_image_cache()
    
    def cleanup_image_cache(self):
        if not os.path.isdir(self.cache_dir):
            return

        now = time.time()
        age_limit_seconds = 3 * 24 * 60 * 60

        try:
            for filename in os.listdir(self.cache_dir):
                file_path = os.path.join(self.cache_dir, filename)
                if os.path.isfile(file_path):
                    file_mod_time = os.path.getmtime(file_path)
                    if (now - file_mod_time) > age_limit_seconds:
                        os.remove(file_path)
        except Exception:
            pass

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
                    if os.path.exists(steam_path): return steam_path
            except: continue
        return None
        
    def get_all_steam_library_paths(self):
        library_paths = []
        if not self.steam_path: return library_paths
        main_library_path = os.path.join(self.steam_path, "steamapps")
        if os.path.exists(main_library_path): library_paths.append(main_library_path)
        library_folders_vdf_path = os.path.join(main_library_path, "libraryfolders.vdf")
        try:
            if os.path.exists(library_folders_vdf_path):
                with open(library_folders_vdf_path, 'r', encoding='utf-8') as f:
                    data = vdf.load(f)
                for key in data.get('libraryfolders', {}):
                    if key.isdigit():
                        folder_info = data['libraryfolders'][key]
                        if 'path' in folder_info:
                            alt_path = os.path.join(folder_info['path'], "steamapps")
                            if os.path.exists(alt_path) and alt_path not in library_paths:
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
                if os.path.exists(steamapps_path):
                    for filename in os.listdir(steamapps_path):
                        if filename.startswith("appmanifest_") and filename.endswith(".acf"):
                            acf_path = os.path.join(steamapps_path, filename)
                            try:
                                with open(acf_path, 'r', encoding='utf-8', errors='ignore') as f:
                                    acf_data = vdf.load(f).get('AppState', {})
                                app_id = acf_data.get('appid')
                                name = acf_data.get('name')
                                if app_id and name:
                                    self.installed_games[app_id] = name
                            except Exception: continue
            except Exception: continue
        self.last_update = time.time()

    def search_steam_api(self, search_term):
        try:
            search_term = search_term.strip()
            if not search_term: return []
            encoded_term = urllib.parse.quote(search_term)
            api_url = f"https://store.steampowered.com/api/storesearch/?term={encoded_term}&cc=us&l=en"
            req = urllib.request.Request(api_url)
            req.add_header('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
            with urllib.request.urlopen(req, timeout=5) as response:
                data = json.loads(response.read().decode('utf-8'))
            games = []
            if 'items' in data:
                for item in data['items'][:5]:
                    games.append({
                        'id': item.get('id'),
                        'name': item.get('name', 'Unknown Game'),
                        'platforms': item.get('platforms', {}),
                        'tiny_image': item.get('tiny_image') 
                    })
            return games
        except Exception: return []

    def create_centered_icon(self, image_url, save_path):
        try:
            with urllib.request.urlopen(image_url, timeout=5) as response:
                img_data = response.read()

            original_img = Image.open(BytesIO(img_data))
            
            canvas_size = max(original_img.width, original_img.height)
            canvas = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
            
            x_offset = (canvas_size - original_img.width) // 2
            y_offset = (canvas_size - original_img.height) // 2
            
            canvas.paste(original_img, (x_offset, y_offset))
            
            canvas.save(save_path, "PNG")
            return True
        except Exception:
            return False

    def open_steam_store_page(self, app_id):
        try:
            subprocess.run(['start', f"steam://store/{app_id}"], shell=True, check=True)
            return f"Steam store page opened for App ID: {app_id}"
        except Exception:
            try:
                import webbrowser
                webbrowser.open(f"https://store.steampowered.com/app/{app_id}/")
                return f"Steam store page opened in browser for App ID: {app_id}"
            except Exception as e: return f"Failed to open Steam store page: {str(e)}"

    def safe_print_json(self, data):
        try:
            json_str = json.dumps(data, ensure_ascii=True)
            print(json_str)
            sys.stdout.flush()
        except Exception as e:
            fallback = {"result": [{"Title": "Encoding Error", "SubTitle": f"Failed to encode output: {str(e)}", "IcoPath": "steam.png"}]}
            print(json.dumps(fallback, ensure_ascii=True))
            sys.stdout.flush()

    def query(self, search_term):
        self.update_installed_games()
        results = []
        
        if not search_term:
            return [{"Title": "Steam Game Search", "SubTitle": f"Found {len(self.installed_games)} installed games. Type to search...", "IcoPath": "steam.png"}]
        
        search_lower = search_term.lower()
        
        matching_games = []
        for app_id, name in self.installed_games.items():
            if search_lower in name.lower():
                matching_games.append((app_id, name))
        
        matching_games.sort(key=lambda x: (x[1].lower().find(search_lower), len(x[1])))
        
        for app_id, name in matching_games[:5]:
            results.append({
                "Title": f"🎮 {name}",
                "SubTitle": f"Launch installed game (ID: {app_id})",
                "IcoPath": "steam.png",
                "JsonRPCAction": {"method": "launch_game", "parameters": [app_id]}
            })
        
        api_results = self.search_steam_api(search_term)
        
        for game in api_results:
            app_id = game.get('id')
            name = game.get('name')
            platforms = game.get('platforms', {})
            image_url = game.get('tiny_image')
            
            icon_path = "steam.png"
            if image_url and app_id:
                cached_icon_path = os.path.join(self.cache_dir, f"{app_id}.png")
                if os.path.exists(cached_icon_path):
                    icon_path = cached_icon_path
                else:
                    if self.create_centered_icon(image_url, cached_icon_path):
                        icon_path = cached_icon_path
            
            platform_text = []
            if platforms.get('windows'): platform_text.append('Win')
            if platforms.get('mac'): platform_text.append('Mac')
            if platforms.get('linux'): platform_text.append('Linux')
            platform_str = f" ({'/'.join(platform_text)})" if platform_text else ""
            
            results.append({
                "Title": f"🛒 {name}",
                "SubTitle": f"Open in Steam store{platform_str}",
                "IcoPath": icon_path,
                "JsonRPCAction": {"method": "open_steam_store_page", "parameters": [app_id]}
            })
        
        if not results:
            results.append({
                "Title": f"No games found for '{search_term}'",
                "SubTitle": "Try a different search term",
                "IcoPath": "steam.png"
            })
        
        return results
    
    def launch_game(self, app_id):
        try:
            subprocess.run(['start', f"steam://rungameid/{app_id}"], shell=True)
            return "Game launched"
        except Exception as e: return f"Failed to launch game: {str(e)}"
    
    def open_steam(self):
        try:
            subprocess.run(['start', 'steam://open/main'], shell=True)
            return "Steam opened"
        except:
            if self.steam_path and os.path.exists(os.path.join(self.steam_path, "steam.exe")):
                try: subprocess.run([os.path.join(self.steam_path, "steam.exe")]); return "Steam opened"
                except: pass
            return "Failed to open Steam"

def main():
    plugin = SteamPlugin()
    try:
        input_data = sys.stdin.read() if sys.stdin and not sys.stdin.isatty() else (sys.argv[1] if len(sys.argv) > 1 else '{"method": "query", "parameters": [""]}')
        input_data = input_data.strip()
        if input_data:
            request = json.loads(input_data)
            method, parameters = request.get("method", ""), request.get("parameters", [])
            
            result = None
            if method == "query": result = plugin.query(parameters[0] if parameters else "")
            elif method == "launch_game": result = plugin.launch_game(parameters[0] if parameters else "")
            elif method == "open_steam_store_page": result = plugin.open_steam_store_page(parameters[0] if parameters else "")
            elif method == "search_store_web": 
                import webbrowser
                search_term = parameters[0] if parameters else ""
                if search_term.strip(): 
                    encoded_term = urllib.parse.quote_plus(search_term)
                    webbrowser.open(f"https://store.steampowered.com/search/?term={encoded_term}&ndl=1&cc=us&l=english")
            elif method == "open_steam": result = plugin.open_steam()
            else: result = [{"Title": f"Unknown method: {method}", "SubTitle": f"Parameters: {parameters}", "IcoPath": "steam.png"}]
            
            if result:
                plugin.safe_print_json({"result": result})
        else:
            plugin.safe_print_json({"result": [{"Title": "Steam Plugin Active", "SubTitle": f"Plugin loaded. Steam: {'Found' if plugin.steam_path else 'Not found'}. Games: {len(plugin.installed_games)}", "IcoPath": "steam.png"}]})
    except Exception as e:
        try:
            print(json.dumps({"result": [{"Title": "Steam Plugin Error", "SubTitle": f"Critical error: {str(e)} | Args: {len(sys.argv)}", "IcoPath": "steam.png"}]}, ensure_ascii=True))
            sys.stdout.flush()
        except:
            print('{"result":[{"Title":"Steam Plugin Fatal Error","SubTitle":"Plugin failed to start","IcoPath":"steam.png"}]}')
            sys.stdout.flush()

if __name__ == "__main__":
    main()