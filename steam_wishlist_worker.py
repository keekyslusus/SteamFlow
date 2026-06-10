import logging
import os
import sys
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

plugindir = Path(__file__).parent.resolve()
if str(plugindir) not in sys.path:
    sys.path.insert(0, str(plugindir))
lib_path = plugindir / "lib"
if str(lib_path) not in sys.path:
    sys.path.insert(0, str(lib_path))

LOG_FILE = plugindir / "steam_wishlist_worker.log"
LOCK_FILE = plugindir / "steam_wishlist_worker.lock"


try:
    log_handler = RotatingFileHandler(
        LOG_FILE,
        maxBytes=512 * 1024,
        backupCount=1,
        encoding="utf-8",
    )
except Exception:
    log_handler = logging.StreamHandler(sys.stderr)
log_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
logger = logging.getLogger("steam_wishlist_worker")
logger.handlers.clear()
logger.addHandler(log_handler)
logger.setLevel(logging.INFO)
logger.propagate = False

try:
    from steamflow.app_details import (
        APP_DETAILS_CACHE_DIR_NAME,
        AppDetailsFileCache,
        fetch_app_details_metadata_with_urlopen,
        is_app_details_cache_entry_fresh,
        normalize_app_details_country_code,
        normalize_app_id,
    )
except Exception:
    logger.exception("Failed to import SteamFlow appdetails helpers")
    raise

APP_DETAILS_CACHE_DIR = plugindir / APP_DETAILS_CACHE_DIR_NAME


class FileLock:
    def __init__(self, lock_file):
        self.lock_file = Path(lock_file)
        self.fd = None

    def acquire(self, timeout=0):
        start_time = time.time()
        while True:
            try:
                self.fd = os.open(str(self.lock_file), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(self.fd, str(os.getpid()).encode("ascii", errors="ignore"))
                return True
            except FileExistsError:
                try:
                    if time.time() - self.lock_file.stat().st_mtime > 15 * 60:
                        self.lock_file.unlink()
                        continue
                except OSError:
                    pass

                if timeout == 0 or (time.time() - start_time) >= timeout:
                    return False
                time.sleep(0.1)

    def release(self):
        if self.fd is not None:
            try:
                os.close(self.fd)
            except OSError:
                pass
            self.fd = None
        try:
            self.lock_file.unlink()
        except OSError:
            pass


def is_cache_entry_fresh(entry, country_code=None):
    return is_app_details_cache_entry_fresh(entry)


def fetch_app_details(app_id, country_code, steam_language="english"):
    return fetch_app_details_metadata_with_urlopen(
        app_id,
        country_code=country_code,
        language=steam_language,
        timeout=1.5,
    )


def entry_matches_language(entry, steam_language):
    entry_language = (entry or {}).get("steam_language")
    return entry_language == steam_language or (steam_language == "english" and entry_language is None)


def main():
    if len(sys.argv) < 3:
        logger.error("Invalid arguments count: %s", len(sys.argv))
        return 1
    extra_args = [str(arg or "").strip() for arg in sys.argv[3:]]
    force = "--force" in {arg.lower() for arg in extra_args}
    steam_language = next((arg for arg in extra_args if arg and not arg.startswith("--")), "english")

    country_code = normalize_app_details_country_code(sys.argv[1])
    app_ids = []
    for raw_app_id in str(sys.argv[2] or "").split(","):
        try:
            app_ids.append(normalize_app_id(raw_app_id))
        except ValueError:
            continue
    if not app_ids:
        logger.info("No wishlist app ids provided")
        return 0

    lock = FileLock(LOCK_FILE)
    if not lock.acquire(timeout=0):
        logger.info("Wishlist worker already running")
        return 0

    try:
        logger.info(
            "Wishlist worker started for %s app ids; country=%s; language=%s; force=%s; app_ids=%s",
            len(app_ids),
            country_code,
            steam_language,
            force,
            ",".join(app_ids),
        )
        app_details_cache = AppDetailsFileCache(APP_DETAILS_CACHE_DIR)
        cache_changed = False

        for app_id in app_ids:
            cache_entry = app_details_cache.read_entry(app_id, country_code)
            language_matches = entry_matches_language(cache_entry, steam_language)
            if is_cache_entry_fresh(cache_entry) and language_matches and not force:
                if cache_entry and cache_entry.get("success"):
                    logger.info("Wishlist appdetails cache fresh for app %s", app_id)
                else:
                    logger.warning("Wishlist appdetails previous failure still cached for app %s", app_id)
                continue
            if is_cache_entry_fresh(cache_entry) and not language_matches:
                logger.info(
                    "Refreshing wishlist appdetails for app %s after language mismatch: cached=%s expected=%s",
                    app_id,
                    (cache_entry or {}).get("steam_language"),
                    steam_language,
                )
            if is_cache_entry_fresh(cache_entry) and language_matches and force:
                logger.info("Force refreshing wishlist appdetails for app %s", app_id)
            if cache_entry and not cache_entry.get("success"):
                logger.info("Retrying wishlist appdetails after cached failure for app %s", app_id)

            try:
                metadata = fetch_app_details(app_id, country_code, steam_language=steam_language)
                app_details_cache.write_entry(
                    app_id,
                    metadata,
                    success=metadata is not None,
                    country_code=country_code,
                    steam_language=steam_language,
                )
                cache_changed = True
                if metadata:
                    logger.info(
                        "Hydrated wishlist appdetails for app %s: %s",
                        app_id,
                        str(metadata.get("name") or "").strip() or "<unnamed>",
                    )
                else:
                    logger.warning("Steam appdetails returned no metadata for wishlist app %s", app_id)
            except Exception:
                logger.exception("Failed to hydrate wishlist appdetails for %s", app_id)
                app_details_cache.write_entry(app_id, {}, success=False, country_code=country_code)
                cache_changed = True

        if cache_changed:
            logger.info("Wishlist worker updated appdetails cache")
        else:
            logger.info("Wishlist worker found nothing to update")
        return 0
    finally:
        lock.release()


if __name__ == "__main__":
    sys.exit(main())
