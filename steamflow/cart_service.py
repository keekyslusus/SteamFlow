import base64
import subprocess
import sys
import urllib.error
import urllib.parse
from pathlib import Path

from .download_control import refresh_download_control_token
from .session_token import (
    STEAM_STORE_ORIGIN,
    delete_saved_download_token,
    load_saved_download_token,
)
from .http_client import USER_AGENT, urllib_form_request, urllib_get_json
from .os_integration import build_hidden_process_kwargs, open_uri, start_hidden_process


STEAM_CART_URI = "steam://openurl/https://store.steampowered.com/cart"
# steam applies the signed-in accounts store region and corrects the final cart price
STEAM_CART_COUNTRY_CODE = "US"
STEAM_CART_CURRENCY_CODE = 1
STEAM_CART_BROWSER_ID = 1234567890123456789
SHOPPING_CART_CREATE_URL = "https://api.steampowered.com/IShoppingCartService/CreateNewShoppingCart/v1/"
SHOPPING_CART_ADD_PACKAGES_URL = "https://api.steampowered.com/IShoppingCartService/AddPackages/v1/"
ACCOUNT_CART_MERGE_URL = "https://api.steampowered.com/IAccountCartService/MergeShoppingCartContents/v1/"
APPDETAILS_URL = "https://store.steampowered.com/api/appdetails"


def encode_varint(value):
    value = int(value)
    if value < 0:
        raise ValueError("Protobuf varint cannot be negative")
    encoded = bytearray()
    while value >= 0x80:
        encoded.append((value & 0x7F) | 0x80)
        value >>= 7
    encoded.append(value)
    return bytes(encoded)


def field_varint(field_number, value):
    return encode_varint((int(field_number) << 3) | 0) + encode_varint(value)


def field_fixed64(field_number, value):
    return encode_varint((int(field_number) << 3) | 1) + int(value).to_bytes(8, "little", signed=False)


def field_bytes(field_number, value):
    if isinstance(value, str):
        value = value.encode("utf-8")
    value = bytes(value)
    return encode_varint((int(field_number) << 3) | 2) + encode_varint(len(value)) + value


def read_varint(data, offset=0):
    shift = 0
    value = 0
    while offset < len(data):
        byte_value = data[offset]
        offset += 1
        value |= (byte_value & 0x7F) << shift
        if not byte_value & 0x80:
            return value, offset
        shift += 7
        if shift > 70:
            raise ValueError("Invalid protobuf varint")
    raise ValueError("Truncated protobuf varint")


def skip_field(data, wire_type, offset):
    if wire_type == 0:
        return read_varint(data, offset)[1]
    if wire_type == 1:
        return offset + 8
    if wire_type == 2:
        size, offset = read_varint(data, offset)
        return offset + size
    if wire_type == 5:
        return offset + 4
    raise ValueError(f"Unsupported protobuf wire type: {wire_type}")


def parse_create_shopping_cart_response(raw_data):
    offset = 0
    while offset < len(raw_data):
        tag, offset = read_varint(raw_data, offset)
        field_number = tag >> 3
        wire_type = tag & 7
        if field_number == 1 and wire_type == 0:
            gid, _offset = read_varint(raw_data, offset)
            return str(gid)
        offset = skip_field(raw_data, wire_type, offset)
    return ""


def build_create_shopping_cart_request(steamid64):
    request = field_fixed64(1, int(str(steamid64).strip()))
    return base64.b64encode(request).decode("ascii")


def build_cart_amount_message(amount_cents, currency_code=STEAM_CART_CURRENCY_CODE):
    return b"".join(
        [
            field_varint(1, int(amount_cents)),
            field_varint(2, int(currency_code)),
        ]
    )


def build_package_item_message(packageid, amount_cents, currency_code=STEAM_CART_CURRENCY_CODE):
    return b"".join(
        [
            field_varint(1, int(packageid)),
            field_bytes(2, build_cart_amount_message(amount_cents, currency_code)),
            field_varint(5, 1),
        ]
    )


def build_add_packages_request(
    gidshoppingcart,
    packageid,
    amount_cents,
    currency_code=STEAM_CART_CURRENCY_CODE,
    store_country_code=STEAM_CART_COUNTRY_CODE,
    browserid=STEAM_CART_BROWSER_ID,
):
    request = b"".join(
        [
            field_varint(1, int(gidshoppingcart)),
            field_varint(2, int(browserid)),
            field_bytes(4, build_package_item_message(packageid, amount_cents, currency_code)),
            field_bytes(5, str(store_country_code or STEAM_CART_COUNTRY_CODE).upper()),
        ]
    )
    return base64.b64encode(request).decode("ascii")


