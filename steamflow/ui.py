from . import util_steam_date
from .constants import STEAMFLOW_CONFIG
from .download_control import build_download_control_subtitle
from .localization import plugin_tr
from .menu import (
    get_game_context_menu_entries,
    get_steam_client_context_menu_entries,
    is_store_action_result_source,
    is_store_cart_result_source,
)
from .os_integration import build_steam_run_game_uri, open_uri, run_shell_start_uri
from .providers import get_plugin_providers


def _feature_enabled_or_default(plugin, name, default=True):
    feature_enabled = getattr(plugin, "feature_enabled", None)
    if not callable(feature_enabled):
        return default
    try:
        return bool(feature_enabled(name))
    except Exception:
        return default


class SteamPluginUIMixin:
    CONFIG = STEAMFLOW_CONFIG
    REQUIRED_PLUGIN_PROVIDERS = (
        "account",
        "download",
        "local",
        "metrics",
        "profile",
        "results",
        "settings",
        "store",
    )
    REQUIRED_PLUGIN_ATTRS = (
        "BUY_ICON",
        "COMMUNITY_ICON",
        "CSRIN_ICON",
        "DEALS_ICON",
        "DEFAULT_ICON",
        "SETTINGS_ICON",
        "TOP_SELLERS_ICON",
        "WISHLIST_ICON",
        "WISHLIST_ADD_ICON",
        "WISHLIST_REMOVE_ICON",
        "state_lock",
    )
    REQUIRED_PLUGIN_METHODS = (
        "log",
    )

    @property
    def ui_providers(self):
        return get_plugin_providers(self)

    def get_launch_steam_subtitle(self):
        account_provider = self.ui_providers.account
        steamid64 = account_provider.active_steamid64()
        user_details = account_provider.user_details(steamid64)
        account_label = (
            user_details.get("persona_name")
            or user_details.get("account_name")
            or plugin_tr(self, "ui.steam_user")
        )
        subtitle = plugin_tr(self, "ui.launch_steam_subtitle", account_label=account_label)
        profile_status = self.ui_providers.profile.active_status()
        if profile_status:
            subtitle += f" | {profile_status}"
        return subtitle

    def format_playtime(self, playtime_minutes):
        if playtime_minutes is None:
            return ""
        if playtime_minutes < 60:
            return f" | {playtime_minutes}m"
        hours = playtime_minutes / 60
        return f" | {hours:.1f}h"

    def format_last_played(self, last_played_timestamp):
        if not last_played_timestamp:
            return ""
        played_on = util_steam_date.format_steam_last_played(last_played_timestamp, tr=getattr(self, "tr", None))
        if not played_on:
            return ""
        return f" | {plugin_tr(self, 'ui.last_played', date=played_on)}"

    def format_achievement_progress(self, app_id):
        if not self.ui_providers.settings.should_show_achievements():
            return ""
        achievement_progress = self.ui_providers.local.achievement_progress(app_id)
        if not achievement_progress:
            return ""
        unlocked_count, total_count = achievement_progress
        if total_count <= 0:
            return ""
        if unlocked_count <= 0 and not self.ui_providers.local.has_current_account_data(app_id):
            return ""
        return f" | {unlocked_count}/{total_count}"

    def get_platform_suffix(self, platforms):
        if not self.ui_providers.settings.should_show_platforms():
            return ""
        labels = [label for key, label in self.CONFIG.platform_labels.items() if platforms.get(key)]
        if not labels:
            return ""
        return f" ({'/'.join(labels)})"

    def build_empty_state_result(self, search_term=None):
        result_provider = self.ui_providers.results
        if search_term:
            return result_provider.build_result(
                title=plugin_tr(self, "ui.no_games_found", search_term=search_term),
                subtitle=plugin_tr(self, "ui.try_different_search"),
            )
        return result_provider.build_result(
            title="SteamFlow",
            subtitle=plugin_tr(self, "ui.no_installed_games"),
        )

    def build_search_error_result(self, search_term, error_message):
        return self.ui_providers.results.build_result(
            title=plugin_tr(self, "ui.search_failed", search_term=search_term),
            subtitle=error_message,
        )

    def build_launch_steam_result(self):
        result_provider = self.ui_providers.results
        return result_provider.build_result(
            title=plugin_tr(self, "ui.launch_steam"),
            subtitle=self.get_launch_steam_subtitle(),
            icon_path=self.ui_providers.profile.active_avatar_icon(),
            context_data={"menu": "steam_client", "name": "Steam"},
            action=result_provider.build_action("open_steam"),
            Score=10000,
        )

    def get_local_game_subtitle(self, app_id, status_label):
        return build_download_control_subtitle(
            status_label,
            control_enabled=_feature_enabled_or_default(self, "download_control"),
            tr=getattr(self, "tr", None),
        )

    def get_local_game_primary_action(self, app_id, status_label):
        desired_action = self.ui_providers.download.action_for_status(status_label)
        if desired_action and _feature_enabled_or_default(self, "download_control"):
            return self.ui_providers.results.build_action("control_steam_download", app_id, desired_action)
        return self.ui_providers.results.build_action("launch_game", app_id)

    def format_local_game_status_label(self, status_label):
        status_label = str(status_label or "").strip()
        status_keys = {
            self.CONFIG.download.status_updating: "download.status.updating",
            self.CONFIG.download.status_update_paused: "download.status.update_paused",
            self.CONFIG.download.status_update_queued: "download.status.update_queued",
            self.CONFIG.download.status_update_required: "download.status.update_required",
        }
        translation_key = status_keys.get(status_label)
        if not translation_key:
            return status_label
        return self.ui_providers.settings.tr(translation_key)

    def should_prefetch_refund_state(self, app_id):
        playtime_minutes = self.ui_providers.local.playtime_minutes(app_id)
        return playtime_minutes is None or playtime_minutes < 120

    def build_local_result(
        self,
        app_id,
        name,
        include_player_count=False,
        player_count=None,
        player_count_loaded=False,
        refund_state=None,
    ):
        local_provider = self.ui_providers.local
        settings_provider = self.ui_providers.settings
        metrics_provider = self.ui_providers.metrics
        store_provider = self.ui_providers.store
        result_provider = self.ui_providers.results
        status_label = local_provider.installed_game_status(app_id)
        status_label = local_provider.live_game_status(app_id, status_label)
        display_status_label = self.format_local_game_status_label(status_label)
        display_name = f"{name} [{display_status_label}]" if display_status_label else name
        subtitle = self.get_local_game_subtitle(app_id, status_label)
        if settings_provider.should_show_playtime():
            subtitle += self.format_playtime(local_provider.playtime_minutes(app_id))
        subtitle += self.format_achievement_progress(app_id)
        if settings_provider.should_show_last_played():
            subtitle += self.format_last_played(local_provider.last_played_timestamp(app_id))
        subtitle += local_provider.game_account_notice(app_id)
        if include_player_count and settings_provider.should_show_player_count():
            if player_count_loaded:
                subtitle += metrics_provider.format_player_count(player_count)
            else:
                subtitle += metrics_provider.format_player_count(metrics_provider.current_players(app_id))
        if self.should_prefetch_refund_state(app_id):
            store_provider.app_details_metadata(app_id, allow_network_on_miss=False)
        if refund_state is None:
            refund_state = store_provider.refund_state_for_local_game(app_id, allow_network_on_miss=False)
        playtime_minutes = local_provider.playtime_minutes(app_id)
        has_current_account_local_data = local_provider.has_current_account_data(app_id)

        return result_provider.build_result(
            title=f"\U0001F3AE {display_name}",
            subtitle=subtitle,
            icon_path=local_provider.game_icon(app_id),
            context_data=result_provider.build_context_data(
                app_id=app_id,
                name=name,
                install_path=local_provider.install_path(app_id),
                refund_state=refund_state,
                playtime_minutes=playtime_minutes,
                has_current_account_local_data=has_current_account_local_data,
            ),
            action=self.get_local_game_primary_action(app_id, status_label),
        )

    def build_context_menu_item(self, title, subtitle, method, *parameters, icon_path=None):
        result_provider = self.ui_providers.results
        return result_provider.build_result(
            title=title,
            subtitle=subtitle,
            icon_path=icon_path or self.DEFAULT_ICON,
            action=result_provider.build_action(method, *parameters),
        )

    def get_steam_client_context_menu_items(self):
        return [
            self.build_context_menu_item(
                entry["title"],
                entry["subtitle"],
                entry["method"],
                icon_path=entry["icon"],
            )
            for entry in get_steam_client_context_menu_entries(
                self.DEFAULT_ICON,
                self.SETTINGS_ICON,
                self.COMMUNITY_ICON,
                self.WISHLIST_ICON,
                self.TOP_SELLERS_ICON,
                self.DEALS_ICON,
                tr=getattr(self, "tr", None),
            )
        ]

    def get_context_menu_items(
        self,
        app_id,
        name,
        install_path,
        is_owned=False,
        refund_state="",
        result_source="",
        store_type="",
        is_free=None,
        is_wishlisted=False,
        coming_soon=False,
        steamid64=None,
        wishlist_actions_enabled=True,
    ):
        steam_cart_enabled = _feature_enabled_or_default(self, "steam_cart")
        steam_session_token_enabled = _feature_enabled_or_default(self, "steam_session_token")
        steam_wishlist_enabled = _feature_enabled_or_default(self, "steam_wishlist")
        settings_provider = self.ui_providers.settings
        show_steamdb_context_menu = settings_provider.should_show_steamdb_context_menu()
        show_csrin_context_menu = settings_provider.should_show_csrin_context_menu()
        cache_key = (
            str(app_id or ""),
            name,
            install_path or "",
            bool(is_owned),
            str(refund_state or ""),
            str(result_source or ""),
            str(store_type or ""),
            bool(is_free) if is_free is not None else None,
            bool(is_wishlisted),
            bool(coming_soon),
            str(steamid64 or ""),
            bool(wishlist_actions_enabled),
            steam_cart_enabled,
            steam_session_token_enabled,
            steam_wishlist_enabled,
            show_steamdb_context_menu,
            show_csrin_context_menu,
        )
        with self.state_lock:
            cached_items = self.context_menu_cache.get(cache_key)
        if cached_items is not None:
            return cached_items

        can_add_to_cart = (
            is_store_cart_result_source(result_source)
            and str(store_type or "") in {"", "game"}
            and not install_path
            and not is_owned
            and not coming_soon
            and is_free is not True
            and steam_cart_enabled
            and steam_session_token_enabled
        )
        can_add_to_wishlist = (
            is_store_action_result_source(result_source)
            and str(store_type or "") in {"", "game"}
            and not install_path
            and not is_owned
            and not bool(is_wishlisted)
            and bool(wishlist_actions_enabled)
            and steam_session_token_enabled
            and steam_wishlist_enabled
        )
        can_remove_from_wishlist = (
            bool(app_id)
            and not install_path
            and not is_owned
            and bool(is_wishlisted)
            and bool(wishlist_actions_enabled)
            and steam_session_token_enabled
            and steam_wishlist_enabled
        )
        items = [
            self.build_context_menu_item(
                entry["title"],
                entry["subtitle"],
                entry["method"],
                *entry.get("parameters", []),
                icon_path=entry["icon"],
            )
            for entry in get_game_context_menu_entries(
                app_id,
                name,
                install_path,
                is_owned,
                refund_state,
                self.DEFAULT_ICON,
                self.STEAMDB_ICON,
                self.BUY_ICON,
                self.CSRIN_ICON,
                self.GUIDES_ICON,
                self.DISCUSSIONS_ICON,
                self.SCREENSHOT_ICON,
                self.REFUND_ICON,
                self.PROPERTIES_ICON,
                self.LOCATION_ICON,
                self.DOWNLOAD_ICON,
                self.TRASH_ICON,
                self.WISHLIST_ADD_ICON,
                self.WISHLIST_REMOVE_ICON,
                is_unreleased=bool(coming_soon),
                can_add_to_cart=can_add_to_cart,
                can_add_to_wishlist=can_add_to_wishlist,
                can_remove_from_wishlist=can_remove_from_wishlist,
                show_steamdb=show_steamdb_context_menu,
                show_csrin=show_csrin_context_menu,
                steamid64=steamid64,
                tr=getattr(self, "tr", None),
            )
        ]

        with self.state_lock:
            self.context_menu_cache[cache_key] = items
        return items

    def context_menu(self, data):
        if not isinstance(data, dict):
            return

        if data.get("menu") == "steam_client":
            items = self.get_steam_client_context_menu_items()
            for item in items:
                self.ui_providers.results.add_result(item)
            return

        app_id = str(data.get("app_id", ""))
        name = data.get("name", "Game")
        install_path = data.get("install_path") or self.ui_providers.local.install_path(app_id)
        is_owned = bool(data.get("is_owned"))
        refund_state = str(data.get("refund_state", "") or "")
        result_source = str(data.get("result_source", "") or "")
        store_type = str(data.get("store_type", "") or "")
        is_free = data.get("is_free")
        is_wishlisted = bool(data.get("is_wishlisted")) or result_source == "wishlist"
        coming_soon = bool(data.get("coming_soon"))
        steamid64 = data.get("steamid64") or self.ui_providers.account.active_steamid64()
        wishlist_actions_enabled = data.get("wishlist_actions_enabled")
        if wishlist_actions_enabled is None:
            account_provider = self.ui_providers.account
            wishlist_actions_enabled = (
                account_provider.has_owned_api_key()
                and account_provider.api_key_bound_to_active_user()
            )

        for item in self.get_context_menu_items(
            app_id,
            name,
            install_path,
            is_owned=is_owned,
            refund_state=refund_state,
            result_source=result_source,
            store_type=store_type,
            is_free=is_free,
            is_wishlisted=is_wishlisted,
            coming_soon=coming_soon,
            steamid64=steamid64,
            wishlist_actions_enabled=wishlist_actions_enabled,
        ):
            self.ui_providers.results.add_result(item)

    def launch_game(self, app_id):
        uri = build_steam_run_game_uri(app_id)
        try:
            open_uri(uri)
            return plugin_tr(self, "action.game_launched")
        except Exception as original_error:
            try:
                run_shell_start_uri(uri)
                return plugin_tr(self, "action.game_launched")
            except Exception:
                self.log("error", f"Failed to launch game {app_id}: {original_error}")
                return plugin_tr(self, "action.game_launch_failed", error=str(original_error))
