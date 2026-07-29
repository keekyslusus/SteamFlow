import time
from urllib.parse import urlencode

from .http_client import http_get_json


FRIEND_FAVORITES_ENDPOINT = (
    "https://api.steampowered.com/IFriendsListService/GetFavorites/v1/"
)
FRIEND_FAVORITES_CACHE_VERSION = 1


def _coerce_float(value, default=0.0):
    try:
        return float(value or default)
    except (TypeError, ValueError):
        return float(default)


def _coerce_accountid(value):
    try:
        accountid = int(value or 0)
    except (TypeError, ValueError):
        return 0
    return accountid if accountid > 0 else 0


def build_friend_favorites_url(access_token):
    token = str(access_token or "").strip()
    if not token:
        raise ValueError("Missing Steam session token")
    return f"{FRIEND_FAVORITES_ENDPOINT}?{urlencode({'access_token': token})}"


def parse_friend_favorites_payload(payload):
    response = payload.get("response", {}) if isinstance(payload, dict) else {}
    favorites = response.get("favorites", []) if isinstance(response, dict) else []
    if not isinstance(favorites, list):
        return set()
    return {
        accountid
        for item in favorites
        if isinstance(item, dict)
        for accountid in (_coerce_accountid(item.get("accountid")),)
        if accountid
    }


def fetch_friend_favorite_accountids(access_token, http_get, timeout=3):
    payload = http_get_json(
        http_get,
        build_friend_favorites_url(access_token),
        timeout=timeout,
    )
    return parse_friend_favorites_payload(payload)


def normalize_friend_favorites_cache_payload(payload):
    accounts = payload.get("accounts", {}) if isinstance(payload, dict) else {}
    if not isinstance(accounts, dict):
        accounts = {}
    normalized = {}
    for steamid64, entry in accounts.items():
        normalized_steamid64 = str(steamid64 or "").strip()
        if not normalized_steamid64 or not isinstance(entry, dict):
            continue
        raw_accountids = entry.get("accountids", [])
        if not isinstance(raw_accountids, (list, tuple, set, frozenset)):
            raw_accountids = []
        accountids = {
            accountid
            for value in raw_accountids
            for accountid in (_coerce_accountid(value),)
            if accountid
        }
        normalized[normalized_steamid64] = {
            "timestamp": _coerce_float(entry.get("timestamp", 0)),
            "accountids": accountids,
        }
    return normalized


def build_friend_favorites_cache_payload(accounts):
    normalized = normalize_friend_favorites_cache_payload({"accounts": accounts})
    return {
        "version": FRIEND_FAVORITES_CACHE_VERSION,
        "accounts": {
            steamid64: {
                "timestamp": entry["timestamp"],
                "accountids": sorted(entry["accountids"]),
            }
            for steamid64, entry in sorted(normalized.items())
        },
    }


def get_cached_friend_favorites(accounts, steamid64):
    normalized_steamid64 = str(steamid64 or "").strip()
    entry = (accounts or {}).get(normalized_steamid64, {})
    if not isinstance(entry, dict):
        return set(), 0.0
    raw_accountids = entry.get("accountids", [])
    if not isinstance(raw_accountids, (list, tuple, set, frozenset)):
        raw_accountids = []
    return (
        {
            accountid
            for value in raw_accountids
            for accountid in (_coerce_accountid(value),)
            if accountid
        },
        _coerce_float(entry.get("timestamp", 0)),
    )


def is_friend_favorites_cache_fresh(accounts, steamid64, ttl_seconds, now=None):
    _accountids, timestamp = get_cached_friend_favorites(accounts, steamid64)
    current_time = time.time() if now is None else float(now)
    return timestamp > 0 and current_time - timestamp < float(ttl_seconds)
