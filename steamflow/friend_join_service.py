import json
import re
import time
from pathlib import Path
from urllib.parse import urlencode

import vdf

from .cache_utils import read_json_file, write_json_file
from .constants import STEAMFLOW_CONFIG
from .feature_health import (
    FEATURE_STEAM_FRIEND_JOIN,
    FEATURE_STEAM_SESSION_TOKEN,
    classify_feature_error,
    feature_enabled,
    record_feature_failure,
    record_feature_success,
)
from .http_client import urllib_get_json
from .local_library_service import load_appmanifest_file, load_steam_library_paths
from .profile_service import normalize_owned_games_cache_payload
from .session_token import SteamSessionTokenProvider


PLAYER_LINK_DETAILS_ENDPOINT = (
    "https://api.steampowered.com/IPlayerService/GetPlayerLinkDetails/v1/"
)
FRIEND_JOIN_CACHE_VERSION = 1


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


def _coerce_bool(value):
    if isinstance(value, str):
        return value.strip().casefold() in {"1", "true", "yes"}
    return bool(value)


def normalize_steamid64(value):
    normalized = str(value or "").strip()
    return normalized if normalized.isdigit() and int(normalized) > 0 else ""


def normalize_app_id(value):
    numeric = _coerce_int(value)
    if numeric <= 0:
        return ""
    if numeric > 0xFFFFFFFF:
        numeric &= 0xFFFFFF
    return str(numeric) if numeric > 0 else ""


def normalize_lobby_id(value):
    numeric = _coerce_int(value)
    return str(numeric) if numeric > 0 else ""


def parse_rich_presence(raw_value):
    text = str(raw_value or "")
    if not text:
        return {}
    try:
        loader = getattr(vdf, "loads", None)
        if not callable(loader):
            match = re.search(
                r'"connect"\s+"((?:[^"\\]|\\.)*)"',
                text,
                flags=re.IGNORECASE,
            )
            return {"connect": match.group(1)} if match else {}
        payload = loader(text)
    except Exception:
        return {}
    if not isinstance(payload, dict):
        return {}
    values = payload.get("rp", payload)
    if not isinstance(values, dict):
        return {}
    return {
        str(key or "").strip().casefold(): str(value or "")
        for key, value in values.items()
        if str(key or "").strip()
    }


def normalize_player_link_detail(account):
    if not isinstance(account, dict):
        return None
    public_data = account.get("public_data", {})
    private_data = account.get("private_data", {})
    if not isinstance(public_data, dict) or not isinstance(private_data, dict):
        return None
    steamid64 = normalize_steamid64(public_data.get("steamid"))
    if not steamid64:
        return None
    app_id = normalize_app_id(private_data.get("game_id"))
    rich_presence = parse_rich_presence(private_data.get("rich_presence_kv"))
    has_connect = bool(str(rich_presence.get("connect", "") or "").strip())
    lobby_id = normalize_lobby_id(private_data.get("lobby_steam_id"))
    has_lobby = bool(lobby_id)
    has_server = (
        _coerce_int(private_data.get("game_server_ip_address")) > 0
        and _coerce_int(private_data.get("game_server_port")) > 0
    )
    game_is_private = _coerce_bool(private_data.get("game_is_private"))
    detail = {
        "steamid64": steamid64,
        "app_id": app_id,
        "joinable": bool(
            app_id
            and not game_is_private
            and (has_connect or has_lobby or has_server)
        ),
        "has_connect": has_connect,
        "has_lobby": has_lobby,
        "has_server": has_server,
    }
    if lobby_id:
        detail["lobby_id"] = lobby_id
    return detail


def parse_player_link_details_payload(payload):
    response = payload.get("response", {}) if isinstance(payload, dict) else {}
    accounts = response.get("accounts", []) if isinstance(response, dict) else []
    if not isinstance(accounts, list):
        return {}
    details = {}
    for account in accounts:
        normalized = normalize_player_link_detail(account)
        if normalized:
            details[normalized["steamid64"]] = normalized
    return details


def build_player_link_details_url(access_token, steamids):
    token = str(access_token or "").strip()
    if not token:
        raise ValueError("Missing Steam session token")
    normalized_ids = [
        steamid64
        for value in steamids or ()
        for steamid64 in (normalize_steamid64(value),)
        if steamid64
    ]
    input_json = json.dumps(
        {"steamids": normalized_ids},
        separators=(",", ":"),
    )
    return f"{PLAYER_LINK_DETAILS_ENDPOINT}?{urlencode({'access_token': token, 'input_json': input_json})}"