def perform_form_request(url, fields, method="POST", timeout=4, opener=None):
    return urllib_form_request(
        url,
        fields=fields,
        method=method.upper(),
        timeout=timeout,
        origin=STEAM_STORE_ORIGIN,
        referer=STEAM_STORE_ORIGIN + "/",
        opener=opener,
    )


def extract_gidshoppingcart(payload, raw_data):
    response = payload.get("response", payload) if isinstance(payload, dict) else {}
    if isinstance(response, dict):
        gid = response.get("gidshoppingcart")
        if gid:
            return str(gid)
    return parse_create_shopping_cart_response(raw_data)


def create_shopping_cart(access_token, steamid64, timeout=4, form_request=perform_form_request):
    payload, raw_data = form_request(
        SHOPPING_CART_CREATE_URL,
        {
            "access_token": access_token,
            "origin": STEAM_STORE_ORIGIN,
            "input_protobuf_encoded": build_create_shopping_cart_request(steamid64),
        },
        timeout=timeout,
    )
    gidshoppingcart = extract_gidshoppingcart(payload, raw_data)
    if not gidshoppingcart:
        raise RuntimeError("Steam did not return a shopping cart id")
    return gidshoppingcart


def extract_cart_result_details(payload):
    response = payload.get("response", payload) if isinstance(payload, dict) else {}
    if isinstance(response, dict) and isinstance(response.get("result_details"), list):
        return response.get("result_details")
    return []


def add_package_to_shopping_cart(access_token, gidshoppingcart, packageid, amount_cents, timeout=4, form_request=perform_form_request):
    payload, _raw_data = form_request(
        SHOPPING_CART_ADD_PACKAGES_URL,
        {
            "access_token": access_token,
            "origin": STEAM_STORE_ORIGIN,
            "input_protobuf_encoded": build_add_packages_request(
                gidshoppingcart,
                packageid,
                amount_cents,
                STEAM_CART_CURRENCY_CODE,
                STEAM_CART_COUNTRY_CODE,
            ),
        },
        timeout=timeout,
    )
    result_details = extract_cart_result_details(payload)
    if result_details:
        raise RuntimeError(f"Steam rejected the cart package: {result_details}")
    return payload


def merge_shopping_cart_contents(access_token, gidshoppingcart, timeout=4, form_request=perform_form_request):
    payload, _raw_data = form_request(
        ACCOUNT_CART_MERGE_URL,
        {
            "access_token": access_token,
            "origin": STEAM_STORE_ORIGIN,
            "gidshoppingcart": str(gidshoppingcart),
            "user_country": STEAM_CART_COUNTRY_CODE,
        },
        timeout=timeout,
    )
    return payload


def fetch_cart_app_details(app_id, timeout=4, opener=None):
    query = urllib.parse.urlencode({"appids": str(app_id), "cc": STEAM_CART_COUNTRY_CODE, "l": "en"})
    payload = urllib_get_json(f"{APPDETAILS_URL}?{query}", timeout=timeout, opener=opener)
    app_details = payload.get(str(app_id), {})
    if not isinstance(app_details, dict) or not app_details.get("success"):
        raise RuntimeError(f"Steam appdetails did not return purchasable metadata for {app_id}")
    details = app_details.get("data", {})
    if not isinstance(details, dict):
        raise RuntimeError(f"Steam appdetails returned invalid metadata for {app_id}")
    return details


def to_positive_int(value):
    try:
        converted = int(value)
    except (TypeError, ValueError):
        return 0
    return converted if converted > 0 else 0


def build_cart_package(packageid, amount_cents):
    return {
        "packageid": int(packageid),
        "amount_cents": int(amount_cents),
        "currency_code": STEAM_CART_CURRENCY_CODE,
        "store_country_code": STEAM_CART_COUNTRY_CODE,
    }


