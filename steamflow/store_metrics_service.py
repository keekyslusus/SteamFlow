from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlencode

from . import util_currency
from .http_client import http_get_json
from .localization import Localizer


RELEASE_DATE_PLACEHOLDER_VALUES = frozenset(
    {
        "coming soon",
        "to be announced",
        "tba",
        "tbd",
    }
)


def _normalize_release_placeholder(value):
    return " ".join(str(value or "").strip().casefold().split())


def _label(labels, name, key):
    labels = labels or {}
    return labels.get(name) or Localizer("en").tr(key)


def normalize_store_game_data(game_data, metadata=None):
    game_data = dict(game_data or {})
    if not metadata:
        return game_data

    name = metadata.get("name") or game_data.get("name")
    return {
        **game_data,
        "store_type": metadata.get("type") or game_data.get("store_type"),
        "name": name,
        "platforms": metadata.get("platforms") or game_data.get("platforms", {}),
        "tiny_image": metadata.get("capsule_image") or game_data.get("tiny_image"),
        "has_price": metadata.get("has_price", game_data.get("has_price", False)),
        "price": metadata.get("price") if metadata.get("price") is not None else game_data.get("price"),
        "is_free": metadata.get("is_free") if metadata.get("is_free") is not None else game_data.get("is_free"),
        "coming_soon": metadata.get("coming_soon", game_data.get("coming_soon", False)),
        "release_date_text": metadata.get("release_date_text") or game_data.get("release_date_text", ""),
    }


def format_release_date_text(release_date_text):
    release_date_text = str(release_date_text or "").strip()
    if not release_date_text:
        return ""
    return f" | {release_date_text}"


def format_owned_playtime(playtime_minutes):
    if playtime_minutes is None:
        return ""
    if playtime_minutes < 60:
        return f" | {playtime_minutes}m"
    return f" | {playtime_minutes / 60:.1f}h"


def format_store_achievement_progress(achievement_progress):
    if not achievement_progress:
        return ""
    unlocked_count, total_count = achievement_progress
    if total_count <= 0:
        return ""
    return f" | {unlocked_count}/{total_count}"


def format_discount_percent(price_info):
    if not isinstance(price_info, dict):
        return ""

    try:
        initial_price = int(price_info.get("initial", 0))
        final_price = int(price_info.get("final", 0))
    except (TypeError, ValueError):
        return ""

    if initial_price <= 0 or final_price < 0 or final_price >= initial_price:
        return ""

    discount_percent = round(((initial_price - final_price) / initial_price) * 100)
    if discount_percent <= 0:
        return ""
    return f" -{discount_percent}%"


def format_store_price_or_availability(game_data, country_code, show_prices=True, is_owned=False, labels=None):
    labels = labels or {}
    if not show_prices or is_owned:
        return ""

    if game_data.get("is_free") is True:
        return f" | {_label(labels, 'free', 'store.availability.free')}"

    price_info = game_data.get("price")
    if price_info and "final" in price_info:
        return (
            f" | {util_currency.format_price(price_info)}"
            f"{format_discount_percent(price_info)}"
        )

    if game_data.get("coming_soon"):
        return f" | {_label(labels, 'coming_soon', 'store.availability.coming_soon')}"

    return ""


def should_show_release_date_text(game_data, placeholder_values=RELEASE_DATE_PLACEHOLDER_VALUES, labels=None):
    release_date_text = str(game_data.get("release_date_text", "") or "").strip()
    if not release_date_text:
        return False

    normalized_placeholders = {
        _normalize_release_placeholder(value)
        for value in placeholder_values
    }
    if game_data.get("coming_soon"):
        coming_soon_label = _label(labels, "coming_soon", "store.availability.coming_soon")
        normalized_placeholders.add(_normalize_release_placeholder(coming_soon_label))

    return _normalize_release_placeholder(release_date_text) not in normalized_placeholders


def supports_live_metrics(game_data, excluded_name_patterns):
    store_type = str(game_data.get("store_type", "") or "").strip().lower()
    if store_type and store_type != "game":
        return False

    if game_data.get("type") != "app":
        return False

    name = str(game_data.get("name", "")).strip().lower()
    if not name:
        return False

    return not any(pattern in name for pattern in excluded_name_patterns)


def format_player_count(player_count):
    if player_count is None:
        return ""
    try:
        player_count = int(player_count)
        if player_count <= 0:
            return ""
    except (TypeError, ValueError):
        return ""
    return f" | \U0001F465 {player_count:,}"


def format_review_score(review_summary):
    if not review_summary:
        return ""

    try:
        total_positive = int(review_summary.get("total_positive", 0))
        total_reviews = int(review_summary.get("total_reviews", 0))
    except (TypeError, ValueError):
        return ""

    if total_reviews <= 0:
        return ""

    percentage = round((total_positive / total_reviews) * 100)
    review_score_desc = str(review_summary.get("review_score_desc", "")).strip()
    if review_score_desc:
        return f" | {percentage}% ({review_score_desc})"
    return f" | {percentage}%"


def get_store_result_action_method(is_owned):
    return "open_steam_library_game_details" if is_owned else "open_steam_store_page"


def build_store_result_title(name, is_owned, labels=None):
    labels = labels or {}
    title_prefix = "\U0001F3AE" if is_owned else "\U0001F6D2"
    ownership_suffix = f" [{_label(labels, 'owned', 'store.owned_suffix')}]" if is_owned else ""
    return f"{title_prefix} {name}{ownership_suffix}"


