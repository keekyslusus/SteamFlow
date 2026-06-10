from functools import cached_property
from pathlib import Path

from .actions import SteamPluginActionsMixin
from .app_details import (
    APP_DETAILS_CACHE_DIR_NAME,
    AppDetailsMetadataProvider,
    MetricAppDetailsCache,
    fetch_app_details_metadata_with_urlopen,
)
from .cart import SteamPluginCartMixin
from .feature_health import feature_enabled
from .hooks import get_secure_settings_dir
from .localization import Localizer, plugin_tr, resolve_configured_locale
from .menu import (
    get_game_context_menu_entries,
    get_steam_client_context_menu_entries,
    is_store_action_result_source,
    is_store_cart_result_source,
)
from .os_integration import resolve_steam_install_path_from_registry
from .pyflow_compat import SteamFlowPluginBase
from .wishlist_mutation_service import start_steam_wishlist_mutation_worker_process

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
UNSET = object()


class SteamContextMenuPlugin(SteamPluginCartMixin, SteamPluginActionsMixin, SteamFlowPluginBase):
    @cached_property
    def app_details_cache_store(self):
        return MetricAppDetailsCache(self.plugin_dir / APP_DETAILS_CACHE_DIR_NAME)

    @cached_property
    def app_details_provider(self):
        return AppDetailsMetadataProvider(
            self.fetch_app_details_metadata,
            cache=self.app_details_cache_store,
        )

    def fetch_app_details_metadata(self, app_id):
        try:
            return fetch_app_details_metadata_with_urlopen(app_id, timeout=0.5)
        except Exception:
            return None

    def get_cached_app_details_metadata(self, app_id):
        return self.app_details_provider.get_cached_metadata(app_id)

    def get_context_app_details_metadata(self, app_id):
        return self.app_details_provider.get_metadata(app_id)

    def derive_is_unreleased(self, data):
        if data.get("install_path"):
            return False

        coming_soon = data.get("coming_soon")
        if coming_soon is True:
            return True
        if coming_soon is False:
            return False

        app_id = str(data.get("app_id", "") or "")
        if not app_id:
            return False

        metadata = self.get_context_app_details_metadata(app_id)
        if not metadata:
            return False
        return bool(metadata.get("coming_soon"))

    def derive_refund_state(self, data):
        refund_state = str(data.get("refund_state", "") or "")
        if refund_state:
            return refund_state

        app_id = str(data.get("app_id", "") or "")
        install_path = data.get("install_path")
        if not app_id or not install_path:
            return ""
        if data.get("has_current_account_local_data") is False:
            return ""

        playtime_minutes = data.get("playtime_minutes")
        try:
            playtime_minutes = int(playtime_minutes) if playtime_minutes is not None else None
        except (TypeError, ValueError):
            playtime_minutes = None

        if playtime_minutes is not None and playtime_minutes >= 120:
            return ""

        metadata = self.get_context_app_details_metadata(app_id)
        if not metadata:
            return ""
        if metadata.get("type") != "game" or metadata.get("is_free") is not False:
            return ""

        if playtime_minutes is not None and playtime_minutes < 120:
            return "likely"
        if playtime_minutes is None:
            return "unclear"
        return ""

    def __init__(self):
        super().__init__()
        self.plugin_dir = PACKAGE_ROOT
        self._steam_path = UNSET
        self.buy_icon = str(self.plugin_dir / "icons" / "buy.png")
        self.community_icon = str(self.plugin_dir / "icons" / "community.png")
        self.csrin_icon = str(self.plugin_dir / "icons" / "csrin.png")
        self.default_icon = str(self.plugin_dir / "icons" / "steam.png")
        self.deals_icon = str(self.plugin_dir / "icons" / "deals.png")
        self.discussions_icon = str(self.plugin_dir / "icons" / "discussions.png")
        self.download_icon = str(self.plugin_dir / "icons" / "download.png")
        self.guides_icon = str(self.plugin_dir / "icons" / "guides.png")
        self.location_icon = str(self.plugin_dir / "icons" / "location.png")
        self.properties_icon = str(self.plugin_dir / "icons" / "properties.png")
        self.refund_icon = str(self.plugin_dir / "icons" / "refund.png")
        self.screenshot_icon = str(self.plugin_dir / "icons" / "screenshot.png")
        self.settings_icon = str(self.plugin_dir / "icons" / "settings.png")
        self.steamdb_icon = str(self.plugin_dir / "icons" / "steamdb.png")
        self.top_sellers_icon = str(self.plugin_dir / "icons" / "top_sellers.png")
        self.trash_icon = str(self.plugin_dir / "icons" / "trash.png")
        self.wishlist_icon = str(self.plugin_dir / "icons" / "wishlist.png")
        self.wishlist_add_icon = str(self.plugin_dir / "icons" / "wl_add.png")
        self.wishlist_remove_icon = str(self.plugin_dir / "icons" / "wl_remove.png")
        self.feature_health_cache_file = self.plugin_dir / "cache_feature_health.json"

    @cached_property
    def logfile(self):
        return str(self.plugin_dir / "plugin_steamflow.log")

    @property
    def steam_path(self):
        if self._steam_path is UNSET:
            self._steam_path = self._find_steam_path()
        return self._steam_path

    def _find_steam_path(self):
        return resolve_steam_install_path_from_registry()

    def _add_menu_entries(self, entries):
        for entry in entries:
            self.add_item(
                title=entry["title"],
                subtitle=entry["subtitle"],
                icon=entry["icon"],
                method=entry["method"],
                parameters=entry.get("parameters"),
            )

    def get_language(self):
        return resolve_configured_locale(self.settings.get("language", "auto"))

    def tr(self, key, default=None, **values):
        return Localizer(self.get_language()).tr(key, default=default, **values)

    def get_setting_bool(self, name, default):
        value = self.settings.get(name, default)
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return bool(value)

    def start_steam_wishlist_mutation_worker(self, steamid64, app_id, action):
        start_steam_wishlist_mutation_worker_process(
            self.plugin_dir,
            get_secure_settings_dir(self),
            steamid64,
            app_id,
            action,
        )

    def mutate_steam_wishlist(self, app_id, action, steamid64=None):
        app_id = str(app_id or "").strip()
        action = str(action or "").strip().lower()
        steamid64 = str(steamid64 or "").strip()
        if not app_id:
            return plugin_tr(self, "action.missing_app_id")
        if not steamid64:
            return plugin_tr(self, "action.no_active_account")
        if action not in {"add", "remove"}:
            return plugin_tr(self, "wishlist.mutation_failed", error=f"Unsupported action: {action}")

        try:
            self.start_steam_wishlist_mutation_worker(steamid64, app_id, action)
            if action == "add":
                return plugin_tr(self, "wishlist.adding", app_id=app_id)
            return plugin_tr(self, "wishlist.removing", app_id=app_id)
        except Exception as error:
            return plugin_tr(self, "wishlist.mutation_failed", error=str(error))

    def add_to_steam_wishlist(self, app_id, steamid64=None):
        return self.mutate_steam_wishlist(app_id, "add", steamid64=steamid64)

    def remove_from_steam_wishlist(self, app_id, steamid64=None):
        return self.mutate_steam_wishlist(app_id, "remove", steamid64=steamid64)

    def context_menu(self, data):
        if not isinstance(data, dict):
            return

        if data.get("menu") == "steam_client":
            self._add_menu_entries(
                get_steam_client_context_menu_entries(
                    self.default_icon,
                    self.settings_icon,
                    self.community_icon,
                    self.wishlist_icon,
                    self.top_sellers_icon,
                    self.deals_icon,
                    tr=getattr(self, "tr", None),
                )
            )
            return

        app_id = str(data.get("app_id", ""))
        name = data.get("name", "Game")
        install_path = data.get("install_path")
        is_owned = bool(data.get("is_owned"))
        refund_state = self.derive_refund_state(data)
        is_unreleased = self.derive_is_unreleased(data)
        result_source = str(data.get("result_source", "") or "")
        store_type = str(data.get("store_type", "") or "")
        steamid64 = str(data.get("steamid64", "") or "")
        is_free = data.get("is_free")
        is_wishlisted = bool(data.get("is_wishlisted")) or result_source == "wishlist"
        wishlist_actions_enabled = bool(data.get("wishlist_actions_enabled", True))
        feature_health_cache_file = getattr(
            self,
            "feature_health_cache_file",
            self.plugin_dir / "cache_feature_health.json",
        )
        can_add_to_cart = (
            is_store_cart_result_source(result_source)
            and store_type in {"", "game"}
            and not install_path
            and not is_owned
            and not is_unreleased
            and is_free is not True
            and feature_enabled(feature_health_cache_file, "steam_cart")
            and feature_enabled(feature_health_cache_file, "steam_session_token")
        )
        can_add_to_wishlist = (
            is_store_action_result_source(result_source)
            and store_type in {"", "game"}
            and not install_path
            and not is_owned
            and not is_wishlisted
            and wishlist_actions_enabled
            and feature_enabled(feature_health_cache_file, "steam_session_token")
            and feature_enabled(feature_health_cache_file, "steam_wishlist")
        )
        can_remove_from_wishlist = (
            bool(app_id)
            and not install_path
            and not is_owned
            and is_wishlisted
            and wishlist_actions_enabled
            and feature_enabled(feature_health_cache_file, "steam_session_token")
            and feature_enabled(feature_health_cache_file, "steam_wishlist")
        )

        self._add_menu_entries(
            get_game_context_menu_entries(
                app_id,
                name,
                install_path,
                is_owned,
                refund_state,
                self.default_icon,
                self.steamdb_icon,
                self.buy_icon,
                self.csrin_icon,
                self.guides_icon,
                self.discussions_icon,
                self.screenshot_icon,
                self.refund_icon,
                self.properties_icon,
                self.location_icon,
                self.download_icon,
                self.trash_icon,
                self.wishlist_add_icon,
                self.wishlist_remove_icon,
                is_unreleased=is_unreleased,
                can_add_to_cart=can_add_to_cart,
                can_add_to_wishlist=can_add_to_wishlist,
                can_remove_from_wishlist=can_remove_from_wishlist,
                show_steamdb=self.get_setting_bool("show_steamdb_context_menu", True),
                show_csrin=self.get_setting_bool("show_csrin_context_menu", True),
                steamid64=steamid64,
                tr=getattr(self, "tr", None),
            )
        )
