import json
import os
import tempfile
import time
from pathlib import Path


def is_timestamp_fresh(timestamp, ttl_seconds):
    try:
        timestamp_value = float(timestamp or 0)
    except (TypeError, ValueError):
        return False
    if timestamp_value <= 0:
        return False
    return (time.time() - timestamp_value) < float(ttl_seconds or 0)


def read_json_file(path, default=None, logger=None, error_message=None):
    try:
        with open(path, "r", encoding="utf-8") as file_obj:
            return json.load(file_obj)
    except Exception:
        if logger and error_message:
            logger(error_message)
        return default


def write_json_file(path, payload, logger=None, error_message=None, indent=None):
    path = Path(path)
    temp_path = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as file_obj:
            temp_path = file_obj.name
            json.dump(payload, file_obj, indent=indent)
            file_obj.flush()
            os.fsync(file_obj.fileno())
        os.replace(temp_path, path)
        return True
    except Exception:
        if logger and error_message:
            logger(error_message)
        return False
    finally:
        if temp_path:
            try:
                os.unlink(temp_path)
            except OSError:
                pass


def build_timestamped_cache_entry(payload=None, now=None):
    return {
        "timestamp": time.time() if now is None else float(now),
        **dict(payload or {}),
    }


def update_timestamped_cache_entry(cache, key, payload=None, now=None):
    if key is None:
        return False
    cache[str(key)] = build_timestamped_cache_entry(payload, now=now)
    return True


def get_timestamped_cache_entry_state(cache, key, ttl_seconds):
    cached_entry = cache.get(str(key))
    if not cached_entry:
        return None, False
    return cached_entry, is_timestamp_fresh(cached_entry.get("timestamp", 0), ttl_seconds)


def cleanup_timestamped_cache_entries(cache, ttl_seconds, now=None):
    now = time.time() if now is None else float(now)
    expired_keys = [
        key
        for key, value in cache.items()
        if now - value.get("timestamp", 0) >= ttl_seconds
    ]
    for key in expired_keys:
        cache.pop(key, None)
    return bool(expired_keys)


def cleanup_app_details_cache_entries(cache, success_ttl_seconds, failure_ttl_seconds, now=None):
    now = time.time() if now is None else float(now)
    expired_keys = []
    for key, value in cache.items():
        ttl_seconds = success_ttl_seconds if value.get("success") else failure_ttl_seconds
        if now - value.get("timestamp", 0) >= ttl_seconds:
            expired_keys.append(key)

    for key in expired_keys:
        cache.pop(key, None)
    return bool(expired_keys)
