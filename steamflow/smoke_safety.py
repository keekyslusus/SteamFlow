import fnmatch
import json
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path


SAFETY_CACHE_TTL_SECONDS = 7 * 24 * 60 * 60
INSTALL_RESCAN_TTL_SECONDS = 60 * 60
MAX_SIGNALS = 1
ANTI_CHEAT_MARKERS = (
    ("file", "start_protected_game.exe", "Easy Anti-Cheat"),
    ("directory", "EasyAntiCheat", "Easy Anti-Cheat"),
    ("directory", "EasyAntiCheat_EOS", "Easy Anti-Cheat"),
    ("directory", "BattlEye", "BattlEye"),
    ("file_glob", "BEService*.exe", "BattlEye"),
    ("file_glob", "BEClient*.dll", "BattlEye"),
    ("file", "EAAntiCheat.GameServiceLauncher.dll", "EA AntiCheat"),
    ("file", "EAAntiCheat.GameServiceLauncher.exe", "EA AntiCheat"),
    ("file", "EAAntiCheat.Installer.exe", "EA AntiCheat"),
    ("file", "NeacClient.exe", "NetEase AntiCheat Experts"),
    ("file", "FragNeacClient.exe", "NetEase AntiCheat Experts"),
    ("file", "NSHNeacClient.exe", "NetEase AntiCheat Experts"),
    ("directory", "AntiCheatExpert", "AntiCheatExpert"),
    ("file", "ACE-Service64.exe", "AntiCheatExpert"),
    ("file", "ACE-Setup64.exe", "AntiCheatExpert"),
    ("file", "AntiCheatInstaller.exe", "AnyBrain AntiCheat"),
)
_CACHE_LOCK = threading.Lock()


@dataclass(frozen=True)
class SmokeSafetyResult:
    risk: bool
    signals: tuple
    scanned_at: float
    install_path: str
    path_sig: tuple


def get_path_signature(install_path):
    path = Path(install_path)
    try:
        stat_result = path.stat()
    except OSError:
        return ()
    return (int(stat_result.st_mtime_ns), int(stat_result.st_size))


def scan_anti_cheat(install_path, now=None):
    root = Path(install_path)
    if not root.is_dir():
        raise FileNotFoundError(str(root))

    labels = []
    label_set = set()
    for current_root, directory_names, file_names in os.walk(root, followlinks=False):
        lower_directories = {name.lower() for name in directory_names}
        lower_files = {name.lower() for name in file_names}
        for marker_type, marker, label in ANTI_CHEAT_MARKERS:
            found = False
            if marker_type == "directory":
                found = marker.lower() in lower_directories
            elif marker_type == "file":
                found = marker.lower() in lower_files
            else:
                found = any(fnmatch.fnmatch(name, marker.lower()) for name in lower_files)
            if found and label not in label_set:
                label_set.add(label)
                labels.append(label)
                if len(labels) >= MAX_SIGNALS:
                    break
        if len(labels) >= MAX_SIGNALS:
            break

    return SmokeSafetyResult(
        risk=bool(labels),
        signals=tuple(labels),
        scanned_at=float(time.time() if now is None else now),
        install_path=str(root),
        path_sig=get_path_signature(root),
    )


def load_safety_cache(cache_file):
    path = Path(cache_file)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save_safety_cache(cache_file, cache):
    path = Path(cache_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(
        path.suffix + f".{os.getpid()}.{threading.get_ident()}.tmp"
    )
    try:
        temporary_path.write_text(
            json.dumps(cache, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary_path.replace(path)
    finally:
        if temporary_path.exists():
            try:
                temporary_path.unlink()
            except OSError:
                pass


def _entry_matches(entry, install_path, now, ttl_seconds):
    if not isinstance(entry, dict):
        return False
    if str(entry.get("install_path", "")) != str(Path(install_path)):
        return False
    if tuple(entry.get("path_sig", ())) != get_path_signature(install_path):
        return False
    try:
        scanned_at = float(entry.get("scanned_at", 0))
    except (TypeError, ValueError):
        return False
    return scanned_at > 0 and (now - scanned_at) <= ttl_seconds


def get_cached_safety(cache_file, app_id, install_path, ttl_seconds=SAFETY_CACHE_TTL_SECONDS, now=None):
    current_time = float(time.time() if now is None else now)
    entry = load_safety_cache(cache_file).get(str(app_id))
    if not _entry_matches(entry, install_path, current_time, ttl_seconds):
        return None
    return SmokeSafetyResult(
        risk=bool(entry.get("risk")),
        signals=tuple(str(signal) for signal in entry.get("signals", ()) if signal),
        scanned_at=float(entry["scanned_at"]),
        install_path=str(entry["install_path"]),
        path_sig=tuple(entry["path_sig"]),
    )


def scan_and_cache_safety(cache_file, app_id, install_path, now=None):
    result = scan_anti_cheat(install_path, now=now)
    with _CACHE_LOCK:
        cache = load_safety_cache(cache_file)
        cache[str(app_id)] = {
            "install_path": result.install_path,
            "path_sig": list(result.path_sig),
            "risk": result.risk,
            "signals": list(result.signals),
            "scanned_at": result.scanned_at,
        }
        save_safety_cache(cache_file, cache)
    return result


def invalidate_safety_cache(cache_file, app_id):
    with _CACHE_LOCK:
        cache = load_safety_cache(cache_file)
        if cache.pop(str(app_id), None) is not None:
            save_safety_cache(cache_file, cache)
