import json
import time
import urllib.parse

from .http_client import http_get_json


STEAM_API_BASE_URL = "https://api.steampowered.com"
STEAM_DECK_COMPATIBILITY_LABEL_KEYS = {
    1: "store.deck.unsupported",
    2: "store.deck.playable",
    3: "store.deck.verified",
}


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


def normalize_app_ids(app_ids):
    normalized = []
    seen = set()
    for app_id in app_ids or ():
        value = str(app_id or "").strip()
        if not value.isascii() or not value.isdigit() or int(value) <= 0 or value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    return normalized


def build_last_played_times_url(api_key):
    query = urllib.parse.urlencode(
        {
            "key": str(api_key or "").strip(),
            "min_last_played": 0,
        }
    )
    return f"{STEAM_API_BASE_URL}/IPlayerService/ClientGetLastPlayedTimes/v1/?{query}"


def parse_last_played_times(payload):
    games = payload.get("response", {}).get("games", []) if isinstance(payload, dict) else []
    return games if isinstance(games, list) else []


def get_latest_deck_playtime(games):
    latest = 0
    for game in games or ():
        if not isinstance(game, dict):
            continue
        latest = max(
            latest,
            _coerce_int(game.get("last_deck_playtime")),
            _coerce_int(game.get("first_deck_playtime")),
        )
    return latest


def fetch_last_played_times(http_get, api_key, timeout=3):
    payload = http_get_json(
        http_get,
        build_last_played_times_url(api_key),
        timeout=timeout,
    )
    return parse_last_played_times(payload)


def is_deck_activity_recent(last_deck_playtime, now=None, activity_window_seconds=50 * 24 * 60 * 60):
    now = time.time() if now is None else float(now)
    last_deck_playtime = _coerce_float(last_deck_playtime)
    return bool(
        last_deck_playtime > 0
        and now - last_deck_playtime <= float(activity_window_seconds)
    )


def get_next_history_check_interval(
    ever_detected,
    negative_check_count,
    initial_intervals_seconds=(24 * 60 * 60, 3 * 24 * 60 * 60, 7 * 24 * 60 * 60),
    detected_interval_seconds=14 * 24 * 60 * 60,
):
    if ever_detected:
        return float(detected_interval_seconds)
    intervals = tuple(float(value) for value in initial_intervals_seconds if float(value) > 0)
    if not intervals:
        return float(detected_interval_seconds)
    index = max(0, min(int(negative_check_count or 0) - 1, len(intervals) - 1))
    return intervals[index]


def build_store_items_url(app_ids, country_code="us", language="english"):
    normalized_app_ids = normalize_app_ids(app_ids)
    input_data = {
        "ids": [{"appid": int(app_id)} for app_id in normalized_app_ids],
        "context": {
            "language": str(language or "english").strip() or "english",
            "country_code": str(country_code or "us").strip().upper() or "US",
            "steam_realm": 1,
        },
        "data_request": {
            "include_platforms": True,
            "include_basic_info": True,
        },
    }
    query = urllib.parse.urlencode(
        {
            "input_json": json.dumps(
                input_data,
                separators=(",", ":"),
            )
        }
    )
    return f"{STEAM_API_BASE_URL}/IStoreBrowseService/GetItems/v1/?{query}"


def parse_deck_compatibility_categories(payload):
    items = payload.get("response", {}).get("store_items", []) if isinstance(payload, dict) else []
    if not isinstance(items, list):
        return {}

    categories = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        app_id = str(item.get("appid") or item.get("id") or "").strip()
        if not app_id:
            continue
        platforms = item.get("platforms") if isinstance(item.get("platforms"), dict) else {}
        category = _coerce_int(platforms.get("steam_deck_compat_category"), default=0)
        categories[app_id] = category if category in {0, 1, 2, 3} else 0
    return categories


def fetch_deck_compatibility_categories(
    http_get,
    app_ids,
    country_code="us",
    language="english",
    timeout=1.2,
):
    normalized_app_ids = normalize_app_ids(app_ids)
    if not normalized_app_ids:
        return {}
    payload = http_get_json(
        http_get,
        build_store_items_url(
            normalized_app_ids,
            country_code=country_code,
            language=language,
        ),
        timeout=timeout,
    )
    parsed = parse_deck_compatibility_categories(payload)
    return {
        app_id: parsed.get(app_id, 0)
        for app_id in normalized_app_ids
    }


def apply_deck_compatibility_categories(games, categories):
    categories = categories if isinstance(categories, dict) else {}
    enriched = []
    for game in games or ():
        game_data = dict(game or {})
        app_id = str(game_data.get("id") or "").strip()
        if app_id in categories:
            game_data["steam_deck_compat_category"] = categories[app_id]
        enriched.append(game_data)
    return enriched


def normalize_steam_deck_cache_payload(payload):
    payload = payload if isinstance(payload, dict) else {}
    raw_accounts = payload.get("accounts") if isinstance(payload.get("accounts"), dict) else {}
    raw_compatibility = (
        payload.get("compatibility")
        if isinstance(payload.get("compatibility"), dict)
        else {}
    )

    accounts = {}
    for steamid64, raw_state in raw_accounts.items():
        steamid64 = str(steamid64 or "").strip()
        if not steamid64.isdigit() or not isinstance(raw_state, dict):
            continue
        accounts[steamid64] = {
            "last_attempt_at": _coerce_float(raw_state.get("last_attempt_at")),
            "last_checked_at": _coerce_float(raw_state.get("last_checked_at")),
            "next_check_at": _coerce_float(raw_state.get("next_check_at")),
            "last_deck_playtime": _coerce_int(raw_state.get("last_deck_playtime")),
            "ever_detected": bool(raw_state.get("ever_detected")),
            "negative_check_count": max(0, _coerce_int(raw_state.get("negative_check_count"))),
        }

    compatibility = {}
    for app_id, raw_entry in raw_compatibility.items():
        app_id = str(app_id or "").strip()
        if not app_id.isdigit() or not isinstance(raw_entry, dict):
            continue
        category = _coerce_int(raw_entry.get("category"))
        compatibility[app_id] = {
            "category": category if category in {0, 1, 2, 3} else 0,
            "timestamp": _coerce_float(raw_entry.get("timestamp")),
        }

    return {
        "accounts": accounts,
        "compatibility": compatibility,
        "compatibility_last_failure": _coerce_float(
            payload.get("compatibility_last_failure")
        ),
    }
