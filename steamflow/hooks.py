from pathlib import Path
import threading
import time


def _get_callable(plugin, method_name):
    method = getattr(plugin, method_name, None)
    return method if callable(method) else None


def log_if_supported(plugin, level, message):
    log_method = _get_callable(plugin, "log")
    if log_method:
        log_method(level, message)


def log_exception_if_supported(plugin, message):
    log_exception = _get_callable(plugin, "log_exception")
    if log_exception:
        log_exception(message)


def get_secure_settings_dir(plugin):
    secure_settings_dir = getattr(plugin, "secure_settings_dir", None)
    if secure_settings_dir is not None:
        return Path(secure_settings_dir)
    return Path(plugin.settings_path).parent


def ensure_startup_initialized_if_needed(plugin):
    ensure_startup_initialized = _get_callable(plugin, "ensure_startup_initialized")
    startup_initialized = bool(getattr(plugin, "startup_initialized", False))
    if ensure_startup_initialized and not startup_initialized:
        ensure_startup_initialized()


def schedule_installed_games_refresh_if_supported(plugin, delay_seconds=0, reset_user_paths=False):
    schedule_refresh = _get_callable(plugin, "schedule_installed_games_refresh")
    if schedule_refresh:
        schedule_refresh(delay_seconds=delay_seconds, reset_user_paths=reset_user_paths)


def reset_plugin_query_if_supported(plugin):
    change_query = _get_callable(plugin, "change_query")
    if not change_query:
        return
    build_plugin_query = _get_callable(plugin, "build_plugin_query")
    plugin_home_query = build_plugin_query() if build_plugin_query else ""
    change_query(plugin_home_query, True)


def schedule_plugin_query_reset_if_supported(plugin, delay_seconds=0):
    if not _get_callable(plugin, "change_query"):
        return None

    def worker():
        if delay_seconds > 0:
            time.sleep(delay_seconds)
        try:
            reset_plugin_query_if_supported(plugin)
        except Exception:
            pass

    thread = threading.Thread(target=worker, daemon=False)
    thread.start()
    return thread


def show_message_if_supported(plugin, title, subtitle, icon_path=""):
    show_msg = _get_callable(plugin, "show_msg")
    if show_msg:
        show_msg(title, subtitle, icon_path)


def get_download_control_action_for_status_or_empty(plugin, status_label):
    get_download_control_action = _get_callable(plugin, "get_download_control_action_for_status")
    if not get_download_control_action:
        return ""
    return str(get_download_control_action(status_label) or "")


def get_live_local_game_status_or_fallback(plugin, app_id, fallback_status=""):
    get_live_status = _get_callable(plugin, "get_live_local_game_status")
    if not get_live_status:
        return str(fallback_status or "")
    return str(get_live_status(app_id, fallback_status) or fallback_status or "")
