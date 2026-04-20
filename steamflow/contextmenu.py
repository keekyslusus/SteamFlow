import json
import time
import urllib.request
from functools import cached_property
from pathlib import Path

from flox import Flox

from .actions import SteamPluginActionsMixin
from .menu import get_game_context_menu_entries, get_steam_client_context_menu_entries

try:
    import winreg
except ImportError:
    import _winreg as winreg

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
UNSET = object()


class SteamContextMenuPlugin(SteamPluginActionsMixin, Flox):
    @cached_property
    def metric_cache_file(self):
        return self.plugin_dir / "cache_metric.json"

    @cached_property
    def app_details_cache(self):
        return self._read_app_details_cache()

    def _read_app_details_cache(self):
        if not self.metric_cache_file.exists():
            return {}
        try:
            with open(self.metric_cache_file, "r", encoding="utf-8") as file_obj:
                cache_data = json.load(file_obj)
            app_details_cache = cache_data.get("app_details_cache", {})
            return app_details_cache if isinstance(app_details_cache, dict) else {}
        except Exception:
            return {}

    def _write_app_details_cache_entry(self, app_id, metadata, success):
        if not app_id:
            return
        cache_data = {}
        if self.metric_cache_file.exists():
            try:
                with open(self.metric_cache_file, "r", encoding="utf-8") as file_obj:
                    loaded = json.load(file_obj)
                if isinstance(loaded, dict):
                    cache_data = loaded
            except Exception:
                cache_data = {}

        app_details_cache = cache_data.get("app_details_cache", {})
        if not isinstance(app_details_cache, dict):
            app_details_cache = {}
        app_details_cache[str(app_id)] = {
            "timestamp": time.time(),
            "success": bool(success),
            "metadata": dict(metadata or {}),
        }
        cache_data["app_details_cache"] = app_details_cache
        try:
            with open(self.metric_cache_file, "w", encoding="utf-8") as file_obj:
                json.dump(cache_data, file_obj)
            self.__dict__["app_details_cache"] = app_details_cache
        except Exception:
            return

    def fetch_app_details_metadata(self, app_id):
        app_id = str(app_id or "").strip()
        if not app_id:
            return None

        try:
            request = urllib.request.Request(
                f"https://store.steampowered.com/api/appdetails?appids={app_id}&l=en",
                headers={"User-Agent": "Mozilla/5.0"},
            )
            with urllib.request.urlopen(request, timeout=0.5) as response:
                data = json.loads(response.read().decode("utf-8"))
            app_details = data.get(app_id, {})
            if not isinstance(app_details, dict) or not app_details.get("success"):
                return None

            details = app_details.get("data", {})
            if not isinstance(details, dict):
                return None

            raw_is_free = details.get("is_free")
            if isinstance(raw_is_free, bool):
                is_free = raw_is_free
            elif raw_is_free in (0, 1):
                is_free = bool(raw_is_free)
            else:
                is_free = None

            return {
                "type": str(details.get("type", "") or "").strip().lower(),
                "is_free": is_free,
                "coming_soon": bool((details.get("release_date") or {}).get("coming_soon")),
            }
        except Exception:
            return None

    def get_cached_app_details_metadata(self, app_id):
        if not app_id:
            return None
        cache_entry = self.app_details_cache.get(str(app_id))
        if not isinstance(cache_entry, dict) or not cache_entry.get("success"):
            return None
        metadata = cache_entry.get("metadata")
        return metadata if isinstance(metadata, dict) else None

    def derive_is_unreleased(self, data):
        if data.get("install_path"):
            return False

        coming_soon = data.get("coming_soon")
        if coming_soon is True:
            return True
        if coming_soon is False:
            return False

        app_id = str(data.get("app_id", "") or "")
        if not app_id:
            return False

        metadata = self.get_cached_app_details_metadata(app_id)
        if not metadata:
            metadata = self.fetch_app_details_metadata(app_id)
            self._write_app_details_cache_entry(app_id, metadata, success=metadata is not None)
        if not metadata:
            return False
        return bool(metadata.get("coming_soon"))

    def derive_refund_state(self, data):
        refund_state = str(data.get("refund_state", "") or "")
        if refund_state:
            return refund_state

        app_id = str(data.get("app_id", "") or "")
        install_path = data.get("install_path")
        if not app_id or not install_path:
            return ""
        if data.get("has_current_account_local_data") is False:
            return ""

        playtime_minutes = data.get("playtime_minutes")
        try:
            playtime_minutes = int(playtime_minutes) if playtime_minutes is not None else None
        except (TypeError, ValueError):
            playtime_minutes = None

        if playtime_minutes is not None and playtime_minutes >= 120:
            return ""

        metadata = self.get_cached_app_details_metadata(app_id)
        if not metadata:
            metadata = self.fetch_app_details_metadata(app_id)
            self._write_app_details_cache_entry(app_id, metadata, success=metadata is not None)
        if not metadata:
            return ""
        if metadata.get("type") != "game" or metadata.get("is_free") is not False:
            return ""

        if playtime_minutes is not None and playtime_minutes < 120:
            return "likely"
        if playtime_minutes is None:
            return "unclear"
        return ""

    def __init__(self):
        super().__init__()
        self.plugin_dir = PACKAGE_ROOT
        self._steam_path = UNSET
        self.community_icon = str(self.plugin_dir / "icons" / "community.png")
        self.default_icon = str(self.plugin_dir / "icons" / "steam.png")
        self.discussions_icon = str(self.plugin_dir / "icons" / "discussions.png")
        self.download_icon = str(self.plugin_dir / "icons" / "download.png")
        self.guides_icon = str(self.plugin_dir / "icons" / "guides.png")
        self.location_icon = str(self.plugin_dir / "icons" / "location.png")
        self.properties_icon = str(self.plugin_dir / "icons" / "properties.png")
        self.refund_icon = str(self.plugin_dir / "icons" / "refund.png")
        self.screenshot_icon = str(self.plugin_dir / "icons" / "screenshot.png")
        self.settings_icon = str(self.plugin_dir / "icons" / "settings.png")
        self.steamdb_icon = str(self.plugin_dir / "icons" / "steamdb.png")
        self.trash_icon = str(self.plugin_dir / "icons" / "trash.png")

    @cached_property
    def logfile(self):
        return str(self.plugin_dir / "plugin_steamflow.log")

    @property
    def steam_path(self):
        if self._steam_path is UNSET:
            self._steam_path = self._find_steam_path()
        return self._steam_path

    def _find_steam_path(self):
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

    def _add_menu_entries(self, entries):
        for entry in entries:
            self.add_item(
                title=entry["title"],
                subtitle=entry["subtitle"],
                icon=entry["icon"],
                method=entry["method"],
                parameters=entry.get("parameters"),
            )

    def context_menu(self, data):
        if not isinstance(data, dict):
            return

        if data.get("menu") == "steam_client":
            self._add_menu_entries(
                get_steam_client_context_menu_entries(
                    self.default_icon,
                    self.settings_icon,
                    self.community_icon,
                )
            )
            return

        app_id = str(data.get("app_id", ""))
        name = data.get("name", "Game")
        install_path = data.get("install_path")
        is_owned = bool(data.get("is_owned"))
        refund_state = self.derive_refund_state(data)
        is_unreleased = self.derive_is_unreleased(data)

        self._add_menu_entries(
            get_game_context_menu_entries(
                app_id,
                name,
                install_path,
                is_owned,
                refund_state,
                self.default_icon,
                self.steamdb_icon,
                self.guides_icon,
                self.discussions_icon,
                self.screenshot_icon,
                self.refund_icon,
                self.properties_icon,
                self.location_icon,
                self.download_icon,
                self.trash_icon,
                is_unreleased=is_unreleased,
            )
        )
