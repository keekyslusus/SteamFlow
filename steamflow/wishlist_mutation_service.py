import subprocess
import sys
import urllib.error
from pathlib import Path

from .http_client import urllib_form_request
from .os_integration import start_hidden_process
from .session_token import (
    HTMLCACHE_REFRESH_TIMEOUT_SECONDS,
    STEAM_STORE_ORIGIN,
    SteamSessionTokenProvider,
    delete_saved_download_token,
    load_saved_download_token,
)


ADD_TO_WISHLIST_URL = "https://api.steampowered.com/IWishlistService/AddToWishlist/v1/"
REMOVE_FROM_WISHLIST_URL = "https://api.steampowered.com/IWishlistService/RemoveFromWishlist/v1/"


WISHLIST_TOKEN_FIELD_CANDIDATES = ("access_token", "webapi_token", "key")


def perform_wishlist_form_request(
    url,
    webapi_token,
    app_id,
    timeout=4,
    form_request=urllib_form_request,
    token_field="webapi_token",
):
    return form_request(
        url,
        {
            str(token_field or "webapi_token"): str(webapi_token or "").strip(),
            "appid": str(app_id or "").strip(),
        },
        method="POST",
        timeout=timeout,
        origin=STEAM_STORE_ORIGIN,
        referer=STEAM_STORE_ORIGIN + "/",
    )


def wishlist_mutation_url(action):
    normalized_action = str(action or "").strip().lower()
    if normalized_action == "add":
        return ADD_TO_WISHLIST_URL
    if normalized_action == "remove":
        return REMOVE_FROM_WISHLIST_URL
    raise ValueError(f"Unsupported Steam wishlist action: {action}")


def is_wishlist_auth_error(error):
    if isinstance(error, urllib.error.HTTPError):
        return getattr(error, "code", None) in {401, 403}

    message = str(error or "").strip().lower()
    if not message:
        return False
    return any(
        marker in message
        for marker in (
            "unauthorized",
            "forbidden",
            "webapi_token",
            "access token",
            "invalid token",
            "expired token",
            "login required",
            "not logged in",
        )
    )


def close_error_if_supported(error):
    close = getattr(error, "close", None)
    if callable(close):
        try:
            close()
        except Exception:
            pass


def perform_wishlist_request_with_token(url, token, app_id, form_request=perform_wishlist_form_request):
    last_auth_error = None
    for token_field in WISHLIST_TOKEN_FIELD_CANDIDATES:
        try:
            return form_request(url, token, app_id, token_field=token_field)
        except Exception as error:
            if not is_wishlist_auth_error(error):
                raise
            close_error_if_supported(error)
            last_auth_error = error
    if last_auth_error:
        raise last_auth_error
    raise RuntimeError("Steam wishlist request failed")


def refresh_wishlist_token(
    secure_settings_dir,
    steamid64,
    logger=None,
    refresh_wait_seconds=HTMLCACHE_REFRESH_TIMEOUT_SECONDS,
):
    provider = SteamSessionTokenProvider(
        secure_settings_dir,
        steamid64,
        logger=logger,
    )
    return provider.refresh_from_steam_htmlcache(refresh_wait_seconds=refresh_wait_seconds)


def perform_wishlist_mutation(
    secure_settings_dir,
    steamid64,
    app_id,
    action,
    logger=None,
    token_loader=load_saved_download_token,
    token_refresher=refresh_wishlist_token,
    token_deleter=delete_saved_download_token,
    form_request=perform_wishlist_form_request,
):
    steamid64 = str(steamid64 or "").strip()
    app_id = str(app_id or "").strip()
    url = wishlist_mutation_url(action)
    if not steamid64 or not app_id:
        raise ValueError("Missing Steam wishlist arguments")

    token = token_loader(secure_settings_dir, steamid64)
    if not token:
        if logger:
            logger.info("No cached Steam webapi token for %s; refreshing via Steam", steamid64)
        token = token_refresher(secure_settings_dir, steamid64, logger=logger)

    try:
        payload, _raw_data = perform_wishlist_request_with_token(
            url,
            token,
            app_id,
            form_request=form_request,
        )
        return payload
    except Exception as error:
        if not is_wishlist_auth_error(error):
            raise
        close_error_if_supported(error)
        token_deleter(secure_settings_dir, steamid64)
        if logger:
            logger.info("Cached Steam webapi token failed for wishlist; refreshing")
        token = token_refresher(secure_settings_dir, steamid64, logger=logger)
        payload, _raw_data = perform_wishlist_request_with_token(
            url,
            token,
            app_id,
            form_request=form_request,
        )
        return payload


def start_steam_wishlist_mutation_worker_process(
    plugin_dir,
    secure_settings_dir,
    steamid64,
    app_id,
    action,
    python_executable=sys.executable,
    popen=None,
    platform=sys.platform,
    subprocess_module=subprocess,
):
    plugin_dir = Path(plugin_dir)
    worker_script = plugin_dir / "steam_wishlist_mutation_worker.py"
    if not worker_script.exists():
        raise FileNotFoundError(f"Steam wishlist worker not found at {worker_script}")

    secure_settings_dir = Path(secure_settings_dir)
    secure_settings_dir.mkdir(parents=True, exist_ok=True)

    return start_hidden_process(
        [
            python_executable,
            str(worker_script),
            str(secure_settings_dir),
            str(steamid64),
            str(app_id),
            str(action),
        ],
        popen=popen,
        platform=platform,
        subprocess_module=subprocess_module,
        cwd=str(plugin_dir),
    )