def select_cart_package_from_app_details(details):
    if not isinstance(details, dict):
        raise ValueError("Missing Steam appdetails metadata")
    if details.get("is_free") is True:
        raise ValueError("Free Steam apps cannot be added to the cart")

    price_overview = details.get("price_overview") if isinstance(details.get("price_overview"), dict) else {}
    fallback_amount = to_positive_int(price_overview.get("final"))

    package_groups = details.get("package_groups") if isinstance(details.get("package_groups"), list) else []
    ordered_groups = sorted(
        [group for group in package_groups if isinstance(group, dict)],
        key=lambda group: 0 if str(group.get("name", "")).lower() == "default" else 1,
    )
    for group in ordered_groups:
        subs = group.get("subs")
        if not isinstance(subs, list):
            continue
        for sub in subs:
            if not isinstance(sub, dict):
                continue
            packageid = to_positive_int(sub.get("packageid"))
            amount = to_positive_int(sub.get("price_in_cents_with_discount")) or fallback_amount
            if packageid and amount:
                return build_cart_package(packageid, amount)

    packages = details.get("packages") if isinstance(details.get("packages"), list) else []
    for packageid in packages:
        packageid = to_positive_int(packageid)
        if packageid and fallback_amount:
            return build_cart_package(packageid, fallback_amount)

    raise ValueError("No paid Steam package was found for this app")


def resolve_cart_package(app_id):
    return select_cart_package_from_app_details(fetch_cart_app_details(app_id))


def add_resolved_package_to_cart_once(
    access_token,
    steamid64,
    app_id,
    package,
    logger=None,
    cart_creator=create_shopping_cart,
    package_adder=add_package_to_shopping_cart,
    cart_merger=merge_shopping_cart_contents,
):
    if logger:
        logger.info(
            "Adding app %s package %s to Steam cart as %s cents",
            app_id,
            package["packageid"],
            package["amount_cents"],
        )
    gidshoppingcart = cart_creator(access_token, steamid64)
    package_adder(
        access_token,
        gidshoppingcart,
        package["packageid"],
        package["amount_cents"],
    )
    cart_merger(access_token, gidshoppingcart)
    return package


def is_cart_auth_error(error):
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
            "access token",
            "invalid token",
            "expired token",
            "token expired",
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


def perform_add_to_cart(
    secure_settings_dir,
    steamid64,
    app_id,
    logger=None,
    package_resolver=resolve_cart_package,
    token_loader=load_saved_download_token,
    token_refresher=refresh_download_control_token,
    token_deleter=delete_saved_download_token,
    package_adder=add_resolved_package_to_cart_once,
):
    steamid64 = str(steamid64 or "").strip()
    app_id = str(app_id or "").strip()
    if not steamid64 or not app_id:
        raise ValueError("Missing Steam cart arguments")

    package = package_resolver(app_id)
    token = token_loader(secure_settings_dir, steamid64)
    if not token:
        if logger:
            logger.info("No cached Steam webapi token for %s; refreshing via Steam", steamid64)
        token = token_refresher(secure_settings_dir, steamid64, logger=logger)

    try:
        return package_adder(token, steamid64, app_id, package, logger=logger)
    except Exception as error:
        if not is_cart_auth_error(error):
            raise
        close_error_if_supported(error)
        token_deleter(secure_settings_dir, steamid64)
        if logger:
            logger.info("Cached Steam webapi token failed for cart; refreshing")
        token = token_refresher(secure_settings_dir, steamid64, logger=logger)
        return package_adder(token, steamid64, app_id, package, logger=logger)


def open_steam_cart(startfile=None):
    open_uri(STEAM_CART_URI, startfile=startfile)


def build_hidden_worker_kwargs(platform=sys.platform, subprocess_module=subprocess):
    return build_hidden_process_kwargs(
        platform=platform,
        subprocess_module=subprocess_module,
    )


def start_steam_cart_worker_process(
    plugin_dir,
    secure_settings_dir,
    steamid64,
    app_id,
    python_executable=sys.executable,
    popen=None,
    platform=sys.platform,
    subprocess_module=subprocess,
):
    plugin_dir = Path(plugin_dir)
    worker_script = plugin_dir / "steam_cart_worker.py"
    if not worker_script.exists():
        raise FileNotFoundError(f"Steam cart worker not found at {worker_script}")

    secure_settings_dir = Path(secure_settings_dir)
    secure_settings_dir.mkdir(parents=True, exist_ok=True)

    return start_hidden_process(
        [
            python_executable,
            str(worker_script),
            str(secure_settings_dir),
            str(steamid64),
            str(app_id),
        ],
        popen=popen,
        platform=platform,
        subprocess_module=subprocess_module,
        cwd=str(plugin_dir),
    )
