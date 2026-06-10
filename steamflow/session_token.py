import base64
import ctypes
import json
import msvcrt
import os
import re
import time
from pathlib import Path

from .os_integration import (
    STEAM_GAMES_URI,
    build_steam_openurl_uri,
    open_uri as open_os_uri,
)
from .secure_storage import (
    DATA_BLOB,
    build_data_blob,
    delete_secure_files,
    protect_dpapi_bytes,
    read_protected_text,
    unprotect_dpapi_bytes,
    write_protected_text,
)


STEAM_SESSION_TOKEN_DPAPI_ENTROPY = b"SteamFlow-DownloadControl-v1"
STEAM_SESSION_TOKEN_DIR_NAME = "download_control_tokens"
STEAM_STORE_ORIGIN = "https://store.steampowered.com"
STEAM_ACCOUNT_PREFERENCES_URL = "https://store.steampowered.com/account/preferences"
STEAM_ACCOUNT_PREFERENCES_URI = build_steam_openurl_uri(STEAM_ACCOUNT_PREFERENCES_URL)
WEBAPI_TOKEN_PATTERN = re.compile(rb'"webapi_token"\s*:\s*"([^"]+)"')
HTML_ESCAPED_WEBAPI_TOKEN_PATTERN = re.compile(rb'&quot;webapi_token&quot;\s*:\s*&quot;([^&"]+)&quot;')
LOYALTY_WEBAPI_TOKEN_PATTERN = re.compile(rb'"loyalty_webapi_token"\s*:\s*"([^"]+)"')
ACCESS_TOKEN_QUERY_PATTERN = re.compile(rb'access_token=([A-Za-z0-9\-_]+\.[A-Za-z0-9\-_]+\.[A-Za-z0-9\-_]+)')
CACHE_SCAN_CHUNK_SIZE = 1024 * 1024
CACHE_SCAN_OVERLAP_SIZE = 8192
HTMLCACHE_REFRESH_TIMEOUT_SECONDS = 4.0
HTMLCACHE_REFRESH_POLL_INTERVAL_SECONDS = 0.25
GENERIC_READ = 0x80000000
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
FILE_SHARE_DELETE = 0x00000004
OPEN_EXISTING = 3
FILE_ATTRIBUTE_NORMAL = 0x00000080
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

# backward-compatible names for existing token files and imports
DOWNLOAD_CONTROL_DPAPI_ENTROPY = STEAM_SESSION_TOKEN_DPAPI_ENTROPY
DOWNLOAD_CONTROL_TOKEN_DIR_NAME = STEAM_SESSION_TOKEN_DIR_NAME


def _build_data_blob(data):
    return build_data_blob(data)


def _open_file_shared_read(path):
    handle = ctypes.windll.kernel32.CreateFileW(
        str(path),
        GENERIC_READ,
        FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
        None,
        OPEN_EXISTING,
        FILE_ATTRIBUTE_NORMAL,
        None,
    )
    if handle == INVALID_HANDLE_VALUE:
        raise ctypes.WinError()

    fd = None
    try:
        fd = msvcrt.open_osfhandle(handle, os.O_RDONLY)
        handle = None
        file_obj = os.fdopen(fd, "rb")
        fd = None
        return file_obj
    except Exception:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
        if handle not in (None, INVALID_HANDLE_VALUE):
            ctypes.windll.kernel32.CloseHandle(handle)
        raise


def protect_steam_session_token(raw_bytes):
    return protect_dpapi_bytes(raw_bytes, STEAM_SESSION_TOKEN_DPAPI_ENTROPY)


def unprotect_steam_session_token(protected_bytes):
    return unprotect_dpapi_bytes(protected_bytes, STEAM_SESSION_TOKEN_DPAPI_ENTROPY)


protect_download_token = protect_steam_session_token
unprotect_download_token = unprotect_steam_session_token


def _decode_base64url_segment(value):
    normalized = str(value or "").strip()
    if not normalized:
        return b""
    normalized += "=" * (-len(normalized) % 4)
    return base64.urlsafe_b64decode(normalized.encode("ascii", errors="ignore"))


