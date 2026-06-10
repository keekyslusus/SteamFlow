import os
from pathlib import Path

import shutil
import vdf


STEAMID64_OFFSET = 76561197960265728


def get_loginusers_path(steam_path):
    if not steam_path:
        return None
    path = Path(steam_path) / "config" / "loginusers.vdf"
    return path if path.exists() else None


def get_loginusers_backup_path(loginusers_path):
    if not loginusers_path:
        return None
    loginusers_path = Path(loginusers_path)
    return loginusers_path.with_name(f"{loginusers_path.name}_last")


def normalize_loginusers_data(parsed):
    normalized = parsed if isinstance(parsed, dict) else {}
    users = normalized.get("users")
    if not isinstance(users, dict):
        normalized["users"] = {}
    return normalized


def load_loginusers_file(loginusers_path, vdf_loader=None):
    vdf_loader = vdf_loader or vdf.load
    with open(loginusers_path, "r", encoding="utf-8", errors="ignore") as file_obj:
        return normalize_loginusers_data(vdf_loader(file_obj))


def save_loginusers_file(loginusers_path, data, backup_path=None, vdf_dumper=None, copy_file=None, sync=False):
    loginusers_path = Path(loginusers_path)
    backup_path = Path(backup_path) if backup_path else get_loginusers_backup_path(loginusers_path)
    temp_path = loginusers_path.with_name(f"{loginusers_path.name}.tmp")
    vdf_dumper = vdf_dumper or vdf.dump
    copy_file = copy_file or shutil.copy2

    if backup_path and loginusers_path.exists():
        copy_file(loginusers_path, backup_path)

    with open(temp_path, "w", encoding="utf-8", newline="\n") as file_obj:
        vdf_dumper(data, file_obj, pretty=True)
        if sync:
            file_obj.flush()
            os.fsync(file_obj.fileno())
    temp_path.replace(loginusers_path)


def get_steam_account_label(account_data):
    if not isinstance(account_data, dict):
        return "Steam account"
    return (
        str(account_data.get("persona_name", "") or "").strip()
        or str(account_data.get("account_name", "") or "").strip()
        or str(account_data.get("steamid64", "") or "").strip()
        or "Steam account"
    )


def normalize_loginuser_account(steamid64, raw_user_data, avatar_path=None):
    steamid64 = str(steamid64 or "").strip()
    if not steamid64.isdigit():
        return None

    user_data = raw_user_data if isinstance(raw_user_data, dict) else {}
    try:
        timestamp = int(user_data.get("Timestamp", 0) or 0)
    except (TypeError, ValueError):
        timestamp = 0

    account = {
        "steamid64": steamid64,
        "account_name": str(user_data.get("AccountName", "") or "").strip(),
        "persona_name": str(user_data.get("PersonaName", "") or "").strip(),
        "remember_password": str(user_data.get("RememberPassword", "0")).strip() == "1",
        "allow_auto_login": str(user_data.get("AllowAutoLogin", "0")).strip() == "1",
        "most_recent": str(user_data.get("MostRecent", "0")).strip() == "1",
        "timestamp": timestamp,
        "icon_path": str(avatar_path) if avatar_path else None,
    }
    account["label"] = get_steam_account_label(account)
    return account


def sort_steam_accounts(accounts):
    return sorted(
        accounts,
        key=lambda account: (
            not account["most_recent"],
            -account["timestamp"],
            account["label"].lower(),
        ),
    )


def get_known_steam_accounts(loginusers_data, avatar_path_resolver=None):
    users = normalize_loginusers_data(loginusers_data).get("users", {})
    accounts = []
    for steamid64, raw_user_data in users.items():
        avatar_path = avatar_path_resolver(steamid64) if avatar_path_resolver else None
        account = normalize_loginuser_account(steamid64, raw_user_data, avatar_path=avatar_path)
        if account:
            accounts.append(account)
    return sort_steam_accounts(accounts)


def set_loginusers_autologin_account_data(loginusers_data, target_steamid64):
    target_steamid64 = str(target_steamid64 or "").strip()
    data = normalize_loginusers_data(loginusers_data)
    users = data.get("users", {})
    if not isinstance(users, dict) or target_steamid64 not in users:
        return None

    for current_steamid64, raw_user_data in list(users.items()):
        user_data = raw_user_data if isinstance(raw_user_data, dict) else {}
        user_data["MostRecent"] = "1" if current_steamid64 == target_steamid64 else "0"
        if current_steamid64 == target_steamid64:
            user_data["AllowAutoLogin"] = "1"
            user_data["RememberPassword"] = "1"
        users[current_steamid64] = user_data

    normalized_user_data = users.get(target_steamid64, {})
    return normalized_user_data if isinstance(normalized_user_data, dict) else {}


def get_steam_user_details(loginusers_data, steamid64):
    steamid64 = str(steamid64 or "").strip()
    if not steamid64:
        return {}
    user_data = normalize_loginusers_data(loginusers_data).get("users", {}).get(steamid64, {})
    user_data = user_data if isinstance(user_data, dict) else {}
    return {
        "steamid64": steamid64,
        "account_name": user_data.get("AccountName"),
        "persona_name": user_data.get("PersonaName"),
    }


def select_last_known_steamid64(loginusers_data):
    users = normalize_loginusers_data(loginusers_data).get("users", {})
    selected_steamid64 = None
    selected_timestamp = -1
    fallback_steamid64 = None
    fallback_timestamp = -1

    for steamid64, user_data in users.items():
        steamid64 = str(steamid64 or "").strip()
        if not steamid64.isdigit():
            continue
        if not isinstance(user_data, dict):
            user_data = {}

        try:
            timestamp = int(user_data.get("Timestamp", 0) or 0)
        except (TypeError, ValueError):
            timestamp = 0

        is_most_recent = str(user_data.get("MostRecent", "0")).strip() == "1"
        if is_most_recent and timestamp >= selected_timestamp:
            selected_steamid64 = steamid64
            selected_timestamp = timestamp

        if timestamp >= fallback_timestamp:
            fallback_steamid64 = steamid64
            fallback_timestamp = timestamp

    return selected_steamid64 or fallback_steamid64


def steamid64_to_user_id(steamid64):
    steamid64 = str(steamid64 or "").strip()
    if not steamid64:
        return None
    return str(int(steamid64) - STEAMID64_OFFSET)


def user_id_to_steamid64(user_id):
    user_id = str(user_id or "").strip()
    if not user_id:
        return None
    return str(STEAMID64_OFFSET + int(user_id))