def build_store_result_subtitle(
    game_data,
    is_owned,
    platform_suffix="",
    review_score_text="",
    player_count_text="",
    owned_playtime_text="",
    achievement_progress_text="",
    price_text="",
    release_date_text="",
    labels=None,
):
    labels = labels or {}
    subtitle_prefix = (
        _label(labels, "library_subtitle", "store.subtitle.library")
        if is_owned
        else _label(labels, "store_subtitle", "store.subtitle.store")
    )
    return (
        f"{subtitle_prefix}{platform_suffix}"
        f"{review_score_text}{player_count_text}{owned_playtime_text}"
        f"{achievement_progress_text}{price_text}{release_date_text}"
    )


def resolve_store_metric_bundle(
    app_id,
    image_url,
    allow_cold_metric_fetch,
    icon_resolver,
    review_resolver=None,
    player_count_resolver=None,
    achievement_resolver=None,
):
    with ThreadPoolExecutor(max_workers=4) as executor:
        icon_future = executor.submit(icon_resolver, app_id, image_url)
        review_future = (
            executor.submit(review_resolver, app_id, allow_cold_metric_fetch)
            if review_resolver
            else None
        )
        player_count_future = (
            executor.submit(player_count_resolver, app_id, allow_cold_metric_fetch)
            if player_count_resolver
            else None
        )
        achievement_future = (
            executor.submit(achievement_resolver, app_id, allow_cold_metric_fetch)
            if achievement_resolver
            else None
        )

        return {
            "icon_path": icon_future.result(),
            "review_summary": review_future.result() if review_future else None,
            "player_count": player_count_future.result() if player_count_future else None,
            "achievement_progress": achievement_future.result() if achievement_future else None,
        }


def build_store_game_result_spec(
    game_data,
    is_owned,
    icon_path,
    review_summary=None,
    player_count=None,
    achievement_progress=None,
    owned_playtime_minutes=None,
    platform_suffix="",
    country_code="us",
    show_prices=True,
    include_review_score=False,
    include_player_count=False,
    include_achievements=False,
    labels=None,
):
    labels = labels or {}
    app_id = game_data.get("id")
    name = game_data.get("name")
    release_date_text = (
        format_release_date_text(game_data.get("release_date_text"))
        if should_show_release_date_text(game_data, labels=labels)
        else ""
    )
    return {
        "title": build_store_result_title(name, is_owned, labels=labels),
        "subtitle": build_store_result_subtitle(
            game_data,
            is_owned,
            platform_suffix=platform_suffix,
            review_score_text=format_review_score(review_summary) if include_review_score else "",
            player_count_text=format_player_count(player_count) if include_player_count else "",
            owned_playtime_text=format_owned_playtime(owned_playtime_minutes) if is_owned else "",
            achievement_progress_text=(
                format_store_achievement_progress(achievement_progress)
                if include_achievements
                else ""
            ),
            price_text=format_store_price_or_availability(
                game_data,
                country_code,
                show_prices=show_prices,
                is_owned=is_owned,
                labels=labels,
            ),
            release_date_text=release_date_text,
            labels=labels,
        ),
        "icon_path": icon_path,
        "context_data": {
            "app_id": app_id,
            "name": name,
            "is_owned": is_owned,
            "coming_soon": game_data.get("coming_soon"),
            "result_source": str(game_data.get("result_source", "") or "store"),
            "store_type": game_data.get("store_type"),
            "is_free": game_data.get("is_free"),
            "has_price": game_data.get("has_price"),
        },
        "action_method": get_store_result_action_method(is_owned),
        "app_id": app_id,
    }


def build_current_players_url(app_id):
    return f"https://api.steampowered.com/ISteamUserStats/GetNumberOfCurrentPlayers/v1/?appid={app_id}"


def fetch_current_players_with_http_get(http_get, app_id, timeout=1):
    data = http_get_json(http_get, build_current_players_url(str(app_id)), timeout=timeout, headers=None)
    if data.get("response", {}).get("result") == 1:
        return data["response"].get("player_count")
    return None


def build_review_score_url(app_id, steam_language="english"):
    query = {
        "json": 1,
        "language": "all",
        "purchase_type": "all",
        "num_per_page": 0,
        "l": str(steam_language or "english"),
    }
    return f"https://store.steampowered.com/appreviews/{app_id}?{urlencode(query)}"


def fetch_review_score_with_http_get(http_get, app_id, timeout=1, steam_language="english"):
    data = http_get_json(http_get, build_review_score_url(str(app_id), steam_language=steam_language), timeout=timeout)
    return data.get("query_summary", data)


def build_achievement_schema_url(api_key, app_id):
    return (
        "https://api.steampowered.com/ISteamUserStats/GetSchemaForGame/v2/"
        f"?key={api_key}&appid={app_id}&l=en"
    )


def fetch_achievement_schema_total_with_http_get(http_get, api_key, app_id, timeout=1.2):
    data = http_get_json(http_get, build_achievement_schema_url(api_key, str(app_id)), timeout=timeout)
    achievements = (
        data.get("game", {})
        .get("availableGameStats", {})
        .get("achievements", [])
    )
    if isinstance(achievements, list):
        return len(achievements)
    return None


def build_player_achievements_url(api_key, steamid64, app_id):
    return (
        "https://api.steampowered.com/ISteamUserStats/GetPlayerAchievements/v1/"
        f"?key={api_key}&steamid={steamid64}&appid={app_id}&l=en"
    )


def fetch_player_achievement_progress_with_http_get(http_get, api_key, steamid64, app_id, timeout=1.2):
    data = http_get_json(
        http_get,
        build_player_achievements_url(api_key, steamid64, str(app_id)),
        timeout=timeout,
    )
    achievements = data.get("playerstats", {}).get("achievements", [])
    if isinstance(achievements, list):
        return sum(1 for achievement in achievements if achievement.get("achieved"))
    return None
