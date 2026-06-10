import json
import logging
import logging.handlers
from functools import cached_property
from pathlib import Path

from pyflowlauncher import Plugin
from pyflowlauncher import api


class Settings(dict):
    def __init__(self, filepath):
        super().__init__()
        self.filepath = Path(filepath)
        if self.filepath.exists():
            try:
                self.update(json.loads(self.filepath.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError):
                pass


class SteamFlowPluginBase(Plugin):
    """compatibility layer for the plugin's existing integration helpers."""

    def __init__(self):
        super().__init__()
        self._results = []
        self.rpc_request = self._client.recieve()
        self._settings = self.rpc_request.get("settings")

    @cached_property
    def plugindir(self):
        return str(self.root_dir)

    @cached_property
    def id(self):
        return self.manifest.id

    @cached_property
    def icon(self):
        return self.manifest.ico_path

    @cached_property
    def action_keyword(self):
        return self.manifest.action_keyword

    @cached_property
    def appdata(self):
        return str(Path(self.plugindir).parent.parent)

    @property
    def app_settings(self):
        path = Path(self.appdata) / "Settings" / "Settings.json"
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    @cached_property
    def user_keyword(self):
        plugin_settings = self.app_settings.get("PluginSettings", {}).get("Plugins", {}).get(self.id, {})
        keywords = plugin_settings.get("UserKeywords", [self.action_keyword])
        return str(keywords[0] if keywords else self.action_keyword)

    @cached_property
    def settings_path(self):
        return str(Path(self.appdata) / "Settings" / "Plugins" / self.manifest.name / "Settings.json")

    @property
    def settings(self):
        if self._settings is not None:
            return self._settings
        return Settings(self.settings_path)

    @cached_property
    def logger(self):
        logger = logging.getLogger(f"steamflow.{self.id}")
        if not logger.handlers:
            handler = logging.handlers.RotatingFileHandler(
                self.logfile,
                maxBytes=1024 * 2024,
                backupCount=1,
            )
            handler.setFormatter(
                logging.Formatter(
                    "%(asctime)s %(levelname)s (%(filename)s): %(message)s",
                    datefmt="%H:%M:%S",
                )
            )
            logger.addHandler(handler)
        logger.setLevel(logging.WARNING)
        return logger

    def logger_level(self, level):
        self.logger.setLevel(getattr(logging, str(level).upper(), logging.WARNING))

    def add_item(
        self,
        title,
        subtitle="",
        icon=None,
        method=None,
        parameters=None,
        context=None,
        score=0,
        **kwargs,
    ):
        item = {
            "Title": str(title),
            "SubTitle": str(subtitle),
            "IcoPath": str(icon or self.icon),
            "ContextData": context,
            "Score": score,
        }
        if method:
            item["JsonRPCAction"] = {
                "method": getattr(method, "__name__", method),
                "parameters": parameters or [],
                "dontHideAfterAction": kwargs.pop("dont_hide", False),
            }
        item.update(kwargs)
        self._results.append(item)
        return item

    def change_query(self, query, requery=False):
        self._client.send(api.change_query(query, requery))

    def show_msg(self, title, subtitle, ico_path=""):
        self._client.send(api.show_msg(title, subtitle, ico_path))

    def run(self):
        request_method = self.rpc_request.get("method") or self.rpc_request.get("Method") or "query"
        parameters = self.rpc_request.get("parameters")
        if parameters is None:
            parameters = self.rpc_request.get("Parameters", [])
        try:
            method = getattr(self, request_method)
            result = method(*parameters)
        except Exception as error:
            try:
                self.logger.exception("Unhandled SteamFlow request method '%s'", request_method)
                self.show_msg("SteamFlow Error", str(error) or f"Failed to run {request_method}", self.icon)
            except Exception:
                pass
            return
        if request_method in {"query", "context_menu"}:
            self._client.send({"Result": result or self._results})
