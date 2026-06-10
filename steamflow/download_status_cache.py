import time

from .cache_utils import read_json_file, write_json_file
from .constants import STEAMFLOW_CONFIG


def get_download_control_hint_label(action, config=STEAMFLOW_CONFIG):
    return {
        "pause": config.download.status_update_paused,
        "resume": config.download.status_updating,
    }.get(str(action or "").strip().lower(), "")


def set_download_control_status_hint(cache_file, app_id, action, now=None, config=STEAMFLOW_CONFIG):
    app_id = str(app_id or "").strip()
    hint_label = get_download_control_hint_label(action, config=config)
    if not cache_file or not app_id or not hint_label:
        return False

    cache_data = read_json_file(cache_file, default={})
    if not isinstance(cache_data, dict):
        cache_data = {}
    progress_entry = cache_data.get(app_id)
    if not isinstance(progress_entry, dict):
        progress_entry = {}
    progress_entry["hint_label"] = hint_label
    progress_entry["hint_until"] = (time.time() if now is None else float(now)) + config.download.status_hint_seconds
    cache_data[app_id] = progress_entry
    return write_json_file(cache_file, cache_data)
