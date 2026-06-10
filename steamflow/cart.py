from .cart_service import (
    ACCOUNT_CART_MERGE_URL,
    APPDETAILS_URL,
    SHOPPING_CART_ADD_PACKAGES_URL,
    SHOPPING_CART_CREATE_URL,
    STEAM_CART_BROWSER_ID,
    STEAM_CART_COUNTRY_CODE,
    STEAM_CART_CURRENCY_CODE,
    STEAM_CART_URI,
    USER_AGENT,
    add_package_to_shopping_cart,
    add_resolved_package_to_cart_once,
    build_add_packages_request,
    build_cart_amount_message,
    build_create_shopping_cart_request,
    build_package_item_message,
    create_shopping_cart,
    fetch_cart_app_details,
    merge_shopping_cart_contents,
    open_steam_cart,
    parse_create_shopping_cart_response,
    perform_add_to_cart,
    resolve_cart_package,
    select_cart_package_from_app_details,
    start_steam_cart_worker_process,
)
from .hooks import get_secure_settings_dir, log_exception_if_supported
from .localization import plugin_tr
from .providers import get_plugin_providers


class SteamPluginCartMixin:
    REQUIRED_PLUGIN_ATTRS = (
        "plugin_dir",
        "settings_path",
    )
    REQUIRED_PLUGIN_PROVIDERS = ("account",)

    @property
    def cart_providers(self):
        return get_plugin_providers(self)

    def start_steam_cart_worker(self, steamid64, app_id):
        start_steam_cart_worker_process(
            self.plugin_dir,
            get_secure_settings_dir(self),
            steamid64,
            app_id,
        )

    def add_to_steam_cart(self, app_id, steamid64=None):
        app_id = str(app_id or "").strip()
        if not app_id:
            return plugin_tr(self, "action.missing_app_id")
        feature_enabled = getattr(self, "feature_enabled", None)
        if callable(feature_enabled) and (
            not feature_enabled("steam_cart") or not feature_enabled("steam_session_token")
        ):
            return plugin_tr(self, "cart.unavailable")

        if not steamid64:
            steamid64 = self.cart_providers.account.active_steamid64()
        steamid64 = str(steamid64 or "").strip()
        if not steamid64:
            return plugin_tr(self, "action.no_active_account")

        try:
            self.start_steam_cart_worker(steamid64, app_id)
            return plugin_tr(self, "cart.adding", app_id=app_id)
        except Exception as error:
            log_exception_if_supported(self, f"Failed to start Steam cart worker for app {app_id}")
            return plugin_tr(self, "cart.add_failed", error=str(error))