def fetch_player_link_details(access_token, steamids, timeout=4, opener=None):
    return parse_player_link_details_payload(
        urllib_get_json(
            build_player_link_details_url(access_token, steamids),
            timeout=timeout,
            opener=opener,
        )
    )


def normalize_friend_join_cache_payload(payload):
    accounts = payload.get("accounts", {}) if isinstance(payload, dict) else {}
    if not isinstance(accounts, dict):
        return {}
    normalized_accounts = {}
    for owner_steamid64, entry in accounts.items():
        owner_id = normalize_steamid64(owner_steamid64)
        if not owner_id or not isinstance(entry, dict):
            continue
        raw_details = entry.get("details", {})
        if not isinstance(raw_details, dict):
            raw_details = {}
        details = {}
        for friend_steamid64, detail in raw_details.items():
            friend_id = normalize_steamid64(friend_steamid64)
            if not friend_id or not isinstance(detail, dict):
                continue
            app_id = normalize_app_id(detail.get("app_id"))
            detail_payload = {
                "steamid64": friend_id,
                "app_id": app_id,
                "joinable": bool(detail.get("joinable")) and bool(app_id),
                "has_connect": bool(detail.get("has_connect")),
                "has_lobby": bool(detail.get("has_lobby")),
                "has_server": bool(detail.get("has_server")),
            }
            lobby_id = normalize_lobby_id(detail.get("lobby_id"))
            if lobby_id:
                detail_payload["lobby_id"] = lobby_id
            details[friend_id] = detail_payload
        normalized_accounts[owner_id] = {
            "timestamp": _coerce_float(entry.get("timestamp")),
            "details": details,
        }
    return normalized_accounts


def build_friend_join_cache_payload(accounts):
    normalized = normalize_friend_join_cache_payload({"accounts": accounts})
    return {
        "version": FRIEND_JOIN_CACHE_VERSION,
        "accounts": {
            owner_id: {
                "timestamp": entry["timestamp"],
                "details": {
                    friend_id: dict(detail)
                    for friend_id, detail in sorted(entry["details"].items())
                },
            }
            for owner_id, entry in sorted(normalized.items())
        },
    }


def get_cached_join_details(accounts, owner_steamid64, ttl_seconds, now=None):
    owner_id = normalize_steamid64(owner_steamid64)
    entry = (accounts or {}).get(owner_id, {})
    if not isinstance(entry, dict):
        return None
    current_time = time.time() if now is None else float(now)
    timestamp = _coerce_float(entry.get("timestamp"))
    if timestamp <= 0 or current_time - timestamp >= float(ttl_seconds):
        return None
    details = entry.get("details", {})
    return dict(details) if isinstance(details, dict) else {}


def get_playing_friends(friend_items, app_id=None, only_steamid64=None):
    normalized_app_id = normalize_app_id(app_id)
    target_id = normalize_steamid64(only_steamid64)
    if app_id is not None and not normalized_app_id:
        return []
    if only_steamid64 is not None and not target_id:
        return []

    matches = []
    for friend in friend_items or ():
        if not isinstance(friend, dict):
            continue
        steamid64 = normalize_steamid64(
            friend.get("steamid64") or friend.get("steamid")
        )
        friend_app_id = normalize_app_id(friend.get("gameid"))
        if not steamid64 or not friend_app_id:
            continue
        if target_id and steamid64 != target_id:
            continue
        if normalized_app_id and friend_app_id != normalized_app_id:
            continue
        matches.append(friend)
    return matches


def get_public_join_details(friend_items):
    details = {}
    for friend in friend_items or ():
        if not isinstance(friend, dict):
            continue
        steamid64 = normalize_steamid64(
            friend.get("steamid64") or friend.get("steamid")
        )
        app_id = normalize_app_id(friend.get("gameid"))
        if not steamid64 or not app_id:
            continue
        lobby_id = normalize_lobby_id(friend.get("lobbysteamid"))
        has_lobby = bool(lobby_id)
        server_ip = str(friend.get("gameserverip", "") or "").strip()
        server_steamid = normalize_steamid64(friend.get("gameserversteamid"))
        has_server = bool(
            server_steamid
            or (
                server_ip
                and server_ip not in {"0", "0.0.0.0", "0.0.0.0:0"}
            )
        )
        detail = {
            "steamid64": steamid64,
            "app_id": app_id,
            "joinable": has_lobby or has_server,
            "has_connect": False,
            "has_lobby": has_lobby,
            "has_server": has_server,
        }
        if lobby_id:
            detail["lobby_id"] = lobby_id
        details[steamid64] = detail
    return details


