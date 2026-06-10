import time

from .http_client import download_http_get_to_file, http_get_json


COMMUNITY_ASSETS_BASE_URL = "https://shared.fastly.steamstatic.com/community_assets/images/"
AVATAR_FRAME_CACHE_TTL_SECONDS = 24 * 60 * 60
PROFILE_STATUS_LABELS = {
    0: "Offline",
    1: "Online",
    2: "Busy",
    3: "Away",
    4: "Snooze",
    5: "Looking to trade",
    6: "Looking to play",
}
PROFILE_STATUS_LABEL_KEYS = {
    0: "profile.status.offline",
    1: "profile.status.online",
    2: "profile.status.busy",
    3: "profile.status.away",
    4: "profile.status.snooze",
    5: "profile.status.looking_to_trade",
    6: "profile.status.looking_to_play",
}


def build_player_summaries_url(api_key, steamid64):
    return (
        "https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2/"
        f"?key={api_key}&steamids={steamid64}"
    )


def parse_player_summary_payload(payload, steamid64, now=None):
    players = payload.get("response", {}).get("players", [])
    if not isinstance(players, list) or not players:
        return None

    player_data = players[0] if isinstance(players[0], dict) else {}
    return {
        "steamid64": str(steamid64 or "").strip(),
        "personaname": str(player_data.get("personaname", "") or "").strip(),
        "personastate": int(player_data.get("personastate", 0) or 0),
        "gameextrainfo": str(player_data.get("gameextrainfo", "") or "").strip(),
        "fetched_at": time.time() if now is None else float(now),
    }


def fetch_player_summary(api_key, steamid64, http_get, timeout=1.2, now=None):
    if not api_key or not steamid64:
        return None
    payload = http_get_json(
        http_get,
        build_player_summaries_url(api_key, steamid64),
        timeout=timeout,
    )
    return parse_player_summary_payload(payload, steamid64, now=now)


def is_profile_summary_for_steamid64(summary, steamid64):
    return str((summary or {}).get("steamid64", "") or "") == str(steamid64 or "").strip()


def get_profile_status_label(summary, tr=None):
    if not summary:
        return ""

    current_game = str(summary.get("gameextrainfo", "") or "").strip()
    if current_game:
        if callable(tr):
            return tr("profile.status.playing", game=current_game)
        return f"Playing {current_game}"

    try:
        persona_state = int(summary.get("personastate", 0) or 0)
    except (TypeError, ValueError):
        return ""
    if callable(tr):
        return tr(PROFILE_STATUS_LABEL_KEYS.get(persona_state, ""))
    return PROFILE_STATUS_LABELS.get(persona_state, "")


def build_owned_games_url(api_key, steamid64):
    return (
        "https://api.steampowered.com/IPlayerService/GetOwnedGames/v1/"
        f"?key={api_key}&steamid={steamid64}&include_played_free_games=1&include_appinfo=0"
    )


def parse_owned_games_payload(payload):
    games = payload.get("response", {}).get("games", [])
    if not isinstance(games, list):
        return set(), {}

    owned_app_ids = set()
    owned_game_playtimes = {}
    for game_data in games:
        if not isinstance(game_data, dict):
            continue
        app_id = str(game_data.get("appid", "")).strip()
        if not app_id:
            continue
        owned_app_ids.add(app_id)
        try:
            owned_game_playtimes[app_id] = int(game_data.get("playtime_forever", 0) or 0)
        except (TypeError, ValueError):
            owned_game_playtimes[app_id] = 0
    return owned_app_ids, owned_game_playtimes


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


def normalize_owned_games_cache_payload(cache_data):
    if not isinstance(cache_data, dict):
        return None

    owned_app_ids = cache_data.get("owned_app_ids", [])
    owned_game_playtimes = cache_data.get("owned_game_playtimes", {})
    if not isinstance(owned_app_ids, list):
        owned_app_ids = []
    if not isinstance(owned_game_playtimes, dict):
        owned_game_playtimes = {}

    return {
        "last_attempt": _coerce_float(cache_data.get("last_attempt", 0)),
        "last_sync": _coerce_float(cache_data.get("timestamp", 0)),
        "public_profile": cache_data.get("public_profile"),
        "steamid64": str(cache_data.get("steamid64", "") or "") or None,
        "owned_app_ids": {str(app_id) for app_id in owned_app_ids if str(app_id).strip()},
        "owned_game_playtimes": {
            str(app_id): _coerce_int(playtime_minutes)
            for app_id, playtime_minutes in owned_game_playtimes.items()
            if str(app_id).strip()
        },
    }


def build_owned_games_cache_payload(
    last_attempt,
    last_sync,
    public_profile,
    steamid64,
    owned_app_ids,
    owned_game_playtimes,
):
    return {
        "last_attempt": last_attempt,
        "timestamp": last_sync,
        "public_profile": public_profile,
        "steamid64": steamid64,
        "owned_app_ids": sorted(owned_app_ids),
        "owned_game_playtimes": dict(owned_game_playtimes),
    }


def is_owned_games_cache_fresh(cache_loaded, cache_steamid64, active_steamid64, last_sync, ttl_seconds, is_fresh):
    if not cache_loaded:
        return False
    if str(cache_steamid64 or "") != str(active_steamid64 or ""):
        return False
    return is_fresh(last_sync, ttl_seconds)


def get_owned_app_state(app_id, cache_steamid64, active_steamid64, owned_app_ids, cache_is_fresh):
    normalized_app_id = str(app_id or "").strip()
    if not normalized_app_id:
        return "unknown"
    if str(cache_steamid64 or "") == str(active_steamid64 or "") and normalized_app_id in owned_app_ids:
        return "owned"
    if cache_is_fresh:
        return "not_owned"
    return "unknown"