def decode_steam_jwt_payload(token):
    parts = str(token or "").strip().split(".")
    if len(parts) < 2:
        return {}
    try:
        payload_bytes = _decode_base64url_segment(parts[1])
        payload = json.loads(payload_bytes.decode("utf-8", errors="ignore"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def token_matches_steamid(payload, steamid64):
    return str(payload.get("sub", "") or "").strip() == str(steamid64 or "").strip()


def token_is_expired(payload, now=None):
    if not isinstance(payload, dict):
        return True
    now = int(time.time() if now is None else now)
    try:
        exp = int(payload.get("exp", 0) or 0)
    except (TypeError, ValueError):
        exp = 0
    return exp <= now


def extract_webapi_tokens_from_bytes(data):
    if not data:
        return []
    matches = []
    matches.extend(WEBAPI_TOKEN_PATTERN.findall(data))
    matches.extend(HTML_ESCAPED_WEBAPI_TOKEN_PATTERN.findall(data))
    matches.extend(LOYALTY_WEBAPI_TOKEN_PATTERN.findall(data))
    matches.extend(ACCESS_TOKEN_QUERY_PATTERN.findall(data))
    tokens = []
    seen_tokens = set()
    for match in matches:
        token = match.decode("utf-8", errors="ignore").strip()
        if token and token not in seen_tokens:
            seen_tokens.add(token)
            tokens.append(token)
    return tokens


def scan_cache_file_for_webapi_tokens(cache_file_path):
    cache_file_path = Path(cache_file_path)
    if not cache_file_path.exists():
        return []

    found_tokens = []
    seen_tokens = set()
    overlap = b""
    try:
        with _open_file_shared_read(cache_file_path) as file_obj:
            while True:
                chunk = file_obj.read(CACHE_SCAN_CHUNK_SIZE)
                if not chunk:
                    break
                buffer = overlap + chunk
                for token in extract_webapi_tokens_from_bytes(buffer):
                    if token not in seen_tokens:
                        seen_tokens.add(token)
                        found_tokens.append(token)
                overlap = buffer[-CACHE_SCAN_OVERLAP_SIZE:]
    except OSError:
        return []
    return found_tokens


def get_htmlcache_cache_data_dir(localappdata=None):
    localappdata = str(localappdata or os.environ.get("LOCALAPPDATA", "")).strip()
    if not localappdata:
        return None
    cache_dir = Path(localappdata) / "Steam" / "htmlcache" / "Default" / "Cache" / "Cache_Data"
    return cache_dir if cache_dir.exists() else None


def get_htmlcache_cache_data_files(localappdata=None, min_mtime=0):
    cache_dir = get_htmlcache_cache_data_dir(localappdata=localappdata)
    if not cache_dir:
        return []

    candidates = []
    for pattern in ("data_*", "f_*"):
        for path in cache_dir.glob(pattern):
            try:
                stat_result = path.stat()
            except OSError:
                continue
            if min_mtime and stat_result.st_mtime < float(min_mtime):
                continue
            candidates.append((stat_result.st_mtime, path))

    candidates.sort(key=lambda item: item[0], reverse=True)
    return [path for _mtime, path in candidates]


def collect_htmlcache_webapi_tokens(localappdata=None, min_mtime=0):
    found_tokens = []
    seen_tokens = set()
    for cache_file_path in get_htmlcache_cache_data_files(localappdata=localappdata, min_mtime=min_mtime):
        for token in scan_cache_file_for_webapi_tokens(cache_file_path):
            if token not in seen_tokens:
                seen_tokens.add(token)
                found_tokens.append(token)
    return found_tokens


def select_best_webapi_token(tokens, steamid64, now=None):
    now = int(time.time() if now is None else now)
    candidates = []
    for token in tokens:
        payload = decode_steam_jwt_payload(token)
        if not token_matches_steamid(payload, steamid64):
            continue
        if token_is_expired(payload, now=now):
            continue
        try:
            exp_value = int(payload.get("exp", 0) or 0)
        except (TypeError, ValueError):
            exp_value = 0
        try:
            iat_value = int(payload.get("iat", 0) or 0)
        except (TypeError, ValueError):
            iat_value = 0
        candidates.append((exp_value, iat_value, token))
    if not candidates:
        return ""
    candidates.sort(reverse=True)
    return candidates[0][2]


def get_steam_session_token_paths(secure_settings_dir, steamid64):
    steamid64 = str(steamid64 or "").strip()
    token_dir = Path(secure_settings_dir) / STEAM_SESSION_TOKEN_DIR_NAME
    token_dir.mkdir(parents=True, exist_ok=True)
    return (
        token_dir / f"{steamid64}.bin",
        token_dir / f"{steamid64}.meta.json",
    )


get_download_token_paths = get_steam_session_token_paths


def delete_saved_steam_session_token(secure_settings_dir, steamid64):
    token_path, metadata_path = get_steam_session_token_paths(secure_settings_dir, steamid64)
    delete_secure_files(token_path, metadata_path)


delete_saved_download_token = delete_saved_steam_session_token


def save_steam_session_token(secure_settings_dir, token, source="htmlcache"):
    payload = decode_steam_jwt_payload(token)
    steamid64 = str(payload.get("sub", "") or "").strip()
    if not steamid64:
        raise ValueError("Token does not include a SteamID")

    token_path, metadata_path = get_steam_session_token_paths(secure_settings_dir, steamid64)
    write_protected_text(
        token_path,
        token,
        STEAM_SESSION_TOKEN_DPAPI_ENTROPY,
        protect_bytes=protect_dpapi_bytes,
    )
    metadata = {
        "steamid64": steamid64,
        "exp": payload.get("exp"),
        "iat": payload.get("iat"),
        "jti": payload.get("jti"),
        "source": source,
        "saved_at": int(time.time()),
    }
    with open(metadata_path, "w", encoding="utf-8") as file_obj:
        json.dump(metadata, file_obj, indent=2)
    return metadata


save_download_token = save_steam_session_token


def load_saved_steam_session_token(secure_settings_dir, steamid64, now=None):
    token_path, metadata_path = get_steam_session_token_paths(secure_settings_dir, steamid64)
    if not token_path.exists():
        return ""

    try:
        token = read_protected_text(
            token_path,
            STEAM_SESSION_TOKEN_DPAPI_ENTROPY,
            unprotect_bytes=unprotect_dpapi_bytes,
        )
    except Exception:
        delete_saved_steam_session_token(secure_settings_dir, steamid64)
        return ""

    payload = decode_steam_jwt_payload(token)
    if not token_matches_steamid(payload, steamid64) or token_is_expired(payload, now=now):
        delete_saved_steam_session_token(secure_settings_dir, steamid64)
        return ""

    if metadata_path.exists():
        try:
            with open(metadata_path, "r", encoding="utf-8") as file_obj:
                metadata = json.load(file_obj)
            if str(metadata.get("steamid64", "") or "").strip() != str(steamid64):
                delete_saved_steam_session_token(secure_settings_dir, steamid64)
                return ""
        except Exception:
            pass

    return token


load_saved_download_token = load_saved_steam_session_token


class SteamSessionTokenProvider:
    def __init__(
        self,
        secure_settings_dir,
        steamid64,
        logger=None,
        validate_token=None,
        open_uri=None,
        sleep=None,
    ):
        self.secure_settings_dir = Path(secure_settings_dir)
        self.steamid64 = str(steamid64 or "").strip()
        self.logger = logger
        self.validate_token = validate_token
        self.open_uri = open_uri or open_os_uri
        self.sleep = sleep or time.sleep

    def _is_valid_for_consumer(self, token):
        if not token:
            return False
        if not self.validate_token:
            return True
        try:
            self.validate_token(token)
            return True
        except Exception:
            return False

    def load_saved_token(self, now=None):
        return load_saved_steam_session_token(self.secure_settings_dir, self.steamid64, now=now)

    def save_token(self, token, source="htmlcache"):
        return save_steam_session_token(self.secure_settings_dir, token, source=source)

    def delete_saved_token(self):
        delete_saved_steam_session_token(self.secure_settings_dir, self.steamid64)

    def select_htmlcache_token(self, min_mtime=0):
        tokens = collect_htmlcache_webapi_tokens(min_mtime=min_mtime)
        return select_best_webapi_token(tokens, self.steamid64)

    def _use_token_if_valid(self, token, source):
        if not token:
            return ""
        if self._is_valid_for_consumer(token):
            self.save_token(token, source=source)
            return token
        return ""

    def get_saved_or_htmlcache_token(self):
        token = self.load_saved_token()
        if token:
            if self._is_valid_for_consumer(token):
                return token
            self.delete_saved_token()

        token = self.select_htmlcache_token()
        return self._use_token_if_valid(token, source="htmlcache")

    def trigger_steam_htmlcache_refresh(self):
        self.open_uri(STEAM_ACCOUNT_PREFERENCES_URI)

    def return_to_steam_library(self):
        try:
            self.open_uri(STEAM_GAMES_URI)
        except Exception:
            pass

    def refresh_from_steam_htmlcache(self, refresh_wait_seconds=HTMLCACHE_REFRESH_TIMEOUT_SECONDS):
        cached_token = self.get_saved_or_htmlcache_token()
        if cached_token:
            return cached_token

        refresh_started_at = time.time()
        refresh_timeout_seconds = max(
            HTMLCACHE_REFRESH_POLL_INTERVAL_SECONDS,
            float(refresh_wait_seconds or 0),
        )
        refresh_attempts = max(
            1,
            int(refresh_timeout_seconds / HTMLCACHE_REFRESH_POLL_INTERVAL_SECONDS) + 1,
        )
        token = ""
        self.trigger_steam_htmlcache_refresh()
        try:
            for attempt in range(refresh_attempts):
                token = self.select_htmlcache_token(min_mtime=refresh_started_at - 2)
                token = self._use_token_if_valid(token, source="account_preferences")
                if token:
                    break
                if attempt + 1 < refresh_attempts:
                    self.sleep(HTMLCACHE_REFRESH_POLL_INTERVAL_SECONDS)
        finally:
            self.return_to_steam_library()

        if token:
            if self.logger:
                self.logger.info("Saved refreshed Steam session token for %s", self.steamid64)
            return token

        token = self.select_htmlcache_token()
        token = self._use_token_if_valid(token, source="htmlcache")
        if token:
            if self.logger:
                self.logger.info("Saved Steam session token from existing htmlcache for %s", self.steamid64)
            return token

        raise RuntimeError(f"No matching Steam webapi_token found for {self.steamid64}")
