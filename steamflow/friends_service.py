import json
import os
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlencode

from .cache_utils import read_json_file
from .http_client import http_get_json
from .os_integration import start_hidden_process


FRIEND_LIST_ENDPOINT = "https://api.steampowered.com/ISteamUser/GetFriendList/v1/"
PLAYER_SUMMARIES_ENDPOINT = "https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2/"
PLAYER_SUMMARIES_BATCH_SIZE = 100
FRIENDS_REFRESH_LOCK_STALE_SECONDS = 30
FRIENDS_REFRESH_WAIT_SECONDS = 3


class FriendsListUnavailableError(RuntimeError):
    pass


def try_acquire_friends_refresh_lock(
    cache_file,
    now=None,
    stale_seconds=FRIENDS_REFRESH_LOCK_STALE_SECONDS,
):
    lock_file = Path(f"{cache_file}.refresh.lock")
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(lock_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        try:
            current_time = time.time() if now is None else float(now)
            if current_time - lock_file.stat().st_mtime < float(stale_seconds):
                return None
            lock_file.unlink()
            descriptor = os.open(lock_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except (FileExistsError, FileNotFoundError, OSError):
            return None
    try:
        os.write(descriptor, str(os.getpid()).encode("ascii"))
    except Exception:
        os.close(descriptor)
        try:
            lock_file.unlink()
        except OSError:
            pass
        raise
    return lock_file, descriptor


def release_friends_refresh_lock(lock):
    if not lock:
        return
    lock_file, descriptor = lock
    try:
        os.close(descriptor)
    finally:
        try:
            Path(lock_file).unlink()
        except FileNotFoundError:
            pass


def is_friends_refresh_running(
    cache_file,
    now=None,
    stale_seconds=FRIENDS_REFRESH_LOCK_STALE_SECONDS,
):
    lock_file = Path(f"{cache_file}.refresh.lock")
    try:
        current_time = time.time() if now is None else float(now)
        return current_time - lock_file.stat().st_mtime < float(stale_seconds)
    except (FileNotFoundError, OSError):
        return False


def should_schedule_friends_refresh(
    steamid64,
    cached_steamid64,
    last_sync,
    last_attempt,
    error,
    ttl_seconds,
    retry_delay_seconds,
    now=None,
):
    steamid64 = str(steamid64 or "")
    if not steamid64:
        return False
    current_time = time.time() if now is None else float(now)
    if is_friends_cache_fresh(
        steamid64,
        cached_steamid64,
        last_sync,
        ttl_seconds,
        now=current_time,
    ):
        return False
    if (
        str(cached_steamid64 or "") == steamid64
        and str(error or "")
        and current_time - _coerce_float(last_attempt) < float(retry_delay_seconds)
    ):
        return False
    return True


def start_friends_refresh_worker_process(
    plugin_dir,
    python_executable=sys.executable,
    popen=None,
    platform=sys.platform,
    subprocess_module=subprocess,
):
    plugin_dir = Path(plugin_dir)
    main_script = plugin_dir / "main.py"
    if not main_script.exists():
        raise FileNotFoundError(f"SteamFlow entry point not found at {main_script}")
    request = json.dumps(
        {
            "method": "refresh_steam_friends",
            "parameters": [],
            "settings": {},
        },
        separators=(",", ":"),
    )
    return start_hidden_process(
        [python_executable, str(main_script), request],
        popen=popen,
        platform=platform,
        subprocess_module=subprocess_module,
        cwd=str(plugin_dir),
    )


def wait_for_friends_cache_update(
    cache_file,
    steamid64,
    previous_attempt,
    timeout_seconds=FRIENDS_REFRESH_WAIT_SECONDS,
    poll_seconds=0.05,
    sleeper=time.sleep,
    monotonic=time.monotonic,
):
    deadline = monotonic() + float(timeout_seconds)
    while monotonic() < deadline:
        payload = normalize_friends_cache_payload(
            read_json_file(cache_file, default=None)
        )
        if (
            payload
            and str(payload.get("steamid64") or "") == str(steamid64 or "")
            and payload["last_attempt"] > _coerce_float(previous_attempt)
            and (
                bool(payload["error"])
                or payload["last_sync"] >= payload["last_attempt"]
            )
        ):
            return payload
        sleeper(float(poll_seconds))
    return None


def _coerce_int(value, default=0):
    try:
        return int(value or default)
    except (TypeError, ValueError):
        return int(default)


def _coerce_float(value, default=0.0):
    try:
        return float(value or default)
    except (TypeError, ValueError):
        return float(default)


def build_friend_list_url(api_key, steamid64):
    return f"{FRIEND_LIST_ENDPOINT}?{urlencode({'key': api_key, 'steamid': steamid64, 'relationship': 'friend'})}"


def build_player_summaries_url(api_key, steamids):
    normalized_ids = [str(steamid or "").strip() for steamid in steamids or []]
    normalized_ids = [steamid for steamid in normalized_ids if steamid]
    return f"{PLAYER_SUMMARIES_ENDPOINT}?{urlencode({'key': api_key, 'steamids': ','.join(normalized_ids)})}"


def normalize_friend(friend):
    if not isinstance(friend, dict):
        return None
    steamid64 = str(friend.get("steamid64") or friend.get("steamid") or "").strip()
    if not steamid64:
        return None
    return {
        "steamid64": steamid64,
        "relationship": str(friend.get("relationship", "friend") or "friend"),
        "personaname": str(friend.get("personaname", "") or "").strip(),
        "profileurl": str(friend.get("profileurl", "") or "").strip(),
        "avatar": str(friend.get("avatar", "") or "").strip(),
        "avatarmedium": str(friend.get("avatarmedium", "") or "").strip(),
        "avatarfull": str(friend.get("avatarfull", "") or "").strip(),
        "personastate": _coerce_int(friend.get("personastate", 0)),
        "lastlogoff": _coerce_int(friend.get("lastlogoff", 0)),
        "gameid": str(friend.get("gameid", "") or "").strip(),
        "gameextrainfo": str(friend.get("gameextrainfo", "") or "").strip(),
        "lobbysteamid": str(friend.get("lobbysteamid", "") or "").strip(),
        "gameserverip": str(friend.get("gameserverip", "") or "").strip(),
        "gameserversteamid": str(
            friend.get("gameserversteamid", "") or ""
        ).strip(),
    }


def normalize_friends(friends):
    normalized = []
    seen = set()
    for friend in friends or []:
        item = normalize_friend(friend)
        if not item or item["steamid64"] in seen:
            continue
        seen.add(item["steamid64"])
        normalized.append(item)
    return normalized


def parse_friend_list_payload(payload):
    friends_list = payload.get("friendslist") if isinstance(payload, dict) else None
    if not isinstance(friends_list, dict):
        raise FriendsListUnavailableError("Steam friend list is private or unavailable")
    friends = friends_list.get("friends", [])
    if not isinstance(friends, list):
        raise FriendsListUnavailableError("Steam returned an invalid friend list")
    return normalize_friends(friends)


def parse_player_summaries_payload(payload):
    response = payload.get("response", {}) if isinstance(payload, dict) else {}
    players = response.get("players", []) if isinstance(response, dict) else []
    return normalize_friends(players if isinstance(players, list) else [])


def merge_friend_summaries(friend_records, player_summaries):
    summaries_by_id = {item["steamid64"]: item for item in normalize_friends(player_summaries)}
    merged = []
    for friend in normalize_friends(friend_records):
        summary = summaries_by_id.get(friend["steamid64"], {})
        merged.append(
            {
                **friend,
                **{
                    key: value
                    for key, value in summary.items()
                    if key != "relationship" and value not in {"", 0}
                },
            }
        )
    return merged


def fetch_friends(api_key, steamid64, http_get, timeout=3, batch_size=PLAYER_SUMMARIES_BATCH_SIZE):
    api_key = str(api_key or "").strip()
    steamid64 = str(steamid64 or "").strip()
    if not api_key or not steamid64:
        raise ValueError("Missing Steam API credentials")

    try:
        friend_payload = http_get_json(
            http_get,
            build_friend_list_url(api_key, steamid64),
            timeout=timeout,
        )
    except Exception as error:
        error_text = str(error or "").upper()
        if "HTTP 401" in error_text or "HTTP 403" in error_text:
            raise FriendsListUnavailableError(
                "Steam friend list is private or unavailable"
            ) from error
        raise
    friend_records = parse_friend_list_payload(friend_payload)
    if not friend_records:
        return []

    summaries = []
    steamids = [friend["steamid64"] for friend in friend_records]
    batch_size = max(1, min(int(batch_size or PLAYER_SUMMARIES_BATCH_SIZE), PLAYER_SUMMARIES_BATCH_SIZE))
    for offset in range(0, len(steamids), batch_size):
        batch = steamids[offset : offset + batch_size]
        payload = http_get_json(
            http_get,
            build_player_summaries_url(api_key, batch),
            timeout=timeout,
        )
        summaries.extend(parse_player_summaries_payload(payload))
    return merge_friend_summaries(friend_records, summaries)


def friend_presence_group(friend):
    if str((friend or {}).get("gameid", "") or "").strip() or str(
        (friend or {}).get("gameextrainfo", "") or ""
    ).strip():
        return "playing"
    state = _coerce_int((friend or {}).get("personastate", 0))
    if state in {1, 5, 6}:
        return "online"
    if state in {2, 3, 4}:
        return "away"
    return "offline"


def steamid64_to_accountid(steamid64):
    try:
        return int(str(steamid64 or "").strip()) & 0xFFFFFFFF
    except (TypeError, ValueError):
        return 0


def is_favorite_friend(friend, favorite_accountids):
    accountid = steamid64_to_accountid((friend or {}).get("steamid64"))
    favorites = favorite_accountids or ()
    return bool(accountid and accountid in favorites)


def friend_matches(friend, search_term):
    query = str(search_term or "").strip().casefold()
    if not query:
        return True
    fields = (
        friend.get("personaname", ""),
        friend.get("gameextrainfo", ""),
        friend.get("steamid64", ""),
    )
    return any(query in str(value or "").casefold() for value in fields)


def sort_friends(friends, search_term="", favorite_accountids=None):
    query = str(search_term or "").strip().casefold()
    favorite_accountids = set(favorite_accountids or ())
    group_rank = {"playing": 0, "online": 1, "away": 2, "offline": 3}

    def search_rank(friend):
        if not query:
            return 0
        name = str(friend.get("personaname", "") or "").casefold()
        game = str(friend.get("gameextrainfo", "") or "").casefold()
        steamid64 = str(friend.get("steamid64", "") or "")
        if name == query:
            return 0
        if name.startswith(query):
            return 1
        if query in name:
            return 2
        if game.startswith(query):
            return 3
        if query in game:
            return 4
        if query in steamid64:
            return 5
        return 6

    matches = [friend for friend in normalize_friends(friends) if friend_matches(friend, query)]
    def sort_key(friend):
        presence = friend_presence_group(friend)
        favorite_rank = (
            0
            if presence != "offline"
            and is_favorite_friend(friend, favorite_accountids)
            else 1
        )
        return (
            search_rank(friend),
            favorite_rank,
            group_rank[presence],
            str(friend.get("personaname", "") or friend["steamid64"]).casefold(),
        )

    return sorted(matches, key=sort_key)


def group_playing_friends_by_app(friends):
    playing_by_app = {}
    for friend in normalize_friends(friends):
        app_id = str(friend.get("gameid", "") or "").strip()
        if not app_id:
            continue
        name = str(friend.get("personaname", "") or friend["steamid64"]).strip()
        playing_by_app.setdefault(app_id, []).append(name)
    return {
        app_id: sorted(names, key=str.casefold)
        for app_id, names in playing_by_app.items()
    }


def normalize_friends_cache_payload(payload):
    if not isinstance(payload, dict):
        return None
    return {
        "last_attempt": _coerce_float(payload.get("last_attempt", 0)),
        "last_sync": _coerce_float(payload.get("timestamp", 0)),
        "steamid64": str(payload.get("steamid64", "") or "") or None,
        "items": normalize_friends(payload.get("items", [])),
        "error": str(payload.get("error", "") or ""),
    }


def build_friends_cache_payload(last_attempt, last_sync, steamid64, items, error=""):
    return {
        "last_attempt": _coerce_float(last_attempt),
        "timestamp": _coerce_float(last_sync),
        "steamid64": str(steamid64 or "") or None,
        "items": normalize_friends(items),
        "error": str(error or ""),
    }


def is_friends_cache_fresh(steamid64, cached_steamid64, last_sync, ttl_seconds, now=None):
    if not steamid64 or str(steamid64) != str(cached_steamid64 or ""):
        return False
    now = time.time() if now is None else float(now)
    return _coerce_float(last_sync) > 0 and now - _coerce_float(last_sync) < float(ttl_seconds)
