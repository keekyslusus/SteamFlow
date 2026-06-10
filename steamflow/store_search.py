import urllib.parse

from .http_client import DEFAULT_HTTP_HEADERS, http_get_json


STORE_SEARCH_URL = "https://store.steampowered.com/api/storesearch/"
USER_AGENT = DEFAULT_HTTP_HEADERS["User-Agent"]


def build_store_search_url(search_term, country_code="us", language="en"):
    query = {
        "term": str(search_term or "").strip(),
        "cc": str(country_code or "us").strip() or "us",
        "l": str(language or "en").strip() or "en",
    }
    return f"{STORE_SEARCH_URL}?{urllib.parse.urlencode(query)}"


def normalize_store_search_item(item):
    if not isinstance(item, dict):
        return None
    return {
        "type": item.get("type"),
        "id": item.get("id"),
        "name": item.get("name", "Unknown Game"),
        "platforms": item.get("platforms", {}),
        "tiny_image": item.get("tiny_image"),
        "has_price": "price" in item,
        "price": item.get("price"),
        "is_free": item.get("is_free", False),
    }


def parse_store_search_games(payload, blacklist=None, max_results=8):
    blacklist = {str(app_id) for app_id in (blacklist or set())}
    items = payload.get("items", []) if isinstance(payload, dict) else []
    if not isinstance(items, list):
        return []

    games = []
    for item in items[: int(max_results or 0)]:
        normalized = normalize_store_search_item(item)
        if not normalized:
            continue
        if str(normalized.get("id")) in blacklist:
            continue
        games.append(normalized)
    return games


def fetch_store_search_games(http_get, search_term, country_code="us", language="en", blacklist=None, max_results=8, timeout=0.7):
    payload = http_get_json(
        http_get,
        build_store_search_url(search_term, country_code=country_code, language=language),
        timeout=timeout,
    )
    return parse_store_search_games(payload, blacklist=blacklist, max_results=max_results)
