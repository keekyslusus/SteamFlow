import hashlib
import json
import os
import shutil
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


API_FILES = (
    ("steam_api.dll", "steam_api_o.dll"),
    ("steam_api64.dll", "steam_api64_o.dll"),
)
SMOKE_CONFIG_FILES = ("SmokeAPI.config.json", "SmokeAPI.json")
SMOKE_LEFTOVER_FILES = ("SmokeAPI.cache.json", "SmokeAPI.log", "SmokeAPI.log.log")
SMOKE_CLEANUP_FILES = SMOKE_CONFIG_FILES + SMOKE_LEFTOVER_FILES
DEFAULT_PAYLOAD_DIR = Path(__file__).resolve().parent.parent / "resources" / "smokeapi"
SMOKE_CONFIG = {
    "$version": 4,
    "logging": False,
    "log_steam_http": False,
    "default_app_status": "unlocked",
    "override_app_status": {},
    "override_dlc_status": {},
    "auto_inject_inventory": True,
    "extra_inventory_items": [],
    "extra_dlcs": {},
}


@dataclass(frozen=True)
class SmokeAPIState:
    installed: bool
    installable: bool
    installed_directories: tuple
    install_directories: tuple
    ambiguous_directories: tuple

    @property
    def action(self):
        if self.installed:
            return "remove"
        if self.installable:
            return "install"
        return ""


@dataclass(frozen=True)
class SmokeAPIOperationResult:
    action: str
    total_directories: int
    successful_directories: int
    changed_dlls: int
    errors: tuple = ()
    backup_missing: tuple = ()

    @property
    def success(self):
        return self.total_directories > 0 and not self.errors and not self.backup_missing

    @property
    def partial(self):
        return self.changed_dlls > 0 and not self.success


def _directory_names(directory):
    try:
        entries = {}
        for entry in directory.iterdir():
            try:
                if entry.is_file():
                    entries[entry.name.lower()] = entry
            except OSError:
                continue
        return entries
    except OSError:
        return {}


def _walk_candidate_directories(install_path):
    root = Path(install_path)
    if not root.is_dir():
        return ()

    candidates = []
    interesting_names = {
        name.lower()
        for pair in API_FILES
        for name in pair
    } | {name.lower() for name in SMOKE_CLEANUP_FILES}
    for current_root, directory_names, file_names in os.walk(root, followlinks=False):
        directory_names.sort(key=str.lower)
        file_names.sort(key=str.lower)
        names = {name.lower() for name in directory_names}
        names.update(name.lower() for name in file_names)
        if names & interesting_names:
            candidates.append(Path(current_root))
    return tuple(candidates)


def find_dll_directories(install_path):
    """Return directories containing a live Steamworks API DLL."""
    result = []
    for directory in _walk_candidate_directories(install_path):
        names = _directory_names(directory)
        if any(live_name.lower() in names for live_name, _backup_name in API_FILES):
            result.append(directory)
    return tuple(result)


def _hash_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _payload_signature(payload_root):
    signature = []
    for live_name, _backup_name in API_FILES:
        try:
            stat_result = (payload_root / live_name).stat()
            signature.append((live_name, int(stat_result.st_mtime_ns), int(stat_result.st_size)))
        except OSError:
            signature.append((live_name, 0, 0))
    return tuple(signature)


@lru_cache(maxsize=8)
def _cached_payload_hash_items(payload_root_string, payload_signature):
    payload_root = Path(payload_root_string)
    hashes = []
    for live_name, _mtime_ns, size in payload_signature:
        if size <= 0:
            continue
        try:
            hashes.append((live_name.lower(), _hash_file(payload_root / live_name)))
        except OSError:
            continue
    return tuple(hashes)


def _payload_hashes(payload_dir):
    payload_root = Path(payload_dir)
    return dict(
        _cached_payload_hash_items(
            str(payload_root),
            _payload_signature(payload_root),
        )
    )


def _directory_is_smokeapi(directory, payload_hashes=None):
    names = _directory_names(directory)
    if not names:
        return False

    has_config = any(name.lower() in names for name in SMOKE_CONFIG_FILES)
    if has_config:
        return True

    has_backup = any(backup.lower() in names for _live, backup in API_FILES)
    has_leftover = any(name.lower() in names for name in SMOKE_LEFTOVER_FILES)
    if has_backup and has_leftover:
        return True

    if not payload_hashes:
        return False
    for live_name, _backup_name in API_FILES:
        live_path = names.get(live_name.lower())
        if live_path is None:
            continue
        expected_hash = payload_hashes.get(live_name.lower())
        if not expected_hash:
            continue
        try:
            if _hash_file(live_path) == expected_hash:
                return True
        except OSError:
            continue
    return False


def detect_smokeapi_state(install_path, payload_dir=DEFAULT_PAYLOAD_DIR):
    payload_hashes = _payload_hashes(payload_dir)
    installed_directories = []
    install_directories = []
    ambiguous_directories = []

    for directory in _walk_candidate_directories(install_path):
        names = _directory_names(directory)
        is_smokeapi = _directory_is_smokeapi(directory, payload_hashes)
        if is_smokeapi:
            installed_directories.append(directory)
            continue

        has_live_api = any(live.lower() in names for live, _backup in API_FILES)
        has_backup = any(backup.lower() in names for _live, backup in API_FILES)
        if has_live_api and has_backup:
            ambiguous_directories.append(directory)
        elif has_live_api:
            install_directories.append(directory)

    return SmokeAPIState(
        installed=bool(installed_directories),
        installable=(
            bool(install_directories)
            and not installed_directories
            and not ambiguous_directories
        ),
        installed_directories=tuple(installed_directories),
        install_directories=tuple(install_directories),
        ambiguous_directories=tuple(ambiguous_directories),
    )


