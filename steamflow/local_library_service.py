import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import vdf

from .constants import STEAMFLOW_CONFIG


@dataclass
class InstalledGamesSnapshot:
    installed_games: dict = field(default_factory=dict)
    installed_game_paths: dict = field(default_factory=dict)
    installed_game_statuses: dict = field(default_factory=dict)
    manifest_keys_in_use: set = field(default_factory=set)


def get_file_signature(path):
    try:
        stat_result = Path(path).stat()
        return (int(stat_result.st_mtime_ns), int(stat_result.st_size))
    except OSError:
        return None


def get_file_modified_time(path):
    try:
        return float(Path(path).stat().st_mtime)
    except OSError:
        return 0


def parse_manifest_int(raw_value, default=0):
    try:
        return int(raw_value)
    except (TypeError, ValueError):
        return int(default)


def parse_state_flags(raw_state_flags, config=STEAMFLOW_CONFIG):
    try:
        state_flags = int(raw_state_flags)
    except (TypeError, ValueError):
        state_flags = 0

    is_fully_installed = bool(state_flags & config.download.state_flag_fully_installed)
    is_update_paused = bool(state_flags & config.download.state_flag_update_paused)
    is_updating = bool(
        state_flags
        & (
            config.download.state_flag_update_running
            | config.download.state_flag_update_started
        )
    )
    is_update_required = bool(state_flags & config.download.state_flag_update_required)

    status_label = ""
    if is_update_paused:
        status_label = config.download.status_update_paused
    elif is_updating:
        status_label = config.download.status_updating
    elif is_update_required:
        status_label = config.download.status_update_queued if is_fully_installed else config.download.status_update_required

    return {
        "raw_value": state_flags,
        "is_visible": is_fully_installed or is_update_required or is_updating or is_update_paused,
        "label": status_label,
        "is_fully_installed": is_fully_installed,
        "is_update_required": is_update_required,
        "is_updating": is_updating,
        "is_update_paused": is_update_paused,
    }


def normalize_appmanifest_state(acf_data, config=STEAMFLOW_CONFIG):
    acf_data = acf_data if isinstance(acf_data, dict) else {}
    return {
        "app_id": str(acf_data.get("appid", "")).strip(),
        "name": acf_data.get("name"),
        "install_dir": acf_data.get("installdir"),
        "state_flags": parse_state_flags(acf_data.get("StateFlags", 0), config=config),
        "bytes_to_download": parse_manifest_int(acf_data.get("BytesToDownload", 0)),
        "bytes_downloaded": parse_manifest_int(acf_data.get("BytesDownloaded", 0)),
        "bytes_to_stage": parse_manifest_int(acf_data.get("BytesToStage", 0)),
        "bytes_staged": parse_manifest_int(acf_data.get("BytesStaged", 0)),
    }


def load_appmanifest_file(manifest_path, config=STEAMFLOW_CONFIG, vdf_loader=None):
    vdf_loader = vdf_loader or vdf.load
    with open(manifest_path, "r", encoding="utf-8", errors="ignore") as file_obj:
        acf_data = vdf_loader(file_obj).get("AppState", {})
    manifest_data = normalize_appmanifest_state(acf_data, config=config)
    manifest_data["modified_at"] = get_file_modified_time(manifest_path)
    return manifest_data


def cleanup_cache_keys(cache, keys_in_use):
    stale_keys = [
        cache_key
        for cache_key in cache
        if cache_key not in keys_in_use
    ]
    for cache_key in stale_keys:
        cache.pop(cache_key, None)
    return bool(stale_keys)


def parse_libraryfolders_steamapps_paths(libraryfolders_data, existing_paths=None):
    existing_paths = list(existing_paths or [])
    library_paths = list(existing_paths)
    folders = libraryfolders_data.get("libraryfolders", {}) if isinstance(libraryfolders_data, dict) else {}
    if not isinstance(folders, dict):
        return library_paths

    for key, folder_info in folders.items():
        if not str(key).isdigit() or not isinstance(folder_info, dict) or "path" not in folder_info:
            continue
        alt_path = Path(folder_info["path"]) / "steamapps"
        if alt_path.exists() and alt_path not in library_paths:
            library_paths.append(alt_path)
    return library_paths


