import subprocess
import sys
import time
from pathlib import Path

from .http_client import http_get_json
from .os_integration import build_hidden_process_kwargs, start_hidden_process

WISHLIST_WORKER_STALE_SECONDS = 15 * 60


def _coerce_float(value, default=0.0):
    try:
        return float(value or default)
    except (TypeError, ValueError):
        return float(default)


def _coerce_int(value, default=0):
    try:
        return int(value or default)
    except (TypeError, ValueError):
        return int(default)


def normalize_wishlist_items(items):
    normalized_items = []
    if not isinstance(items, list):
        return normalized_items

    for item in items:
        if not isinstance(item, dict):
            continue
        app_id = str(item.get("appid", "")).strip()
        if not app_id:
            continue
        normalized_items.append(
            {
                "appid": app_id,
                "date_added": _coerce_int(item.get("date_added", 0)),
                "priority": _coerce_int(item.get("priority", 0)),
            }
        )
    return normalized_items


def build_wishlist_url(api_key, steamid64):
    return f"https://api.steampowered.com/IWishlistService/GetWishlist/v1/?key={api_key}&steamid={steamid64}"


def parse_wishlist_payload(payload):
    items = payload.get("response", {}).get("items", [])
    if not isinstance(items, list):
        return []
    return normalize_wishlist_items(items)


def fetch_wishlist_items(api_key, steamid64, http_get, normalize_api_key=None, timeout=3):
    normalized_key = normalize_api_key(api_key) if normalize_api_key else str(api_key or "").strip()
    normalized_steamid64 = str(steamid64 or "").strip()
    if not normalized_key or not normalized_steamid64:
        raise ValueError("Missing Steam API credentials")

    payload = http_get_json(
        http_get,
        build_wishlist_url(normalized_key, normalized_steamid64),
        timeout=timeout,
    )
    return parse_wishlist_payload(payload)


def fetch_wishlist_result(fetch_wishlist_items_from_api, api_key, steamid64, timeout=3):
    try:
        return {
            "success": True,
            "items": fetch_wishlist_items_from_api(api_key, steamid64, timeout=timeout),
            "error": None,
        }
    except Exception as error:
        return {
            "success": False,
            "items": [],
            "error": error,
        }


def get_wishlist_fetch_error_message(error):
    error_message = str(error or "").strip()
    return error_message or "Steam wishlist request failed"


def normalize_wishlist_cache_payload(cache_data):
    if not isinstance(cache_data, dict):
        return None
    return {
        "last_attempt": _coerce_float(cache_data.get("last_attempt", 0)),
        "last_sync": _coerce_float(cache_data.get("timestamp", 0)),
        "steamid64": str(cache_data.get("steamid64", "") or "") or None,
        "items": normalize_wishlist_items(cache_data.get("items", [])),
    }


def build_wishlist_cache_payload(last_attempt, last_sync, steamid64, items):
    return {
        "last_attempt": last_attempt,
        "timestamp": last_sync,
        "steamid64": steamid64,
        "items": list(items),
    }


def is_wishlist_cache_fresh(steamid64, cached_steamid64, last_sync, ttl_seconds, is_fresh):
    return bool(
        steamid64
        and str(cached_steamid64 or "") == str(steamid64 or "")
        and is_fresh(last_sync, ttl_seconds)
    )


def is_wishlist_worker_running(lock_file, now=None, stale_seconds=WISHLIST_WORKER_STALE_SECONDS):
    if not lock_file or not Path(lock_file).exists():
        return False
    try:
        return ((time.time() if now is None else float(now)) - Path(lock_file).stat().st_mtime) < stale_seconds
    except OSError:
        return False


def collect_unique_wishlist_app_ids(wishlist_items):
    app_ids = []
    seen_app_ids = set()
    for wishlist_item in wishlist_items or []:
        app_id = str((wishlist_item or {}).get("appid", "")).strip()
        if app_id and app_id not in seen_app_ids:
            seen_app_ids.add(app_id)
            app_ids.append(app_id)
    return app_ids


