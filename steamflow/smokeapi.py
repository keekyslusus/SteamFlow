import ctypes
import threading
from pathlib import Path

from .hooks import log_exception_if_supported, log_if_supported, show_message_if_supported
from .localization import plugin_tr
from .smoke_safety import (
    INSTALL_RESCAN_TTL_SECONDS,
    get_cached_safety,
    invalidate_safety_cache,
    scan_and_cache_safety,
)
from .smoke_state_cache import (
    detect_and_cache_smokeapi_action,
    get_cached_smokeapi_action,
    invalidate_smokeapi_state_cache,
)
from .smokeapi_service import (
    DEFAULT_PAYLOAD_DIR,
    install_smokeapi as install_smokeapi_files,
    remove_smokeapi as remove_smokeapi_files,
)
from .smokeapi_payload_service import (
    download_smokeapi_payload,
    inspect_smokeapi_payload,
)


_SCAN_LOCK = threading.Lock()
_PENDING_SCANS = set()
_WARMING_CACHES = set()
MESSAGE_BOX_YES = 6
MB_YESNO = 0x00000004
MB_ICONWARNING = 0x00000030
MB_DEFBUTTON2 = 0x00000100
MB_TOPMOST = 0x00040000


def show_yes_no_dialog(title, body):
    try:
        result = ctypes.windll.user32.MessageBoxW(
            None,
            str(body),
            str(title),
            MB_YESNO | MB_ICONWARNING | MB_DEFBUTTON2 | MB_TOPMOST,
        )
    except Exception:
        return False
    return result == MESSAGE_BOX_YES