def load_steam_library_paths(steam_path, vdf_loader=None):
    if not steam_path:
        return []

    steam_path = Path(steam_path)
    main_library_path = steam_path / "steamapps"
    library_paths = []
    if main_library_path.exists():
        library_paths.append(main_library_path)

    library_folders_vdf_path = main_library_path / "libraryfolders.vdf"
    if not library_folders_vdf_path.exists():
        return library_paths

    vdf_loader = vdf_loader or vdf.load
    with open(library_folders_vdf_path, "r", encoding="utf-8") as file_obj:
        data = vdf_loader(file_obj)
    return parse_libraryfolders_steamapps_paths(data, existing_paths=library_paths)


def get_latest_existing_path(candidates):
    existing_candidates = [Path(path) for path in candidates if path and Path(path).exists()]
    if not existing_candidates:
        return None
    return max(existing_candidates, key=lambda path: path.stat().st_mtime)


def resolve_localconfig_path(steam_path, active_user_id=None):
    if not steam_path:
        return None

    userdata_path = Path(steam_path) / "userdata"
    if not userdata_path.exists():
        return None

    active_user_id = str(active_user_id or "").strip()
    if active_user_id:
        active_user_config = userdata_path / active_user_id / "config" / "localconfig.vdf"
        if active_user_config.exists():
            return active_user_config

    return get_latest_existing_path(userdata_path.glob("*/config/localconfig.vdf"))


def resolve_hidden_collections_path(steam_path, active_user_id=None, localconfig_path=None):
    if localconfig_path:
        candidate = Path(localconfig_path).parent / "cloudstorage" / "cloud-storage-namespace-1.json"
        if candidate.exists():
            return candidate

    if not steam_path:
        return None

    userdata_path = Path(steam_path) / "userdata"
    if not userdata_path.exists():
        return None

    active_user_id = str(active_user_id or "").strip()
    if active_user_id:
        active_user_cloudstorage = (
            userdata_path
            / active_user_id
            / "config"
            / "cloudstorage"
            / "cloud-storage-namespace-1.json"
        )
        if active_user_cloudstorage.exists():
            return active_user_cloudstorage

    return get_latest_existing_path(userdata_path.glob("*/config/cloudstorage/cloud-storage-namespace-1.json"))


def load_vdf_file(path, vdf_loader=None):
    vdf_loader = vdf_loader or vdf.load
    with open(path, "r", encoding="utf-8", errors="ignore") as file_obj:
        data = vdf_loader(file_obj)
    return data if isinstance(data, dict) else {}


def get_localconfig_steam_data(localconfig_root):
    steam_data = (
        (localconfig_root or {})
        .get("UserLocalConfigStore", {})
        .get("Software", {})
        .get("Valve", {})
        .get("Steam", {})
    )
    return steam_data if isinstance(steam_data, dict) else {}


def get_localconfig_friends_data(localconfig_root):
    user_config = (localconfig_root or {}).get("UserLocalConfigStore", {})
    friends_data = user_config.get("friends") or user_config.get("Friends")
    return friends_data if isinstance(friends_data, dict) else {}


def parse_active_persona_state(localconfig_text, active_user_id):
    active_user_id = str(active_user_id or "").strip()
    if not active_user_id or not localconfig_text:
        return None

    pattern = rf'"FriendStoreLocalPrefs_{re.escape(active_user_id)}"\s+"{{\\\"ePersonaState\\\":\s*(\d+)'
    match = re.search(pattern, localconfig_text)
    if not match:
        return None
    return int(match.group(1))


