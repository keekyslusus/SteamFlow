import time

from .clipboard import get_clipboard_text
from .constants import STEAMFLOW_CONFIG
from .hooks import show_message_if_supported
from .localization import plugin_tr
from .os_integration import build_steam_openurl_uri, open_uri
from .providers import get_plugin_providers


class SteamPluginUICommandsMixin:
    CONFIG = STEAMFLOW_CONFIG
    REQUIRED_PLUGIN_ATTRS = (
        "DEALS_ICON",
        "TOP_SELLERS_ICON",
    )
    REQUIRED_PLUGIN_PROVIDERS = (
        "account",
        "local",
        "owned_api",
        "results",
        "runtime",
        "wishlist",
    )

    OWNED_API_QUERY_ALIASES = {"api", "api key", "apikey", "owned", "owned games"}
    SWITCH_ACCOUNT_QUERY_ALIASES = {"switch", "switch account", "switch accounts", "account switch", "accounts"}
    STATUS_QUERY_ALIASES = {"status", "statuses"}
    WISHLIST_QUERY_ALIASES = {"wishlist", "wish list"}
    STORE_COLLECTION_QUERY_ALIASES = {
        "top": "top_sellers",
        "seller": "top_sellers",
        "sellers": "top_sellers",
        "top seller": "top_sellers",
        "top sellers": "top_sellers",
        "special": "specials",
        "specials": "specials",
        "deal": "specials",
        "deals": "specials",
    }
    HELP_QUERY_ALIASES = {"?"}
    STEAM_STATUS_OPTIONS = (
        ("online", "status.option.online"),
        ("offline", "status.option.offline"),
        ("invisible", "status.option.invisible"),
    )
    FEATURE_HEALTH_STATUS_FEATURES = (
        ("download_control", "api.feature_health.label.download_control"),
        ("steam_cart", "api.feature_health.label.steam_cart"),
        ("steam_wishlist", "api.feature_health.label.steam_wishlist"),
        ("steam_session_token", "api.feature_health.label.token_cache"),
    )
    STATUS_CURRENT_RESULT_SCORE = 1_000_000
    STATUS_OPTION_BASE_SCORE = 999_000

    @property
    def ui_command_providers(self):
        return get_plugin_providers(self)

    def get_status_icon_path(self, status_key):
        return {
            "online": self.ONLINE_ICON,
            "offline": self.OFFLINE_ICON,
            "invisible": self.INVISIBLE_ICON,
        }.get(str(status_key or "").strip().lower(), self.COMMUNITY_ICON)

    def is_owned_api_query(self, search_term):
        normalized = str(search_term or "").strip().lower()
        return normalized in self.OWNED_API_QUERY_ALIASES

    def is_switch_account_query(self, search_term):
        normalized = str(search_term or "").strip().lower()
        return normalized in self.SWITCH_ACCOUNT_QUERY_ALIASES

    def is_status_query(self, search_term):
        normalized = str(search_term or "").strip().lower()
        return normalized in self.STATUS_QUERY_ALIASES

    def is_wishlist_query(self, search_term):
        return self.get_wishlist_query_text(search_term) is not None

    def get_store_collection_query(self, search_term):
        normalized = str(search_term or "").strip().lower()
        return self.STORE_COLLECTION_QUERY_ALIASES.get(normalized)

    def is_help_query(self, search_term):
        normalized = str(search_term or "").strip().lower()
        return normalized in self.HELP_QUERY_ALIASES

    def get_wishlist_query_text(self, search_term):
        raw_value = str(search_term or "").strip()
        normalized = raw_value.lower()
        first_token = normalized.split(" ", 1)[0]
        if first_token.startswith("wishl"):
            return raw_value.split(" ", 1)[1].strip() if " " in raw_value else ""
        for alias in sorted(self.WISHLIST_QUERY_ALIASES, key=len, reverse=True):
            if normalized == alias:
                return ""
            prefix = f"{alias} "
            if normalized.startswith(prefix):
                return raw_value[len(alias) :].strip()
        return None

    def build_switch_account_results(self):
        account_provider = self.ui_command_providers.account
        result_provider = self.ui_command_providers.results
        switchable_accounts = account_provider.switchable_accounts()
        if not switchable_accounts:
            return [
                result_provider.build_result(
                    title=plugin_tr(self, "switch.none.title"),
                    subtitle=plugin_tr(self, "switch.none.subtitle"),
                    icon_path=self.DEFAULT_ICON,
                    Score=21000,
                )
            ]

        results = []
        for score_offset, account in enumerate(switchable_accounts, start=1):
            account_label = account_provider.account_label(account)
            subtitle = plugin_tr(self, "switch.to_account", account_label=account_label)
            account_name = str(account.get("account_name", "") or "").strip()
            if account_name and account_name != account_label:
                subtitle += f" | @{account_name}"
            if not account.get("remember_password", True):
                subtitle += f" | {plugin_tr(self, 'switch.password_required')}"
            results.append(
                result_provider.build_result(
                    title=account_label,
                    subtitle=subtitle,
                    icon_path=account.get("icon_path") or self.DEFAULT_ICON,
                    action=result_provider.build_action("switch_steam_account", account.get("steamid64")),
                    Score=21001 - score_offset,
                )
            )

        return results

    def build_help_results(self):
        result_provider = self.ui_command_providers.results
        api_query = result_provider.build_plugin_query("api")
        switch_query = result_provider.build_plugin_query("switch")
        status_query = result_provider.build_plugin_query("status")
        wishlist_query = result_provider.build_plugin_query("wishlist")
        top_query = result_provider.build_plugin_query("top")
        deals_query = result_provider.build_plugin_query("deals")

        wishlist_items, wishlist_error = self.ui_command_providers.wishlist.items()
        wishlist_subtitle = plugin_tr(self, "command.wishlist.subtitle")
        reasons = self.CONFIG.availability_reasons
        if wishlist_error == reasons.api_not_configured:
            wishlist_subtitle += f" | {plugin_tr(self, 'command.wishlist.unavailable_api')}"
        elif wishlist_error == reasons.api_bound_to_another_account:
            wishlist_subtitle += f" | {plugin_tr(self, 'command.wishlist.unavailable_bound')}"
        elif wishlist_error == reasons.no_active_account:
            wishlist_subtitle += f" | {plugin_tr(self, 'command.wishlist.unavailable_no_account')}"

        return [
            result_provider.build_result(
                title=api_query,
                subtitle=plugin_tr(self, "command.api.subtitle"),
                icon_path=self.OWNED_ICON,
                action=result_provider.build_change_query_action(api_query),
                Score=22000,
            ),
            result_provider.build_result(
                title=switch_query,
                subtitle=plugin_tr(self, "command.switch.subtitle"),
                icon_path=self.COMMUNITY_ICON,
                action=result_provider.build_change_query_action(switch_query),
                Score=21999,
            ),
            result_provider.build_result(
                title=status_query,
                subtitle=plugin_tr(self, "command.status.subtitle"),
                icon_path=self.ONLINE_ICON,
                action=result_provider.build_change_query_action(status_query),
                Score=21998,
            ),
            result_provider.build_result(
                title=wishlist_query,
                subtitle=wishlist_subtitle,
                icon_path=self.WISHLIST_ICON,
                action=result_provider.build_change_query_action(wishlist_query),
                Score=21997,
            ),
            result_provider.build_result(
                title=top_query,
                subtitle=plugin_tr(self, "command.top_sellers.subtitle"),
                icon_path=self.TOP_SELLERS_ICON,
                action=result_provider.build_change_query_action(top_query),
                Score=21996,
            ),
            result_provider.build_result(
                title=deals_query,
                subtitle=plugin_tr(self, "command.specials.subtitle"),
                icon_path=self.DEALS_ICON,
                action=result_provider.build_change_query_action(deals_query),
                Score=21995,
            ),
        ]

    def build_status_results(self):
        account_provider = self.ui_command_providers.account
        local_provider = self.ui_command_providers.local
        result_provider = self.ui_command_providers.results
        status_query = result_provider.build_plugin_query("status")
        steamid64 = account_provider.active_steamid64()
        if not steamid64:
            return [
                result_provider.build_result(
                    title=plugin_tr(self, "status.no_active_account.title"),
                    subtitle=plugin_tr(self, "status.no_active_account.subtitle"),
                    icon_path=self.COMMUNITY_ICON,
                    action=result_provider.build_change_query_action(status_query),
                    Score=self.STATUS_CURRENT_RESULT_SCORE,
                )
            ]

        user_details = account_provider.user_details(steamid64)
        account_label = (
            str(user_details.get("persona_name", "") or "").strip()
            or str(user_details.get("account_name", "") or "").strip()
            or plugin_tr(self, "ui.steam_user")
        )
        current_state = local_provider.active_persona_state()
        current_label = local_provider.persona_state_label(current_state)
        current_protocol = local_provider.persona_state_protocol(current_state)

        if current_label:
            current_result = result_provider.build_result(
                title=plugin_tr(self, "status.current", status=current_label),
                subtitle=plugin_tr(self, "status.choose_different", account_label=account_label),
                icon_path=self.get_status_icon_path(current_protocol),
                action=result_provider.build_change_query_action(status_query),
                Score=self.STATUS_CURRENT_RESULT_SCORE,
            )
        else:
            current_result = result_provider.build_result(
                title=plugin_tr(self, "status.current_unknown"),
                subtitle=plugin_tr(self, "status.choose", account_label=account_label),
                icon_path=self.WARNING_ICON,
                action=result_provider.build_change_query_action(status_query),
                Score=self.STATUS_CURRENT_RESULT_SCORE,
            )

        results = [current_result]
        for score_offset, (status_key, status_label_key) in enumerate(self.STEAM_STATUS_OPTIONS, start=1):
            if current_protocol == status_key:
                continue
            status_label = plugin_tr(self, status_label_key)

            results.append(
                result_provider.build_result(
                    title=status_label,
                    subtitle=plugin_tr(self, "status.set_to", status=status_label.lower()),
                    icon_path=self.get_status_icon_path(status_key),
                    action=result_provider.build_action("set_steam_friends_status", status_key),
                    Score=self.STATUS_OPTION_BASE_SCORE - score_offset,
                )
            )

        return results

    def build_owned_api_results(self):
        account_provider = self.ui_command_providers.account
        owned_api_provider = self.ui_command_providers.owned_api
        result_provider = self.ui_command_providers.results
        status_title, status_subtitle = owned_api_provider.status()
        status_result = result_provider.build_result(
            title=status_title,
            subtitle=status_subtitle,
            icon_path=self.OWNED_ICON,
            Score=19997 if not account_provider.has_owned_api_key() else 20000,
        )
        reset_feature_health_result = self.build_feature_health_reset_result(result_provider)
        save_key_result = result_provider.build_result(
            title=plugin_tr(self, "api.save_key.title"),
            subtitle=plugin_tr(self, "api.save_key.subtitle"),
            icon_path=self.CLIPBOARD_ICON,
            action=result_provider.build_action("save_owned_api_key_from_clipboard"),
            Score=19999,
        )
        remove_key_result = result_provider.build_result(
            title=plugin_tr(self, "api.remove_key.title"),
            subtitle=plugin_tr(self, "api.remove_key.subtitle"),
            icon_path=self.TRASH_ICON,
            action=result_provider.build_action("remove_owned_api_key_action"),
            Score=19998,
        )
        open_key_page_result = result_provider.build_result(
            title=plugin_tr(self, "api.open_key_page.title"),
            subtitle=plugin_tr(self, "api.open_key_page.subtitle"),
            icon_path=self.BROWSER_ICON,
            action=result_provider.build_action("open_steam_web_api_key_page"),
            Score=20000,
        )

        if account_provider.has_owned_api_key():
            results = [
                status_result,
                remove_key_result,
                reset_feature_health_result,
            ]
        else:
            results = [
                open_key_page_result,
                save_key_result,
                status_result,
                reset_feature_health_result,
            ]
        return results

    def build_feature_health_reset_result(self, result_provider):
        title = plugin_tr(self, "api.reset_feature_health.title")
        subtitle = plugin_tr(self, "api.reset_feature_health.subtitle")
        get_status = getattr(self, "get_feature_health_status", None)
        feature_enabled = getattr(self, "feature_enabled", None)

        if callable(get_status):
            labels = []
            problem_details = []
            for feature_name, label_key in self.FEATURE_HEALTH_STATUS_FEATURES:
                label = plugin_tr(self, label_key)
                labels.append(label)
                try:
                    status = get_status(feature_name)
                    enabled = feature_enabled(feature_name) if callable(feature_enabled) else True
                except Exception:
                    continue

                state = str(status.get("state") or "healthy").strip().lower()
                last_reason = str(status.get("last_reason") or "").strip() or plugin_tr(
                    self,
                    "api.feature_health.reason_unknown",
                )
                if state == "disabled" or not enabled:
                    problem_details.append(
                        plugin_tr(
                            self,
                            "api.feature_health.detail.disabled",
                            label=label,
                            reason=last_reason,
                        )
                    )
                elif state == "suspect":
                    problem_details.append(
                        plugin_tr(
                            self,
                            "api.feature_health.detail.suspect",
                            label=label,
                            reason=last_reason,
                        )
                    )

            if problem_details:
                title = plugin_tr(self, "api.feature_health.title.needs_attention", count=len(problem_details))
                subtitle = plugin_tr(
                    self,
                    "api.feature_health.subtitle.problem",
                    details="; ".join(problem_details),
                )
            else:
                title = plugin_tr(self, "api.feature_health.title.all_ok")
                subtitle = plugin_tr(
                    self,
                    "api.feature_health.subtitle.all_ok",
                    features=", ".join(labels),
                )

        return result_provider.build_result(
            title=title,
            subtitle=subtitle,
            icon_path=self.FEATURE_HEALTH_RESET_ICON,
            action=result_provider.build_action("reset_feature_health_action"),
            Score=19996,
        )

    def show_owned_api_message(self, title, subtitle):
        try:
            show_message_if_supported(self, title, subtitle, self.OWNED_ICON)
        except Exception:
            pass

    def save_owned_api_key_from_clipboard(self):
        providers = self.ui_command_providers
        providers.runtime.ensure_startup_initialized()
        clipboard_text = get_clipboard_text()
        api_key = providers.owned_api.normalize_key(clipboard_text)
        if not api_key:
            message = plugin_tr(self, "api.valid_clipboard_missing")
            self.show_owned_api_message(plugin_tr(self, "api.key_not_saved"), message)
            return message

        steamid64 = providers.account.active_steamid64()
        if not steamid64:
            message = plugin_tr(self, "action.no_active_account")
            self.show_owned_api_message(plugin_tr(self, "api.key_not_saved"), message)
            return message

        try:
            owned_app_ids, owned_game_playtimes = providers.owned_api.fetch_owned_app_ids(api_key, steamid64, timeout=5)
        except Exception as error:
            providers.runtime.log("error", f"Failed to validate Steam API key: {error}")
            error_message = str(error).strip()
            if error_message:
                message = plugin_tr(self, "action.validation_failed_detail", error=error_message)
            else:
                message = plugin_tr(self, "action.validation_failed")
            self.show_owned_api_message(plugin_tr(self, "api.key_not_saved"), message)
            return message

        user_details = providers.account.user_details(steamid64)
        providers.owned_api.save_key(
            api_key,
            steamid64,
            persona_name=user_details.get("persona_name"),
            account_name=user_details.get("account_name"),
        )
        with self.state_lock:
            self.owned_games_last_attempt = time.time()
            self.owned_games_last_sync = time.time()
            self.owned_games_public_profile = True
            self.owned_games_steamid64 = steamid64
            self.owned_app_ids = set(owned_app_ids)
            self.owned_game_playtimes = dict(owned_game_playtimes)
            self.owned_games_cache_loaded = True
        providers.owned_api.save_owned_games_cache()
        message = plugin_tr(
            self,
            "api.key_saved_bound",
            account_label=user_details.get("persona_name") or steamid64,
        )
        self.show_owned_api_message(plugin_tr(self, "api.key_saved"), message)
        return message

    def remove_owned_api_key_action(self):
        self.ui_command_providers.runtime.ensure_startup_initialized()
        self.ui_command_providers.owned_api.remove_key()
        message = plugin_tr(self, "action.stored_key_removed")
        self.show_owned_api_message(plugin_tr(self, "api.key_removed"), message)
        return message

    def reset_feature_health_action(self):
        reset = getattr(self, "reset_feature_health", None)
        if not callable(reset):
            return plugin_tr(self, "action.feature_health_unavailable")
        reset()
        try:
            show_message_if_supported(
                self,
                plugin_tr(self, "action.feature_health_reset_title"),
                plugin_tr(self, "action.feature_health_reset_message"),
                self.FEATURE_HEALTH_RESET_ICON,
            )
        except Exception:
            pass
        return plugin_tr(self, "action.feature_health_reset")

    def open_steam_web_api_key_page(self):
        try:
            open_uri(build_steam_openurl_uri("https://steamcommunity.com/dev/apikey"))
            return plugin_tr(self, "action.open_api_key_success")
        except Exception as error:
            self.ui_command_providers.runtime.log("error", f"Failed to open Steam Web API key page: {error}")
            return plugin_tr(
                self,
                "action.open_api_key_failed",
                error=str(error),
            )
