import time
import urllib.error
from pathlib import Path

from .cache_utils import read_json_file, write_json_file


FEATURE_STEAM_SESSION_TOKEN = "steam_session_token"
FEATURE_DOWNLOAD_CONTROL = "download_control"
FEATURE_STEAM_CART = "steam_cart"
FEATURE_STEAM_WISHLIST = "steam_wishlist"
FEATURE_NAMES = (
    FEATURE_STEAM_SESSION_TOKEN,
    FEATURE_DOWNLOAD_CONTROL,
    FEATURE_STEAM_CART,
    FEATURE_STEAM_WISHLIST,
)
# debug switch to force all fragile features off in the ui (default: False)
DEBUG_DISABLE_ALL_FRAGILE_FEATURES = False

STATE_HEALTHY = "healthy"
STATE_SUSPECT = "suspect"
STATE_DISABLED = "disabled"

DEFAULT_FAILURE_THRESHOLD = 3
DEFAULT_COOLDOWN_SECONDS = 60 * 60
REASON_COOLDOWNS = {
    "clientcomm_rejected": 6 * 60 * 60,
    "cart_rejected": 60 * 60,
    "wishlist_rejected": 60 * 60,
    "token_not_found": 60 * 60,
    "htmlcache_missing": 60 * 60,
    "auth_rejected": 60 * 60,
    "token_rejected": 60 * 60,
    "token_expired": 60 * 60,
    "network_error": 20 * 60,
    "timeout": 20 * 60,
    "worker_start_failed": 10 * 60,
}


def _now(now=None):
    return time.time() if now is None else float(now)


def _default_entry():
    return {
        "state": STATE_HEALTHY,
        "failures": 0,
        "last_error": "",
        "last_reason": "",
        "last_success": 0,
        "last_failure": 0,
        "disabled_until": 0,
    }