def get_join_candidates(friend_items, link_details, app_id, only_steamid64=None):
    normalized_app_id = normalize_app_id(app_id)
    target_id = normalize_steamid64(only_steamid64)
    if (
        not normalized_app_id
        or (only_steamid64 is not None and not target_id)
    ):
        return []
    candidates = []
    for friend in friend_items or ():
        if not isinstance(friend, dict):
            continue
        steamid64 = normalize_steamid64(
            friend.get("steamid64") or friend.get("steamid")
        )
        if not steamid64 or (target_id and steamid64 != target_id):
            continue
        detail = (link_details or {}).get(steamid64, {})
        if (
            not isinstance(detail, dict)
            or not detail.get("joinable")
            or normalize_app_id(detail.get("app_id")) != normalized_app_id
        ):
            continue
        candidate = {
            "steamid64": steamid64,
            "name": str(
                friend.get("personaname") or friend.get("name") or steamid64
            ).strip(),
            "app_id": normalized_app_id,
        }
        lobby_id = normalize_lobby_id(detail.get("lobby_id"))
        if lobby_id:
            candidate["lobby_id"] = lobby_id
        candidates.append(candidate)
    return sorted(candidates, key=lambda item: item["name"].casefold())


def get_owned_cache_state(cache_payload, owner_steamid64, app_id, ttl_seconds, now=None):
    normalized = normalize_owned_games_cache_payload(cache_payload)
    if not normalized:
        return False
    owner_id = normalize_steamid64(owner_steamid64)
    current_time = time.time() if now is None else float(now)
    return bool(
        owner_id
        and str(normalized.get("steamid64") or "") == owner_id
        and current_time - _coerce_float(normalized.get("last_sync")) < float(ttl_seconds)
        and normalize_app_id(app_id) in normalized.get("owned_app_ids", set())
    )


def find_installed_app_path(steam_path, app_id):
    normalized_app_id = normalize_app_id(app_id)
    if not steam_path or not normalized_app_id:
        return None
    for steamapps_path in load_steam_library_paths(steam_path):
        manifest_path = Path(steamapps_path) / f"appmanifest_{normalized_app_id}.acf"
        if not manifest_path.exists():
            continue
        try:
            manifest = load_appmanifest_file(manifest_path)
        except Exception:
            continue
        state_flags = manifest.get("state_flags", {})
        install_dir = str(manifest.get("install_dir", "") or "").strip()
        install_path = Path(steamapps_path) / "common" / install_dir
        if (
            state_flags.get("is_fully_installed")
            and install_dir
            and install_path.exists()
        ):
            return install_path
    return None


def installed_app_matches_owner(steam_path, app_id, owner_steamid64):
    normalized_app_id = normalize_app_id(app_id)
    owner_id = normalize_steamid64(owner_steamid64)
    if not steam_path or not normalized_app_id or not owner_id:
        return False
    for steamapps_path in load_steam_library_paths(steam_path):
        manifest_path = Path(steamapps_path) / f"appmanifest_{normalized_app_id}.acf"
        if not manifest_path.exists():
            continue
        try:
            manifest = load_appmanifest_file(manifest_path)
        except Exception:
            continue
        state_flags = manifest.get("state_flags", {})
        install_dir = str(manifest.get("install_dir", "") or "").strip()
        install_path = Path(steamapps_path) / "common" / install_dir
        if (
            state_flags.get("is_fully_installed")
            and install_dir
            and install_path.exists()
            and normalize_steamid64(manifest.get("last_owner")) == owner_id
        ):
            return True
    return False


