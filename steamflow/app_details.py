import os
import time
import urllib.parse
from pathlib import Path

from .cache_utils import build_timestamped_cache_entry, is_timestamp_fresh, read_json_file, write_json_file
from .http_client import DEFAULT_HTTP_HEADERS, http_get_json, urllib_get_json
from .util_currency import normalize_country_code


APPDETAILS_URL = "https://store.steampowered.com/api/appdetails"
USER_AGENT = DEFAULT_HTTP_HEADERS["User-Agent"]
APP_DETAILS_CACHE_DIR_NAME = "cache_app_details"
APP_DETAILS_CACHE_TTL_SECONDS = 30 * 24 * 60 * 60
APP_DETAILS_FAILURE_CACHE_TTL_SECONDS = 6 * 60 * 60
APP_DETAILS_FILE_MAX_AGE_SECONDS = 10 * 24 * 60 * 60
APP_DETAILS_FILE_TOUCH_INTERVAL_SECONDS = 24 * 60 * 60
APP_DETAILS_CLEANUP_INTERVAL_SECONDS = 24 * 60 * 60
MAX_CACHE_FILES = 1067


def normalize_app_id(app_id):
    normalized = str(app_id or "").strip()
    if not normalized.isascii() or not normalized.isdigit() or int(normalized) <= 0:
        raise ValueError(f"Invalid Steam app ID: {app_id!r}")
    return normalized


def normalize_app_details_country_code(country_code):
    return normalize_country_code(country_code, default="us")


def is_app_details_cache_entry_fresh(
    entry,
    success_ttl_seconds=APP_DETAILS_CACHE_TTL_SECONDS,
    failure_ttl_seconds=APP_DETAILS_FAILURE_CACHE_TTL_SECONDS,
):
    if not isinstance(entry, dict):
        return False
    ttl_seconds = success_ttl_seconds if entry.get("success") else failure_ttl_seconds
    return is_timestamp_fresh(entry.get("timestamp", 0), ttl_seconds)


def normalize_app_details_metadata(details):
    if not isinstance(details, dict):
        return None

    raw_is_free = details.get("is_free")
    if isinstance(raw_is_free, bool):
        is_free = raw_is_free
    elif raw_is_free in (0, 1):
        is_free = bool(raw_is_free)
    else:
        is_free = None

    release_date = details.get("release_date") if isinstance(details.get("release_date"), dict) else {}
    price_overview = details.get("price_overview") if isinstance(details.get("price_overview"), dict) else None

    return {
        "type": str(details.get("type", "") or "").strip().lower(),
        "is_free": is_free,
        "name": str(details.get("name", "") or "").strip(),
        "capsule_image": details.get("capsule_image") or details.get("header_image"),
        "platforms": details.get("platforms") if isinstance(details.get("platforms"), dict) else {},
        "has_price": isinstance(price_overview, dict),
        "price": price_overview,
        "coming_soon": bool(release_date.get("coming_soon")),
        "release_date_text": str(release_date.get("date", "") or "").strip(),
    }


def parse_app_details_metadata(payload, app_id):
    app_id = str(app_id or "").strip()
    app_details = payload.get(app_id, {}) if isinstance(payload, dict) else {}
    if not isinstance(app_details, dict) or not app_details.get("success"):
        return None

    return normalize_app_details_metadata(app_details.get("data", {}))


def build_appdetails_url(app_id, country_code=None, language="en"):
    query = {
        "appids": str(app_id or "").strip(),
        "l": str(language or "en").strip() or "en",
    }
    if country_code:
        query["cc"] = str(country_code).strip()
    return f"{APPDETAILS_URL}?{urllib.parse.urlencode(query)}"


def fetch_app_details_metadata_with_http_get(http_get, app_id, country_code=None, language="en", timeout=1.5):
    app_id = str(app_id or "").strip()
    if not app_id:
        return None

    payload = http_get_json(
        http_get,
        build_appdetails_url(app_id, country_code=country_code, language=language),
        timeout=timeout,
    )
    return parse_app_details_metadata(payload, app_id)


def fetch_app_details_metadata_with_urlopen(app_id, country_code=None, language="en", timeout=0.5):
    app_id = str(app_id or "").strip()
    if not app_id:
        return None

    payload = urllib_get_json(
        build_appdetails_url(app_id, country_code=country_code, language=language),
        timeout=timeout,
    )
    return parse_app_details_metadata(payload, app_id)