def parse_hidden_app_ids_data(data):
    hidden_app_ids = set()
    if not isinstance(data, list):
        return hidden_app_ids

    for entry in data:
        if not isinstance(entry, list) or len(entry) < 2:
            continue
        entry_key, entry_payload = entry[0], entry[1]
        if entry_key != "user-collections.hidden" or not isinstance(entry_payload, dict):
            continue

        raw_value = entry_payload.get("value")
        if not raw_value:
            break

        collection_data = json.loads(raw_value)
        added = collection_data.get("added", [])
        removed = {str(app_id) for app_id in collection_data.get("removed", [])}
        hidden_app_ids = {
            str(app_id)
            for app_id in added
            if str(app_id) not in removed
        }
        break
    return hidden_app_ids


def load_hidden_app_ids_file(hidden_collections_path):
    with open(hidden_collections_path, "r", encoding="utf-8") as file_obj:
        return parse_hidden_app_ids_data(json.load(file_obj))


def extract_localconfig_app_stats(steam_data):
    apps = steam_data.get("apps") or steam_data.get("Apps") or {}
    if not isinstance(apps, dict):
        apps = {}

    playtimes = {}
    last_played_timestamps = {}
    for app_id, app_data in apps.items():
        if not isinstance(app_data, dict):
            continue

        playtime = app_data.get("Playtime")
        try:
            if playtime is not None:
                playtimes[str(app_id)] = int(playtime)
        except (TypeError, ValueError):
            pass

        last_played = app_data.get("LastPlayed")
        if last_played is None:
            continue
        try:
            last_played_timestamps[str(app_id)] = int(last_played)
        except (TypeError, ValueError):
            continue

    return playtimes, last_played_timestamps


def build_installed_game_record(steamapps_path, manifest_data, status_label="", blacklist=None):
    blacklist = {str(app_id) for app_id in (blacklist or set())}
    manifest_data = manifest_data if isinstance(manifest_data, dict) else {}
    app_id = str(manifest_data.get("app_id", "") or "").strip()
    name = manifest_data.get("name")
    install_dir = manifest_data.get("install_dir")
    state_flags = manifest_data.get("state_flags") if isinstance(manifest_data.get("state_flags"), dict) else {}

    if not app_id or not name or app_id in blacklist:
        return None
    if not state_flags.get("is_visible"):
        return None

    record = {
        "app_id": app_id,
        "name": name,
        "status": str(status_label or ""),
        "install_path": "",
    }
    if install_dir:
        record["install_path"] = str(Path(steamapps_path) / "common" / install_dir)
    return record


def collect_installed_games_snapshot(
    steamapps_paths,
    load_manifest_data,
    derive_status_label,
    blacklist=None,
    log_exception=None,
):
    snapshot = InstalledGamesSnapshot()
    blacklist = {str(app_id) for app_id in (blacklist or set())}

    for steamapps_path in steamapps_paths:
        steamapps_path = Path(steamapps_path)
        try:
            if not steamapps_path.exists():
                continue
            for acf_file in steamapps_path.glob("appmanifest_*.acf"):
                snapshot.manifest_keys_in_use.add(str(acf_file))
                try:
                    manifest_data = load_manifest_data(acf_file)
                    if not manifest_data:
                        continue
                    state_flags = manifest_data.get("state_flags") or {}
                    app_id = str(manifest_data.get("app_id", "") or "").strip()
                    status_label = derive_status_label(app_id, state_flags, manifest_data)
                    record = build_installed_game_record(
                        steamapps_path,
                        manifest_data,
                        status_label=status_label,
                        blacklist=blacklist,
                    )
                    if not record:
                        continue
                    snapshot.installed_games[record["app_id"]] = record["name"]
                    snapshot.installed_game_statuses[record["app_id"]] = record["status"]
                    if record["install_path"]:
                        snapshot.installed_game_paths[record["app_id"]] = record["install_path"]
                except Exception:
                    if log_exception:
                        log_exception(f"Failed to process manifest: {acf_file}")
        except Exception:
            if log_exception:
                log_exception(f"Failed to scan Steam library: {steamapps_path}")

    return snapshot
