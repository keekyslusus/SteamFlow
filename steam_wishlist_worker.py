#!/usr/bin/env python
import json
import logging
import os
import subprocess
import sys
import time
import urllib.request
from logging.handlers import RotatingFileHandler
from pathlib import Path


plugindir = Path(__file__).parent.resolve()
LOG_FILE = plugindir / "steam_wishlist_worker.log"
LOCK_FILE = plugindir / "steam_wishlist_worker.lock"
METRIC_CACHE_FILE = plugindir / "cache_metric.json"
APP_DETAILS_CACHE_TTL_SECONDS = 30 * 24 * 60 * 60
APP_DETAILS_FAILURE_CACHE_TTL_SECONDS = 6 * 60 * 60
USER_AGENT = "Mozilla/5.0"


log_handler = RotatingFileHandler(
    LOG_FILE,
    maxBytes=512 * 1024,
    backupCount=1,
    encoding="utf-8",
)
log_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
logger = logging.getLogger("steam_wishlist_worker")
logger.handlers.clear()
logger.addHandler(log_handler)
logger.setLevel(logging.INFO)
logger.propagate = False


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


def load_metric_cache():
    if not METRIC_CACHE_FILE.exists():
        return {}
    try:
        with open(METRIC_CACHE_FILE, "r", encoding="utf-8") as file_obj:
            data = json.load(file_obj)
        return data if isinstance(data, dict) else {}
    except Exception:
        logger.exception("Failed to load metric cache")
        return {}


def save_metric_cache(cache_data):
    try:
        with open(METRIC_CACHE_FILE, "w", encoding="utf-8") as file_obj:
            json.dump(cache_data, file_obj)
        return True
    except Exception:
        logger.exception("Failed to save metric cache")
        return False


def get_app_details_cache(cache_data):
    app_details_cache = cache_data.get("app_details_cache", {})
    if not isinstance(app_details_cache, dict):
        app_details_cache = {}
        cache_data["app_details_cache"] = app_details_cache
    return app_details_cache


def is_cache_entry_fresh(entry):
    if not isinstance(entry, dict):
        return False
    ttl_seconds = APP_DETAILS_CACHE_TTL_SECONDS if entry.get("success") else APP_DETAILS_FAILURE_CACHE_TTL_SECONDS
    return (time.time() - float(entry.get("timestamp", 0) or 0)) < ttl_seconds


def fetch_app_details(app_id, country_code):
    url = f"https://store.steampowered.com/api/appdetails?appids={app_id}&cc={country_code}&l=en"
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=1.5) as response:
        payload = json.loads(response.read().decode("utf-8"))

    app_details = payload.get(str(app_id), {})
    if not isinstance(app_details, dict) or not app_details.get("success"):
        return None

    details = app_details.get("data", {})
    if not isinstance(details, dict):
        return None

    raw_is_free = details.get("is_free")
    if isinstance(raw_is_free, bool):
        is_free = raw_is_free
    elif raw_is_free in (0, 1):
        is_free = bool(raw_is_free)
    else:
        is_free = None

    return {
        "type": str(details.get("type", "") or "").strip().lower(),
        "is_free": is_free,
        "name": str(details.get("name", "") or "").strip(),
        "capsule_image": details.get("capsule_image") or details.get("header_image"),
        "platforms": details.get("platforms") if isinstance(details.get("platforms"), dict) else {},
        "has_price": isinstance(details.get("price_overview"), dict),
        "price": details.get("price_overview") if isinstance(details.get("price_overview"), dict) else None,
        "coming_soon": bool((details.get("release_date") or {}).get("coming_soon")),
        "release_date_text": str((details.get("release_date") or {}).get("date", "") or "").strip(),
    }


def main():
    if len(sys.argv) != 3:
        logger.error("Invalid arguments count: %s", len(sys.argv))
        return 1

    country_code = str(sys.argv[1] or "us").strip().lower() or "us"
    app_ids = [str(app_id).strip() for app_id in str(sys.argv[2] or "").split(",") if str(app_id).strip()]
    if not app_ids:
        logger.info("No wishlist app ids provided")
        return 0

    lock = FileLock(LOCK_FILE)
    if not lock.acquire(timeout=0):
        logger.info("Wishlist worker already running")
        return 0

    try:
        logger.info("Wishlist worker started for %s app ids", len(app_ids))
        cache_data = load_metric_cache()
        app_details_cache = get_app_details_cache(cache_data)
        cache_changed = False

        for app_id in app_ids:
            cache_entry = app_details_cache.get(app_id)
            if is_cache_entry_fresh(cache_entry):
                continue

            try:
                metadata = fetch_app_details(app_id, country_code)
                app_details_cache[app_id] = {
                    "timestamp": time.time(),
                    "success": metadata is not None,
                    "metadata": dict(metadata or {}),
                }
                cache_changed = True
                save_metric_cache(cache_data)
            except Exception:
                logger.exception("Failed to hydrate wishlist appdetails for %s", app_id)
                app_details_cache[app_id] = {
                    "timestamp": time.time(),
                    "success": False,
                    "metadata": {},
                }
                cache_changed = True
                save_metric_cache(cache_data)

        if cache_changed:
            logger.info("Wishlist worker updated appdetails cache")
        else:
            logger.info("Wishlist worker found nothing to update")
        return 0
    finally:
        lock.release()


if __name__ == "__main__":
    sys.exit(main())