def _coerce_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _coerce_float(value, default=0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def normalize_feature_name(name):
    normalized = str(name or "").strip().lower()
    return normalized if normalized in FEATURE_NAMES else normalized


def normalize_feature_entry(entry, now=None, expire_disabled=True):
    normalized = _default_entry()
    if isinstance(entry, dict):
        normalized.update(
            {
                "state": str(entry.get("state") or STATE_HEALTHY),
                "failures": _coerce_int(entry.get("failures"), 0),
                "last_error": str(entry.get("last_error") or ""),
                "last_reason": str(entry.get("last_reason") or ""),
                "last_success": _coerce_float(entry.get("last_success"), 0),
                "last_failure": _coerce_float(entry.get("last_failure"), 0),
                "disabled_until": _coerce_float(entry.get("disabled_until"), 0),
            }
        )
    if normalized["state"] not in {STATE_HEALTHY, STATE_SUSPECT, STATE_DISABLED}:
        normalized["state"] = STATE_HEALTHY
    if normalized["failures"] < 0:
        normalized["failures"] = 0
    if expire_disabled and normalized["state"] == STATE_DISABLED and normalized["disabled_until"] <= _now(now):
        normalized["state"] = STATE_SUSPECT
    return normalized


def read_feature_health(cache_file):
    data = read_json_file(cache_file, default={})
    if not isinstance(data, dict):
        data = {}
    return {
        name: normalize_feature_entry(data.get(name), expire_disabled=False)
        for name in FEATURE_NAMES
    }


def write_feature_health(cache_file, data):
    payload = {
        name: normalize_feature_entry((data or {}).get(name), expire_disabled=False)
        for name in FEATURE_NAMES
    }
    return write_json_file(cache_file, payload, indent=2)


def get_feature_health_status(cache_file, name, now=None):
    feature_name = normalize_feature_name(name)
    if DEBUG_DISABLE_ALL_FRAGILE_FEATURES and feature_name in FEATURE_NAMES:
        current_time = _now(now)
        entry = _default_entry()
        entry.update(
            {
                "state": STATE_DISABLED,
                "failures": DEFAULT_FAILURE_THRESHOLD,
                "last_error": "Debug override",
                "last_reason": "debug_disabled",
                "last_failure": current_time,
                "disabled_until": current_time + DEFAULT_COOLDOWN_SECONDS,
            }
        )
        return entry
    data = read_feature_health(cache_file)
    return normalize_feature_entry(data.get(feature_name), now=now)


def feature_enabled(cache_file, name, now=None):
    status = get_feature_health_status(cache_file, name, now=now)
    return not (
        status["state"] == STATE_DISABLED
        and status["disabled_until"] > _now(now)
    )


def record_feature_success(cache_file, name, now=None):
    feature_name = normalize_feature_name(name)
    data = read_feature_health(cache_file)
    entry = normalize_feature_entry(data.get(feature_name), now=now)
    entry.update(
        {
            "state": STATE_HEALTHY,
            "failures": 0,
            "last_error": "",
            "last_reason": "",
            "last_success": _now(now),
            "disabled_until": 0,
        }
    )
    data[feature_name] = entry
    write_feature_health(cache_file, data)
    return entry


def cooldown_seconds_for_reason(reason, default=DEFAULT_COOLDOWN_SECONDS):
    return REASON_COOLDOWNS.get(str(reason or "").strip().lower(), default)


def record_feature_failure(
    cache_file,
    name,
    error=None,
    reason="unknown",
    now=None,
    failure_threshold=DEFAULT_FAILURE_THRESHOLD,
    cooldown_seconds=None,
):
    feature_name = normalize_feature_name(name)
    current_time = _now(now)
    data = read_feature_health(cache_file)
    entry = normalize_feature_entry(data.get(feature_name), now=current_time)
    failures = int(entry.get("failures") or 0) + 1
    reason = str(reason or "unknown").strip() or "unknown"
    entry.update(
        {
            "failures": failures,
            "last_error": str(error or ""),
            "last_reason": reason,
            "last_failure": current_time,
        }
    )
    if failures >= int(failure_threshold or DEFAULT_FAILURE_THRESHOLD):
        entry["state"] = STATE_DISABLED
        cooldown = cooldown_seconds_for_reason(reason) if cooldown_seconds is None else float(cooldown_seconds)
        entry["disabled_until"] = current_time + cooldown
    else:
        entry["state"] = STATE_SUSPECT
    data[feature_name] = entry
    write_feature_health(cache_file, data)
    return entry


def reset_feature_health(cache_file, name=None):
    if name:
        data = read_feature_health(cache_file)
        data[normalize_feature_name(name)] = _default_entry()
        write_feature_health(cache_file, data)
        return data
    write_feature_health(cache_file, {feature_name: _default_entry() for feature_name in FEATURE_NAMES})
    return read_feature_health(cache_file)


def classify_feature_error(error, feature_name=None):
    feature_name = normalize_feature_name(feature_name)
    if isinstance(error, urllib.error.HTTPError):
        if getattr(error, "code", None) in {401, 403}:
            if feature_name == FEATURE_DOWNLOAD_CONTROL:
                return "clientcomm_rejected"
            if feature_name == FEATURE_STEAM_CART:
                return "cart_rejected"
            if feature_name == FEATURE_STEAM_WISHLIST:
                return "wishlist_rejected"
            return "auth_rejected"

    message = str(error or "").strip().lower()
    if not message:
        return "unknown"
    if "no matching steam webapi_token found" in message:
        return "token_not_found"
    if "cache_data" in message or "htmlcache" in message and "missing" in message:
        return "htmlcache_missing"
    if "timed out" in message or "timeout" in message:
        return "timeout"
    if "network" in message or "socket" in message or "connection" in message:
        return "network_error"
    if "expired token" in message or "token expired" in message:
        return "token_expired"
    if "unauthorized" in message or "forbidden" in message or "invalid token" in message:
        if feature_name == FEATURE_DOWNLOAD_CONTROL:
            return "clientcomm_rejected"
        if feature_name == FEATURE_STEAM_CART:
            return "cart_rejected"
        if feature_name == FEATURE_STEAM_WISHLIST:
            return "wishlist_rejected"
        return "auth_rejected"
    if "clientcomm" in message or "iclientcommservice" in message or "http 401" in message or "http 403" in message:
        return "clientcomm_rejected"
    if "cart" in message or "shopping cart" in message or "package" in message:
        return "cart_rejected"
    if "wishlist" in message or "iwishlistservice" in message:
        return "wishlist_rejected"
    return "unknown"


class SteamPluginFeatureHealthMixin:
    REQUIRED_PLUGIN_ATTRS = ("feature_health_cache_file",)

    def feature_enabled(self, name, now=None):
        return feature_enabled(self.feature_health_cache_file, name, now=now)

    def record_feature_success(self, name, now=None):
        return record_feature_success(self.feature_health_cache_file, name, now=now)

    def record_feature_failure(self, name, error=None, reason="unknown", now=None):
        return record_feature_failure(
            self.feature_health_cache_file,
            name,
            error=error,
            reason=reason,
            now=now,
        )

    def get_feature_health_status(self, name, now=None):
        return get_feature_health_status(self.feature_health_cache_file, name, now=now)

    def reset_feature_health(self, name=None):
        return reset_feature_health(self.feature_health_cache_file, name=name)