class AppDetailsFileCache:
    def __init__(self, cache_dir):
        self.cache_dir = Path(cache_dir)
        self.cleanup_marker_file = self.cache_dir / ".last_cleanup.json"
        self._recently_touched = {}

    def entry_path(self, app_id, country_code="us"):
        return self.cache_dir / normalize_app_details_country_code(country_code) / f"{normalize_app_id(app_id)}.json"

    def read_entry(self, app_id, country_code="us", touch=True, now=None):
        try:
            path = self.entry_path(app_id, country_code)
            entry = read_json_file(path, default=None)
            if not isinstance(entry, dict) or not isinstance(entry.get("metadata"), dict):
                return None
            if touch:
                self.touch_entry(app_id, country_code, now=now)
            return entry
        except (OSError, ValueError):
            return None

    def touch_entry(self, app_id, country_code="us", now=None):
        now = time.time() if now is None else float(now)
        path = self.entry_path(app_id, country_code)
        if now - self._recently_touched.get(path, 0) < APP_DETAILS_FILE_TOUCH_INTERVAL_SECONDS:
            return
        if now - path.stat().st_mtime >= APP_DETAILS_FILE_TOUCH_INTERVAL_SECONDS:
            os.utime(path, (now, now))
        self._recently_touched[path] = now

    def get_metadata(self, app_id, country_code="us"):
        entry = self.read_entry(app_id, country_code)
        if not is_app_details_cache_entry_fresh(entry) or not entry.get("success"):
            return None
        return entry["metadata"]

    def write_entry(self, app_id, metadata, success, country_code="us", timestamp=None, steam_language=None):
        entry = build_timestamped_cache_entry(
            {
                "success": bool(success),
                "metadata": dict(metadata or {}),
                "steam_language": str(steam_language or "en"),
            },
            now=timestamp,
        )
        return entry if write_json_file(self.entry_path(app_id, country_code), entry) else None

    def migrate_legacy_entries(self, entries):
        if not isinstance(entries, dict):
            return True
        migration_complete = True
        for app_id, entry in entries.items():
            if not isinstance(entry, dict):
                continue
            try:
                migrated_entry = self.write_entry(
                    app_id,
                    entry.get("metadata"),
                    success=entry.get("success"),
                    country_code=entry.get("country_code", "us"),
                    timestamp=entry.get("timestamp"),
                )
            except (TypeError, ValueError):
                continue
            if not migrated_entry:
                migration_complete = False
        return migration_complete

    def cleanup(self, now=None, force=False):
        now = time.time() if now is None else float(now)
        if not force:
            try:
                if now - self.cleanup_marker_file.stat().st_mtime < APP_DETAILS_CLEANUP_INTERVAL_SECONDS:
                    return False
            except OSError:
                pass

        changed = False
        files = []
        if self.cache_dir.is_dir():
            try:
                country_dirs = list(self.cache_dir.iterdir())
            except OSError:
                country_dirs = []
            for country_dir in country_dirs:
                if not country_dir.is_dir():
                    continue
                for path in country_dir.glob("*.json"):
                    try:
                        mtime = path.stat().st_mtime
                        if now - mtime >= APP_DETAILS_FILE_MAX_AGE_SECONDS:
                            path.unlink()
                            changed = True
                        else:
                            files.append((mtime, path))
                    except OSError:
                        continue

        for _mtime, path in sorted(files)[:max(0, len(files) - MAX_CACHE_FILES)]:
            try:
                path.unlink()
                changed = True
            except OSError:
                continue

        write_json_file(self.cleanup_marker_file, {"timestamp": now})
        return changed


# Kept as a compatibility alias for callers that imported the old class name.
MetricAppDetailsCache = AppDetailsFileCache


class AppDetailsMetadataProvider:
    def __init__(self, fetch_metadata, cache=None, country_code="us"):
        self.fetch_metadata = fetch_metadata
        self.cache = cache
        self.country_code = country_code

    def get_cached_metadata(self, app_id):
        if not self.cache:
            return None
        return self.cache.get_metadata(app_id, self.country_code)

    def fetch_and_cache_metadata(self, app_id):
        metadata = self.fetch_metadata(app_id)
        if self.cache:
            self.cache.write_entry(app_id, metadata, success=metadata is not None, country_code=self.country_code)
        return metadata

    def get_metadata(self, app_id):
        metadata = self.get_cached_metadata(app_id)
        if metadata:
            return metadata
        return self.fetch_and_cache_metadata(app_id)
