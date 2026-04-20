import os
import subprocess
import webbrowser
from pathlib import Path


class SteamPluginActionsMixin:
    STEAM_GAMES_URI = "steam://nav/games"
    STEAM_FRIENDS_STATUS_URIS = {
        "online": "steam://friends/status/online",
        "offline": "steam://friends/status/offline",
        "invisible": "steam://friends/status/invisible",
    }

    def _log_action_error(self, message):
        log_method = getattr(self, "log", None)
        if callable(log_method):
            log_method("error", message)

    def _log_action_exception(self, message):
        log_exception = getattr(self, "log_exception", None)
        if callable(log_exception):
            log_exception(message)

    def open_steam_store_page(self, app_id):
        uri = f"steam://store/{app_id}"
        try:
            os.startfile(uri)
            return f"Steam store page opened for App ID: {app_id}"
        except Exception:
            try:
                webbrowser.open(f"https://store.steampowered.com/app/{app_id}/")
                return f"Steam store page opened in browser for App ID: {app_id}"
            except Exception as error:
                self._log_action_error(f"Failed to open Steam store page for app {app_id}: {error}")
                return f"Failed to open Steam store page: {str(error)}"

    def open_steam_guides_page(self, app_id):
        uri = f"steam://openurl/https://steamcommunity.com/app/{app_id}/guides/"
        try:
            os.startfile(uri)
            return f"Steam guides opened for App ID: {app_id}"
        except Exception as error:
            self._log_action_error(f"Failed to open Steam guides for app {app_id}: {error}")
            return f"Failed to open Steam guides: {str(error)}"

    def open_steam_discussions_page(self, app_id):
        uri = f"steam://openurl/https://steamcommunity.com/app/{app_id}/discussions/"
        try:
            os.startfile(uri)
            return f"Steam discussions opened for App ID: {app_id}"
        except Exception as error:
            self._log_action_error(f"Failed to open Steam discussions for app {app_id}: {error}")
            return f"Failed to open Steam discussions: {str(error)}"

    def open_steam_game_properties_page(self, app_id):
        uri = f"steam://gameproperties/{app_id}"
        try:
            os.startfile(uri)
            return f"Steam game properties opened for App ID: {app_id}"
        except Exception as error:
            self._log_action_error(f"Failed to open Steam game properties for app {app_id}: {error}")
            return f"Failed to open Steam game properties: {str(error)}"

    def open_steam_screenshots_page(self, app_id):
        uri = f"steam://open/screenshots/{app_id}"
        try:
            os.startfile(uri)
            return f"Steam recordings and screenshots opened for App ID: {app_id}"
        except Exception as error:
            self._log_action_error(f"Failed to open Steam recordings and screenshots for app {app_id}: {error}")
            return f"Failed to open Steam recordings and screenshots: {str(error)}"

    def open_steam_refund_page(self, app_id):
        uri = f"steam://openurl/https://help.steampowered.com/en/wizard/HelpWithGameIssue/?appid={app_id}&issueid=108"
        try:
            os.startfile(uri)
            return f"Steam refund page opened for App ID: {app_id}"
        except Exception as error:
            self._log_action_error(f"Failed to open Steam refund page for app {app_id}: {error}")
            return f"Failed to open Steam refund page: {str(error)}"

    def open_steam(self):
        try:
            os.startfile(self.STEAM_GAMES_URI)
            return "Steam opened"
        except Exception:
            ensure_startup_initialized = getattr(self, "ensure_startup_initialized", None)
            startup_initialized = getattr(self, "startup_initialized", False)
            if callable(ensure_startup_initialized) and not startup_initialized:
                ensure_startup_initialized()

            steam_path = getattr(self, "steam_path", None)
            if steam_path:
                steam_exe = Path(steam_path) / "steam.exe"
                if steam_exe.exists():
                    try:
                        subprocess.run([str(steam_exe)])
                        return "Steam opened"
                    except Exception:
                        self._log_action_exception("Failed to launch steam.exe directly")
            return "Failed to open Steam"

    def open_steam_settings(self):
        try:
            os.startfile("steam://open/settings")
            return "Steam settings opened"
        except Exception as error:
            self._log_action_error(f"Failed to open Steam settings: {error}")
            return f"Failed to open Steam settings: {str(error)}"

    def open_steam_friends(self):
        try:
            os.startfile("steam://open/friends")
            return "Steam friends opened"
        except Exception as error:
            self._log_action_error(f"Failed to open Steam friends: {error}")
            return f"Failed to open Steam friends: {str(error)}"

    def set_steam_friends_status(self, status):
        normalized_status = str(status or "").strip().lower()
        uri = self.STEAM_FRIENDS_STATUS_URIS.get(normalized_status)
        if not uri:
            return f"Invalid Steam status: {status}"

        try:
            os.startfile(uri)
            change_query = getattr(self, "change_query", None)
            if callable(change_query):
                try:
                    build_plugin_query = getattr(self, "build_plugin_query", None)
                    plugin_home_query = build_plugin_query() if callable(build_plugin_query) else ""
                    change_query(plugin_home_query, True)
                except Exception:
                    self._log_action_exception("Failed to reset launcher query after changing Steam status")
            return f"Steam status set to {normalized_status.title()}"
        except Exception as error:
            self._log_action_error(f"Failed to set Steam friends status to {normalized_status}: {error}")
            return f"Failed to set Steam status: {str(error)}"

    def open_steam_library_game_details(self, app_id):
        uri = f"steam://nav/games/details/{app_id}"
        try:
            os.startfile(uri)
            return f"Steam library details opened for App ID: {app_id}"
        except Exception as error:
            self._log_action_error(f"Failed to open Steam library details for app {app_id}: {error}")
            return f"Failed to open Steam library details: {str(error)}"

    def open_my_steam_wishlist(self):
        uri = "steam://openurl/https://steamcommunity.com/my/wishlist/"
        try:
            os.startfile(uri)
            return "Steam wishlist opened"
        except Exception:
            try:
                webbrowser.open("https://steamcommunity.com/my/wishlist/")
                return "Steam wishlist opened in browser"
            except Exception as error:
                self._log_action_error(f"Failed to open Steam wishlist: {error}")
                return f"Failed to open Steam wishlist: {str(error)}"

    def install_steam_game(self, app_id):
        try:
            os.startfile(f"steam://install/{app_id}")
            schedule_refresh = getattr(self, "schedule_installed_games_refresh", None)
            if callable(schedule_refresh):
                schedule_refresh(delay_seconds=2)
            return f"Steam install opened for App ID: {app_id}"
        except Exception as error:
            self._log_action_error(f"Failed to install Steam game {app_id}: {error}")
            return f"Failed to install Steam game: {str(error)}"

    def uninstall_steam_game(self, app_id):
        try:
            os.startfile(f"steam://uninstall/{app_id}")
            schedule_refresh = getattr(self, "schedule_installed_games_refresh", None)
            if callable(schedule_refresh):
                schedule_refresh(delay_seconds=2)
            return f"Steam uninstall opened for App ID: {app_id}"
        except Exception as error:
            self._log_action_error(f"Failed to uninstall Steam game {app_id}: {error}")
            return f"Failed to uninstall Steam game: {str(error)}"

    def open_local_files(self, install_path):
        try:
            if install_path and Path(install_path).exists():
                os.startfile(install_path)
                return "Local files opened"
            return "Local files folder not found"
        except Exception as error:
            self._log_action_error(f"Failed to open local files '{install_path}': {error}")
            return f"Failed to open local files: {str(error)}"

    def open_steamdb_page(self, app_id):
        try:
            webbrowser.open(f"https://steamdb.info/app/{app_id}/")
            return f"SteamDB page opened for App ID: {app_id}"
        except Exception as error:
            self._log_action_error(f"Failed to open SteamDB page for app {app_id}: {error}")
            return f"Failed to open SteamDB page: {str(error)}"