class FriendJoinCoordinator:
    def __init__(
        self,
        plugin_dir,
        secure_settings_dir,
        steam_path,
        logger=None,
        fetch_details=None,
        token_provider_factory=None,
        installed_path_finder=None,
        installed_owner_matcher=None,
    ):
        self.plugin_dir = Path(plugin_dir)
        self.secure_settings_dir = Path(secure_settings_dir)
        self.steam_path = Path(steam_path) if steam_path else None
        self.logger = logger
        self.fetch_details = fetch_details or fetch_player_link_details
        self.token_provider_factory = (
            token_provider_factory or SteamSessionTokenProvider
        )
        self.installed_path_finder = (
            installed_path_finder or find_installed_app_path
        )
        self.installed_owner_matcher = (
            installed_owner_matcher or installed_app_matches_owner
        )
        self.friends_cache_file = self.secure_settings_dir / "cache_friends.json"
        self.join_cache_file = (
            self.secure_settings_dir / "cache_friend_joinability.json"
        )
        self.owned_games_cache_file = self.plugin_dir / "cache_owned_games.json"
        self.feature_health_cache_file = (
            self.plugin_dir / "cache_feature_health.json"
        )

    def _log_failure(self, message):
        if self.logger:
            self.logger.exception(message)

    def _read_friend_snapshot(self):
        payload = read_json_file(self.friends_cache_file, default={})
        if not isinstance(payload, dict):
            return "", []
        owner_id = normalize_steamid64(payload.get("steamid64"))
        items = payload.get("items", [])
        return owner_id, items if isinstance(items, list) else []

    def _prerequisites_met(self, owner_id, app_id):
        try:
            if self.installed_path_finder(self.steam_path, app_id) is None:
                return False
        except Exception:
            self._log_failure(
                f"Failed to verify local Steam installation for app {app_id}"
            )
            return False
        owned_payload = read_json_file(self.owned_games_cache_file, default={})
        if get_owned_cache_state(
            owned_payload,
            owner_id,
            app_id,
            STEAMFLOW_CONFIG.cache.owned_games_cache_ttl_seconds,
        ):
            return True
        try:
            return bool(
                self.installed_owner_matcher(
                    self.steam_path,
                    app_id,
                    owner_id,
                )
            )
        except Exception:
            self._log_failure(
                f"Failed to verify local Steam ownership for app {app_id}"
            )
            return False

    def _read_cached_details(self, owner_id):
        payload = read_json_file(self.join_cache_file, default={})
        accounts = normalize_friend_join_cache_payload(payload)
        return accounts, get_cached_join_details(
            accounts,
            owner_id,
            STEAMFLOW_CONFIG.cache.friend_joinability_ttl_seconds,
        )

    def _fetch_fresh_details(self, owner_id, friend_items):
        if not feature_enabled(
            self.feature_health_cache_file,
            FEATURE_STEAM_FRIEND_JOIN,
        ) or not feature_enabled(
            self.feature_health_cache_file,
            FEATURE_STEAM_SESSION_TOKEN,
        ):
            return None
        friend_ids = [
            steamid64
            for item in friend_items
            if isinstance(item, dict)
            for steamid64 in (
                normalize_steamid64(
                    item.get("steamid64") or item.get("steamid")
                ),
            )
            if steamid64
        ]
        if not friend_ids:
            return {}
        try:
            token_provider = self.token_provider_factory(
                self.secure_settings_dir,
                owner_id,
                logger=self.logger,
            )
            access_token = token_provider.get_saved_or_htmlcache_token()
            if not access_token:
                raise RuntimeError(
                    f"No matching Steam webapi_token found for {owner_id}"
                )
            details = self.fetch_details(
                access_token,
                friend_ids,
                timeout=4,
            )
        except Exception as error:
            record_feature_failure(
                self.feature_health_cache_file,
                FEATURE_STEAM_FRIEND_JOIN,
                error,
                reason=classify_feature_error(
                    error,
                    FEATURE_STEAM_FRIEND_JOIN,
                ),
            )
            self._log_failure("Failed to refresh Steam friend joinability")
            return None

        payload = read_json_file(self.join_cache_file, default={})
        accounts = normalize_friend_join_cache_payload(payload)
        accounts[owner_id] = {
            "timestamp": time.time(),
            "details": details,
        }
        write_json_file(
            self.join_cache_file,
            build_friend_join_cache_payload(accounts),
        )
        record_feature_success(
            self.feature_health_cache_file,
            FEATURE_STEAM_FRIEND_JOIN,
        )
        return details

    def get_candidates(
        self,
        app_id,
        only_steamid64=None,
        force_refresh=False,
    ):
        normalized_app_id = normalize_app_id(app_id)
        owner_id, friend_items = self._read_friend_snapshot()
        if (
            not normalized_app_id
            or not owner_id
        ):
            return []

        presence_candidates = get_playing_friends(
            friend_items,
            normalized_app_id,
            only_steamid64=only_steamid64,
        )
        if not presence_candidates:
            return []
        if not self._prerequisites_met(owner_id, normalized_app_id):
            return []

        public_candidates = get_join_candidates(
            presence_candidates,
            get_public_join_details(presence_candidates),
            normalized_app_id,
            only_steamid64=only_steamid64,
        )
        if public_candidates:
            return public_candidates

        details = None
        if not force_refresh:
            _accounts, details = self._read_cached_details(owner_id)
        if details is None:
            details = self._fetch_fresh_details(
                owner_id,
                get_playing_friends(friend_items),
            )
        if details is None:
            return []
        return get_join_candidates(
            presence_candidates,
            details,
            normalized_app_id,
            only_steamid64=only_steamid64,
        )