def _write_config(directory):
    config_path = Path(directory) / "SmokeAPI.config.json"
    temporary_path = config_path.with_suffix(config_path.suffix + ".tmp")
    try:
        temporary_path.write_text(
            json.dumps(SMOKE_CONFIG, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary_path.replace(config_path)
    finally:
        if temporary_path.exists():
            try:
                temporary_path.unlink()
            except OSError:
                pass


def install_smokeapi(install_path, payload_dir=DEFAULT_PAYLOAD_DIR):
    root = Path(install_path)
    if not root.is_dir():
        return SmokeAPIOperationResult("install", 0, 0, 0, ("install_path_missing",))

    state = detect_smokeapi_state(root, payload_dir=payload_dir)
    if state.installed:
        return SmokeAPIOperationResult("install", 0, 0, 0, ("already_installed",))
    if state.ambiguous_directories:
        return SmokeAPIOperationResult("install", 0, 0, 0, ("ambiguous_backup",))
    targets = state.install_directories
    if not targets:
        error = "ambiguous_backup" if state.ambiguous_directories else "no_targets"
        return SmokeAPIOperationResult("install", 0, 0, 0, (error,))

    payload_root = Path(payload_dir)
    required_payloads = set()
    for directory in targets:
        names = _directory_names(directory)
        for live_name, _backup_name in API_FILES:
            if live_name.lower() in names:
                required_payloads.add(live_name)
    missing_payloads = tuple(
        sorted(name for name in required_payloads if not (payload_root / name).is_file())
    )
    if missing_payloads:
        return SmokeAPIOperationResult(
            "install",
            len(targets),
            0,
            0,
            tuple(f"payload_missing:{name}" for name in missing_payloads),
        )

    successful_directories = 0
    changed_dlls = 0
    errors = []
    for directory in targets:
        directory_changed = 0
        directory_failed = False
        names = _directory_names(directory)
        for live_name, backup_name in API_FILES:
            live_path = names.get(live_name.lower())
            if live_path is None:
                continue
            backup_path = directory / backup_name
            try:
                if backup_path.exists():
                    raise FileExistsError(str(backup_path))
                live_path.replace(backup_path)
                try:
                    shutil.copy2(payload_root / live_name, directory / live_name)
                except Exception:
                    incomplete_path = directory / live_name
                    if incomplete_path.exists():
                        incomplete_path.unlink()
                    if backup_path.exists():
                        backup_path.replace(incomplete_path)
                    raise
                directory_changed += 1
                changed_dlls += 1
            except Exception as error:
                directory_failed = True
                errors.append(f"{directory}:{live_name}:{error}")

        if directory_changed:
            try:
                _write_config(directory)
            except Exception as error:
                directory_failed = True
                errors.append(f"{directory}:SmokeAPI.config.json:{error}")
        if directory_changed and not directory_failed:
            successful_directories += 1

    return SmokeAPIOperationResult(
        "install",
        len(targets),
        successful_directories,
        changed_dlls,
        tuple(errors),
    )


def remove_smokeapi(install_path, payload_dir=DEFAULT_PAYLOAD_DIR):
    root = Path(install_path)
    if not root.is_dir():
        return SmokeAPIOperationResult("remove", 0, 0, 0, ("install_path_missing",))

    state = detect_smokeapi_state(root, payload_dir=payload_dir)
    targets = state.installed_directories
    if not targets:
        return SmokeAPIOperationResult("remove", 0, 0, 0, ("not_installed",))

    successful_directories = 0
    changed_dlls = 0
    errors = []
    backup_missing = []
    for directory in targets:
        names = _directory_names(directory)
        directory_failed = False
        directory_backup_missing = False
        restored_here = 0
        for live_name, backup_name in API_FILES:
            live_path = names.get(live_name.lower())
            backup_path = names.get(backup_name.lower())
            if backup_path is None:
                if live_path is not None:
                    backup_missing.append(f"{directory}:{backup_name}")
                    directory_backup_missing = True
                continue
            try:
                backup_path.replace(directory / live_name)
                restored_here += 1
                changed_dlls += 1
            except Exception as error:
                directory_failed = True
                errors.append(f"{directory}:{live_name}:{error}")

        cleanup_files = SMOKE_LEFTOVER_FILES if directory_backup_missing else SMOKE_CLEANUP_FILES
        for filename in cleanup_files:
            path = _directory_names(directory).get(filename.lower())
            if path is None:
                continue
            try:
                path.unlink()
            except Exception as error:
                directory_failed = True
                errors.append(f"{directory}:{filename}:{error}")
        if restored_here and not directory_failed:
            successful_directories += 1

    return SmokeAPIOperationResult(
        "remove",
        len(targets),
        successful_directories,
        changed_dlls,
        tuple(errors),
        tuple(backup_missing),
    )
