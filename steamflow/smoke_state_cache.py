import json
import os
import threading
import time
from pathlib import Path

from .smokeapi_service import API_FILES, detect_smokeapi_state


SMOKE_STATE_TTL_SECONDS = 5 * 60
_CACHE_LOCK = threading.Lock()


def _path_signature(path):
    try:
        stat_result = Path(path).stat()
    except OSError:
        return ()
    return (int(stat_result.st_mtime_ns), int(stat_result.st_size))


def _payload_signature(payload_dir):
    root = Path(payload_dir)
    signature = []
    for filename, _backup_name in API_FILES:
        try:
            stat_result = (root / filename).stat()
            signature.append((filename, int(stat_result.st_mtime_ns), int(stat_result.st_size)))
        except OSError:
            signature.append((filename, 0, 0))
    return tuple(signature)


def _load_cache(cache_file):
    try:
        data = json.loads(Path(cache_file).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _save_cache(cache_file, cache):
    path = Path(cache_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(
        path.suffix + f".{os.getpid()}.{threading.get_ident()}.tmp"
    )
    try:
        temporary_path.write_text(
            json.dumps(cache, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary_path.replace(path)
    finally:
        if temporary_path.exists():
            try:
                temporary_path.unlink()
            except OSError:
                pass


def get_cached_smokeapi_action(
    cache_file,
    app_id,
    install_path,
    payload_dir,
    ttl_seconds=SMOKE_STATE_TTL_SECONDS,
    now=None,
):
    current_time = float(time.time() if now is None else now)
    with _CACHE_LOCK:
        entry = _load_cache(cache_file).get(str(app_id))
    if not isinstance(entry, dict):
        return None
    if str(entry.get("install_path", "")) != str(Path(install_path)):
        return None
    if tuple(entry.get("path_sig", ())) != _path_signature(install_path):
        return None
    cached_payload_sig = tuple(
        tuple(item) for item in entry.get("payload_sig", ()) if isinstance(item, list)
    )
    if cached_payload_sig != _payload_signature(payload_dir):
        return None
    try:
        scanned_at = float(entry.get("scanned_at", 0))
    except (TypeError, ValueError):
        return None
    if scanned_at <= 0 or (current_time - scanned_at) > ttl_seconds:
        return None
    action = str(entry.get("action", ""))
    return action if action in {"", "install", "remove"} else None


def detect_and_cache_smokeapi_action(
    cache_file,
    app_id,
    install_path,
    payload_dir,
    now=None,
):
    state = detect_smokeapi_state(install_path, payload_dir=payload_dir)
    scanned_at = float(time.time() if now is None else now)
    with _CACHE_LOCK:
        cache = _load_cache(cache_file)
        cache[str(app_id)] = {
            "install_path": str(Path(install_path)),
            "path_sig": list(_path_signature(install_path)),
            "payload_sig": [list(item) for item in _payload_signature(payload_dir)],
            "action": state.action,
            "scanned_at": scanned_at,
        }
        _save_cache(cache_file, cache)
    return state.action


def invalidate_smokeapi_state_cache(cache_file, app_id):
    with _CACHE_LOCK:
        cache = _load_cache(cache_file)
        if cache.pop(str(app_id), None) is not None:
            _save_cache(cache_file, cache)