def should_schedule_owned_games_refresh(force, now, last_attempt, retry_delay_seconds, cache_is_fresh):
    if force:
        return True
    if (float(now) - float(last_attempt or 0)) < float(retry_delay_seconds or 0):
        return False
    if callable(cache_is_fresh):
        cache_is_fresh = cache_is_fresh()
    if cache_is_fresh:
        return False
    return True


def is_expected_owned_games_refresh_error(error, urllib3_module):
    expected_error_types = (
        urllib3_module.exceptions.TimeoutError,
        urllib3_module.exceptions.HTTPError,
        ValueError,
    )
    return isinstance(error, expected_error_types)


def fetch_owned_games_refresh_result(fetch_owned_app_ids_from_api, api_key, steamid64, urllib3_module, timeout=3):
    try:
        owned_app_ids, owned_game_playtimes = fetch_owned_app_ids_from_api(api_key, steamid64, timeout=timeout)
        return {
            "success": True,
            "owned_app_ids": owned_app_ids,
            "owned_game_playtimes": owned_game_playtimes,
            "error": None,
            "should_log_error": False,
        }
    except Exception as error:
        return {
            "success": False,
            "owned_app_ids": set(),
            "owned_game_playtimes": {},
            "error": error,
            "should_log_error": not is_expected_owned_games_refresh_error(error, urllib3_module),
        }


def build_owned_games_refresh_log_details(steamid64, owned_app_ids, success):
    return f"steamid64={steamid64} count={len(owned_app_ids)} success={success}"


def fetch_owned_app_ids(api_key, steamid64, http_get, normalize_api_key=None, timeout=3):
    normalized_key = normalize_api_key(api_key) if normalize_api_key else str(api_key or "").strip()
    normalized_steamid64 = str(steamid64 or "").strip()
    if not normalized_key or not normalized_steamid64:
        raise ValueError("Missing Steam API credentials")

    payload = http_get_json(
        http_get,
        build_owned_games_url(normalized_key, normalized_steamid64),
        timeout=timeout,
    )
    return parse_owned_games_payload(payload)


def build_avatar_frame_url(api_key, steamid64):
    return f"https://api.steampowered.com/IPlayerService/GetAvatarFrame/v1/?key={api_key}&steamid={steamid64}"


def normalize_avatar_frame_image_url(image_path):
    image_url = str(image_path or "").strip()
    if not image_url:
        return ""
    if image_url.startswith("http://") or image_url.startswith("https://"):
        return image_url
    return f"{COMMUNITY_ASSETS_BASE_URL}{image_url.lstrip('/')}"


def parse_avatar_frame_payload(payload):
    frame_data = payload.get("response", {}).get("avatar_frame") or {}
    if not isinstance(frame_data, dict):
        return None

    communityitemid = str(frame_data.get("communityitemid", "")).strip()
    image_url = normalize_avatar_frame_image_url(
        frame_data.get("image_small") or frame_data.get("image_large") or ""
    )
    if not communityitemid or not image_url:
        return None

    return {
        "communityitemid": communityitemid,
        "image_url": image_url,
        "name": frame_data.get("name") or frame_data.get("item_title"),
    }


def get_cached_avatar_frame_state(cache_data, steamid64, avatar_cache_dir, now=None, ttl_seconds=AVATAR_FRAME_CACHE_TTL_SECONDS):
    cache_data = cache_data or {}
    cached_steamid64 = str(cache_data.get("steamid64", "") or "")
    cache_age_seconds = (time.time() if now is None else float(now)) - _coerce_float(cache_data.get("timestamp", 0))
    if cached_steamid64 != str(steamid64 or "") or cache_age_seconds >= ttl_seconds:
        return None, False

    cached_image_name = str((cache_data or {}).get("image_name", "") or "")
    cached_frame_path = avatar_cache_dir / cached_image_name if cached_image_name else None
    if cached_frame_path and cached_frame_path.exists():
        return cached_frame_path, False
    if cache_data.get("no_frame"):
        return None, True
    return None, False


def build_no_avatar_frame_cache_entry(steamid64, now=None):
    return {
        "steamid64": steamid64,
        "timestamp": time.time() if now is None else float(now),
        "no_frame": True,
    }


def build_avatar_frame_cache_entry(steamid64, frame_data, image_name, now=None):
    return {
        "steamid64": steamid64,
        "timestamp": time.time() if now is None else float(now),
        "communityitemid": frame_data["communityitemid"],
        "image_name": image_name,
        "image_url": frame_data["image_url"],
        "frame_name": frame_data.get("name"),
    }


def fetch_avatar_frame_data(api_key, steamid64, http_get, timeout=1.2):
    if not api_key or not steamid64:
        return None
    payload = http_get_json(
        http_get,
        build_avatar_frame_url(api_key, steamid64),
        timeout=timeout,
    )
    return parse_avatar_frame_payload(payload)


def download_binary_file(http_get, url, save_path, timeout=2):
    return download_http_get_to_file(http_get, url, save_path, timeout=timeout)


def compose_framed_avatar_icon(avatar_path, frame_path, output_path, image_module):
    if image_module is None:
        return False

    with image_module.open(avatar_path) as avatar_image, image_module.open(frame_path) as frame_image:
        avatar_rgba = avatar_image.convert("RGBA")
        frame_rgba = frame_image.convert("RGBA").resize(avatar_rgba.size, image_module.Resampling.LANCZOS)
        composed = avatar_rgba.copy()
        composed.alpha_composite(frame_rgba)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        composed.save(output_path, format="PNG")
    return output_path.exists()
