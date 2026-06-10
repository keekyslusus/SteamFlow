import time
import urllib.parse

from .http_client import http_get_json


FEATURED_CATEGORIES_URL = "https://store.steampowered.com/api/featuredcategories/"
DYNAMIC_STORE_USERDATA_URL = "https://store.steampowered.com/dynamicstore/userdata/"
STORE_COLLECTIONS = frozenset({"top_sellers", "specials"})


def normalize_store_collection_name(value):
    normalized = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    return normalized if normalized in STORE_COLLECTIONS else ""


def build_featured_categories_url(country_code="us", language="en"):
    query = {
        "cc": str(country_code or "us").strip() or "us",
        "l": str(language or "en").strip() or "en",
    }
    return f"{FEATURED_CATEGORIES_URL}?{urllib.parse.urlencode(query)}"


def build_dynamic_store_userdata_url(access_token):
    query = {"access_token": str(access_token or "").strip()}
    return f"{DYNAMIC_STORE_USERDATA_URL}?{urllib.parse.urlencode(query)}"


def _normalize_platforms(item):
    platforms = item.get("platforms")
    if isinstance(platforms, dict):
        return platforms
    return {
        "windows": bool(item.get("windows_available")),
        "mac": bool(item.get("mac_available")),
        "linux": bool(item.get("linux_available")),
    }


def _normalize_price(item):
    final_price = item.get("final_price")
    original_price = item.get("original_price")
    currency = str(item.get("currency", "") or "").strip()
    if final_price is None and original_price is None:
        return None

    price = {}
    if final_price is not None:
        price["final"] = final_price
    if original_price is not None:
        price["initial"] = original_price
    if currency:
        price["currency"] = currency
    return price


def normalize_featured_category_item(item, result_source=None):
    if not isinstance(item, dict):
        return None

    app_id = item.get("id") or item.get("appid") or item.get("app_id")
    if app_id is None:
        return None

    price = _normalize_price(item)
    is_free = item.get("is_free")
    if is_free is None:
        try:
            is_free = int(price.get("final", 1)) == 0 if price else False
        except (TypeError, ValueError, AttributeError):
            is_free = False

    return {
        "type": "app",
        "id": app_id,
        "name": item.get("name", "Unknown Game"),
        "platforms": _normalize_platforms(item),
        "tiny_image": (
            item.get("small_capsule_image")
            or item.get("tiny_image")
            or item.get("capsule_image")
            or item.get("header_image")
        ),
        "has_price": price is not None,
        "price": price,
        "is_free": bool(is_free),
        "store_type": "game",
        "result_source": result_source or "store_collection",
    }


def parse_featured_collection_games(payload, collection_name, blacklist=None, ignored_app_ids=None, max_results=8):
    collection_name = normalize_store_collection_name(collection_name)
    if not collection_name or not isinstance(payload, dict):
        return []

    collection = payload.get(collection_name, {})
    items = collection.get("items", []) if isinstance(collection, dict) else []
    if not isinstance(items, list):
        return []

    blocked = {str(app_id) for app_id in (blacklist or set())}
    blocked.update(str(app_id) for app_id in (ignored_app_ids or set()))

    games = []
    for item in items:
        normalized = normalize_featured_category_item(item, result_source=collection_name)
        if not normalized:
            continue
        if str(normalized.get("id")) in blocked:
            continue
        games.append(normalized)
        if len(games) >= int(max_results or 0):
            break
    return games


def fetch_featured_collection_games(
    http_get,
    collection_name,
    country_code="us",
    language="en",
    blacklist=None,
    ignored_app_ids=None,
    max_results=8,
    timeout=1.2,
):
    payload = http_get_json(
        http_get,
        build_featured_categories_url(country_code=country_code, language=language),
        timeout=timeout,
    )
    return parse_featured_collection_games(
        payload,
        collection_name,
        blacklist=blacklist,
        ignored_app_ids=ignored_app_ids,
        max_results=max_results,
    )


def fetch_featured_collections_games(
    http_get,
    collection_names=STORE_COLLECTIONS,
    country_code="us",
    language="en",
    blacklist=None,
    ignored_app_ids=None,
    max_results=8,
    timeout=1.2,
):
    payload = http_get_json(
        http_get,
        build_featured_categories_url(country_code=country_code, language=language),
        timeout=timeout,
    )
    games_by_collection = {}
    for collection_name in collection_names or STORE_COLLECTIONS:
        normalized_name = normalize_store_collection_name(collection_name)
        if not normalized_name:
            continue
        games_by_collection[normalized_name] = parse_featured_collection_games(
            payload,
            normalized_name,
            blacklist=blacklist,
            ignored_app_ids=ignored_app_ids,
            max_results=max_results,
        )
    return games_by_collection


def parse_dynamic_store_ignored_app_ids(payload):
    if not isinstance(payload, dict):
        return set()
    ignored = payload.get("rgIgnoredApps", [])
    if isinstance(ignored, dict):
        ignored = list(ignored.keys())
    if not isinstance(ignored, (list, tuple, set)):
        return set()
    return {str(app_id) for app_id in ignored if str(app_id or "").strip()}


def fetch_ignored_app_ids(http_get, access_token, timeout=1.2):
    if not access_token:
        return set()
    payload = http_get_json(
        http_get,
        build_dynamic_store_userdata_url(access_token),
        timeout=timeout,
        headers={"Authorization": f"Bearer {access_token}"},
    )
    return parse_dynamic_store_ignored_app_ids(payload)


def build_store_collection_cache_entry(games, error=None, now=None):
    timestamp = time.time() if now is None else float(now)
    return {
        "timestamp": timestamp,
        "games": list(games or []),
        "error": error,
        "error_timestamp": time.time() if error else None,
    }