def wishlist_contains_app_id(wishlist_items, app_id):
    normalized_app_id = str(app_id or "").strip()
    if not normalized_app_id:
        return False
    return normalized_app_id in set(collect_unique_wishlist_app_ids(wishlist_items))


def add_wishlist_cache_item(wishlist_items, app_id, now=None):
    normalized_app_id = str(app_id or "").strip()
    if not normalized_app_id:
        return normalize_wishlist_items(wishlist_items)

    normalized_items = normalize_wishlist_items(wishlist_items)
    if wishlist_contains_app_id(normalized_items, normalized_app_id):
        return normalized_items

    normalized_items.append(
        {
            "appid": normalized_app_id,
            "date_added": int(time.time() if now is None else now),
            "priority": 0,
        }
    )
    return normalized_items


def remove_wishlist_cache_item(wishlist_items, app_id):
    normalized_app_id = str(app_id or "").strip()
    if not normalized_app_id:
        return normalize_wishlist_items(wishlist_items)
    return [
        item
        for item in normalize_wishlist_items(wishlist_items)
        if str(item.get("appid", "")).strip() != normalized_app_id
    ]


def build_hidden_worker_kwargs(platform=sys.platform, subprocess_module=subprocess):
    return build_hidden_process_kwargs(
        platform=platform,
        subprocess_module=subprocess_module,
    )


def start_wishlist_hydration_worker_process(
    plugin_dir,
    country_code,
    wishlist_items,
    steam_language="english",
    python_executable=sys.executable,
    popen=subprocess.Popen,
    platform=sys.platform,
    subprocess_module=subprocess,
    force=False,
):
    app_ids = collect_unique_wishlist_app_ids(wishlist_items)
    if not app_ids:
        return None

    plugin_dir = Path(plugin_dir)
    worker_script = plugin_dir / "steam_wishlist_worker.py"
    if not worker_script.exists():
        return None

    resolved_country_code = country_code() if callable(country_code) else country_code
    command = [
        python_executable,
        str(worker_script),
        resolved_country_code,
        ",".join(app_ids),
        str(steam_language or "english").strip() or "english",
    ]
    if force:
        command.append("--force")

    error_log = plugin_dir / "steam_wishlist_worker_error.log"
    with error_log.open("ab") as error_stream:
        return start_hidden_process(
            command,
            popen=popen,
            platform=platform,
            subprocess_module=subprocess_module,
            cwd=str(plugin_dir),
            stderr=error_stream,
        )


def sort_wishlist_items(items):
    return sorted(
        items,
        key=lambda item: (-_coerce_int(item.get("date_added", 0)), item["appid"]),
    )


def normalize_wishlist_search(search_term):
    return str(search_term or "").strip().lower()


def select_wishlist_prewarm_items(sorted_items, limit):
    try:
        limit = int(limit or 0)
    except (TypeError, ValueError):
        limit = 0
    if limit <= 0:
        return []
    return list(sorted_items[:limit])


def build_wishlist_results_plan(wishlist_items, search_term, metadata_resolver, max_results):
    normalized_search = normalize_wishlist_search(search_term)
    sorted_items = sort_wishlist_items(wishlist_items)
    loaded_count = 0
    missing_items = []
    visible_items = []
    matching_loaded_count = 0

    try:
        max_results = int(max_results or 0)
    except (TypeError, ValueError):
        max_results = 0

    for wishlist_item in sorted_items:
        metadata = metadata_resolver(wishlist_item["appid"])
        if metadata and metadata.get("name"):
            loaded_count += 1
            name_matches = not normalized_search or normalized_search in str(metadata["name"]).lower()
            if name_matches:
                matching_loaded_count += 1
                if len(visible_items) < max_results:
                    visible_items.append(wishlist_item)
        else:
            missing_items.append(wishlist_item)

    return {
        "normalized_search": normalized_search,
        "sorted_items": sorted_items,
        "loaded_count": loaded_count,
        "missing_items": missing_items,
        "visible_items": visible_items,
        "matching_loaded_count": matching_loaded_count,
    }