class SteamPluginSmokeAPIMixin:
    def should_show_smokeapi_context_menu(self):
        get_setting_bool = getattr(self, "get_setting_bool", None)
        if callable(get_setting_bool):
            return bool(get_setting_bool("enable_smokeapi_context_menu", False))
        settings = getattr(self, "settings", {})
        return bool(settings.get("enable_smokeapi_context_menu", False))

    def get_smokeapi_payload_dir(self):
        plugin_dir = Path(getattr(self, "plugin_dir", DEFAULT_PAYLOAD_DIR.parent.parent))
        return plugin_dir / "resources" / "smokeapi"

    def get_smoke_safety_cache_file(self):
        configured = getattr(self, "smoke_safety_cache_file", None)
        if configured:
            return Path(configured)
        return Path(getattr(self, "plugin_dir", Path.cwd())) / "cache_smoke_safety.json"

    def get_smokeapi_state_cache_file(self):
        configured = getattr(self, "smokeapi_state_cache_file", None)
        if configured:
            return Path(configured)
        return Path(getattr(self, "plugin_dir", Path.cwd())) / "cache_smoke_state.json"

    def _run_smoke_safety_scan(self, app_id, install_path):
        cache_file = self.get_smoke_safety_cache_file()
        key = (str(cache_file), str(app_id), str(install_path))
        try:
            scan_and_cache_safety(cache_file, app_id, install_path)
        except Exception:
            log_exception_if_supported(self, "Failed to scan game folder for anti-cheat markers")
        finally:
            with _SCAN_LOCK:
                _PENDING_SCANS.discard(key)

    def schedule_smoke_safety_scan(self, app_id, install_path):
        if not app_id or not install_path or not Path(install_path).is_dir():
            return False
        cache_file = self.get_smoke_safety_cache_file()
        key = (str(cache_file), str(app_id), str(install_path))
        with _SCAN_LOCK:
            if key in _PENDING_SCANS:
                return False
            _PENDING_SCANS.add(key)

        start_task = getattr(self, "start_daemon_task", None)
        if callable(start_task):
            start_task(self._run_smoke_safety_scan, str(app_id), str(install_path))
        else:
            thread = threading.Thread(
                target=self._run_smoke_safety_scan,
                args=(str(app_id), str(install_path)),
                daemon=False,
            )
            thread.start()
        return True

    def _run_smoke_safety_warm(self, cache_key, stale_entries):
        try:
            for app_id, install_path in stale_entries:
                scan_key = (cache_key, str(app_id), str(install_path))
                with _SCAN_LOCK:
                    if scan_key in _PENDING_SCANS:
                        continue
                    _PENDING_SCANS.add(scan_key)
                self._run_smoke_safety_scan(app_id, install_path)
        finally:
            with _SCAN_LOCK:
                _WARMING_CACHES.discard(cache_key)

    def warm_smoke_safety_cache(self, installed_game_paths=None):
        if not self.should_show_smokeapi_context_menu():
            return
        paths = installed_game_paths
        if paths is None:
            paths = getattr(self, "installed_game_paths", {})
        cache_file = self.get_smoke_safety_cache_file()
        stale_entries = []
        for app_id, install_path in dict(paths or {}).items():
            if get_cached_safety(
                cache_file,
                app_id,
                install_path,
            ) is None:
                stale_entries.append((str(app_id), str(install_path)))
        if not stale_entries:
            return

        cache_key = str(cache_file)
        with _SCAN_LOCK:
            if cache_key in _WARMING_CACHES:
                return
            _WARMING_CACHES.add(cache_key)
        start_task = getattr(self, "start_daemon_task", None)
        if callable(start_task):
            start_task(self._run_smoke_safety_warm, cache_key, tuple(stale_entries))
        else:
            threading.Thread(
                target=self._run_smoke_safety_warm,
                args=(cache_key, tuple(stale_entries)),
                daemon=True,
            ).start()

    def get_smokeapi_menu_state(self, app_id, install_path):
        if not self.should_show_smokeapi_context_menu() or not app_id or not install_path:
            return {"action": "", "safety": "", "signals": ()}
        if not Path(install_path).is_dir():
            return {"action": "", "safety": "", "signals": ()}

        payload_dir = self.get_smokeapi_payload_dir()
        action = get_cached_smokeapi_action(
            self.get_smokeapi_state_cache_file(),
            app_id,
            install_path,
            payload_dir,
        )
        if action is None:
            action = detect_and_cache_smokeapi_action(
                self.get_smokeapi_state_cache_file(),
                app_id,
                install_path,
                payload_dir,
            )
        if not action:
            return {"action": "", "safety": "", "signals": ()}
        if action == "remove":
            return {"action": "remove", "safety": "", "signals": ()}

        safety = get_cached_safety(
            self.get_smoke_safety_cache_file(),
            app_id,
            install_path,
        )
        if safety is None:
            self.schedule_smoke_safety_scan(app_id, install_path)
            return {"action": "install", "safety": "checking", "signals": ()}
        return {
            "action": "install",
            "safety": "risk" if safety.risk else "clean",
            "signals": safety.signals,
        }

    def _confirm_smokeapi(self, title_key, body_key, **values):
        title = plugin_tr(self, title_key)
        body = plugin_tr(self, body_key, **values)
        return show_yes_no_dialog(title, body)

    def _show_smoke_message(self, title_key, body_key, **values):
        title = plugin_tr(self, title_key)
        body = plugin_tr(self, body_key, **values)
        icon = str(getattr(self, "PROPERTIES_ICON", getattr(self, "properties_icon", "")))
        show_message_if_supported(self, title, body, icon)
        return body

    def _refresh_smokeapi_ui_state(self, app_id):
        invalidate_safety_cache(self.get_smoke_safety_cache_file(), app_id)
        invalidate_smokeapi_state_cache(self.get_smokeapi_state_cache_file(), app_id)
        context_cache = getattr(self, "context_menu_cache", None)
        if isinstance(context_cache, dict):
            context_cache.clear()

    def install_smokeapi(self, app_id, install_path, name="Game"):
        app_id = str(app_id or "").strip()
        install_path = str(install_path or "").strip()
        if not app_id or not install_path or not Path(install_path).is_dir():
            return self._show_smoke_message(
                "smoke.toast.error.title",
                "smoke.toast.install_path_missing",
            )

        payload_dir = self.get_smokeapi_payload_dir()
        payload_status = inspect_smokeapi_payload(payload_dir)
        if not payload_status.ready:
            if not self._confirm_smokeapi(
                "smoke.confirm.download.title",
                "smoke.confirm.download.body",
            ):
                return plugin_tr(self, "smoke.toast.cancelled")
            download_result = download_smokeapi_payload(payload_dir)
            if not download_result.success:
                log_if_supported(
                    self,
                    "error",
                    "SmokeAPI payload download failed: "
                    + "; ".join(download_result.errors),
                )
                return self._show_smoke_message(
                    "smoke.toast.error.title",
                    "smoke.toast.download_failed",
                )

        try:
            safety = get_cached_safety(
                self.get_smoke_safety_cache_file(),
                app_id,
                install_path,
                ttl_seconds=INSTALL_RESCAN_TTL_SECONDS,
            )
            if safety is None:
                safety = scan_and_cache_safety(
                    self.get_smoke_safety_cache_file(),
                    app_id,
                    install_path,
                )
        except Exception:
            log_exception_if_supported(self, "Failed to scan game folder before SmokeAPI install")
            return self._show_smoke_message(
                "smoke.toast.error.title",
                "smoke.toast.safety_scan_failed",
            )

        body_key = "smoke.confirm.install.body_ac" if safety.risk else "smoke.confirm.install.body"
        signals = ", ".join(safety.signals)
        if not self._confirm_smokeapi(
            "smoke.confirm.install.title",
            body_key,
            name=name,
            signals=signals,
        ):
            return plugin_tr(self, "smoke.toast.cancelled")

        result = install_smokeapi_files(
            install_path,
            payload_dir=payload_dir,
        )
        self._refresh_smokeapi_ui_state(app_id)
        if result.success:
            return self._show_smoke_message(
                "smoke.toast.success.title",
                "smoke.toast.install_success",
                count=result.changed_dlls,
            )
        if any(error.startswith("payload_missing:") for error in result.errors):
            return self._show_smoke_message(
                "smoke.toast.error.title",
                "smoke.toast.payload_missing",
            )
        if result.partial:
            return self._show_smoke_message(
                "smoke.toast.error.title",
                "smoke.toast.install_partial",
                successful=result.successful_directories,
                total=result.total_directories,
            )
        return self._show_smoke_message(
            "smoke.toast.error.title",
            "smoke.toast.install_failed",
        )

    def remove_smokeapi(self, app_id, install_path, name="Game"):
        app_id = str(app_id or "").strip()
        install_path = str(install_path or "").strip()
        if not app_id or not install_path or not Path(install_path).is_dir():
            return self._show_smoke_message(
                "smoke.toast.error.title",
                "smoke.toast.install_path_missing",
            )
        if not self._confirm_smokeapi(
            "smoke.confirm.remove.title",
            "smoke.confirm.remove.body",
            name=name,
        ):
            return plugin_tr(self, "smoke.toast.cancelled")

        result = remove_smokeapi_files(
            install_path,
            payload_dir=self.get_smokeapi_payload_dir(),
        )
        self._refresh_smokeapi_ui_state(app_id)
        if result.success:
            return self._show_smoke_message(
                "smoke.toast.success.title",
                "smoke.toast.remove_success",
                count=result.changed_dlls,
            )
        if result.backup_missing:
            return self._show_smoke_message(
                "smoke.toast.error.title",
                "smoke.toast.backup_missing",
            )
        if result.partial:
            return self._show_smoke_message(
                "smoke.toast.error.title",
                "smoke.toast.remove_partial",
                successful=result.successful_directories,
                total=result.total_directories,
            )
        return self._show_smoke_message(
            "smoke.toast.error.title",
            "smoke.toast.remove_failed",
        )
