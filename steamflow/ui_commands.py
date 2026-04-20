import time
import webbrowser

from flox.clipboard import get as get_clipboard_text


class SteamPluginUICommandsMixin:
    OWNED_API_QUERY_ALIASES = {"api", "api key", "apikey", "owned", "owned games"}
    SWITCH_ACCOUNT_QUERY_ALIASES = {"switch", "switch account", "switch accounts", "account switch", "accounts"}
    STATUS_QUERY_ALIASES = {"status", "statuses"}
    WISHLIST_QUERY_ALIASES = {"wishlist", "wish list"}
    HELP_QUERY_ALIASES = {"?"}
    STEAM_STATUS_OPTIONS = (
        ("online", "Online"),
        ("offline", "Offline"),
        ("invisible", "Invisible"),
    )
    STATUS_CURRENT_RESULT_SCORE = 1_000_000
    STATUS_OPTION_BASE_SCORE = 999_000

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
        switchable_accounts = self.get_switchable_steam_accounts()
        if not switchable_accounts:
            return [
                self.build_result(
                    title="No Other Steam Accounts Found",
                    subtitle="Sign into another Steam account on this PC to make it available here",
                    icon_path=self.DEFAULT_ICON,
                    Score=21000,
                )
            ]

        results = []
        for score_offset, account in enumerate(switchable_accounts, start=1):
            account_label = self.get_steam_account_label(account)
            subtitle = f"Switch to {account_label} and restart Steam"
            account_name = str(account.get("account_name", "") or "").strip()
            if account_name and account_name != account_label:
                subtitle += f" | @{account_name}"
            if not account.get("remember_password", True):
                subtitle += " | password may be required"
            results.append(
                self.build_result(
                    title=account_label,
                    subtitle=subtitle,
                    icon_path=account.get("icon_path") or self.DEFAULT_ICON,
                    action=self.build_action("switch_steam_account", account.get("steamid64")),
                    Score=21001 - score_offset,
                )
            )

        return results

    def build_help_results(self):
        api_query = self.build_plugin_query("api")
        switch_query = self.build_plugin_query("switch")
        status_query = self.build_plugin_query("status")
        wishlist_query = self.build_plugin_query("wishlist")

        wishlist_items, wishlist_error = self.get_wishlist_items()
        wishlist_subtitle = "Browse your Steam wishlist and recent additions"
        if wishlist_error == "Steam API Not Configured":
            wishlist_subtitle += " | Unavailable: Steam API not configured"
        elif wishlist_error == "Steam API Bound to Another Account":
            wishlist_subtitle += " | Unavailable: key is bound to another account"
        elif wishlist_error == "No active Steam account found":
            wishlist_subtitle += " | Unavailable: no active Steam account"

        return [
            self.build_result(
                title=api_query,
                subtitle="Set up Steam API features and owned-game sync",
                icon_path=self.OWNED_ICON,
                action=self.build_change_query_action(api_query),
                Score=22000,
            ),
            self.build_result(
                title=switch_query,
                subtitle="Switch between Steam accounts signed in on this PC",
                icon_path=self.COMMUNITY_ICON,
                action=self.build_change_query_action(switch_query),
                Score=21999,
            ),
            self.build_result(
                title=status_query,
                subtitle="Change your Steam status",
                icon_path=self.ONLINE_ICON,
                action=self.build_change_query_action(status_query),
                Score=21998,
            ),
            self.build_result(
                title=wishlist_query,
                subtitle=wishlist_subtitle,
                icon_path=self.WISHLIST_ICON,
                action=self.build_change_query_action(wishlist_query),
                Score=21997,
            ),
        ]

    def build_status_results(self):
        status_query = self.build_plugin_query("status")
        steamid64 = self.get_active_steam_user_steamid64()
        if not steamid64:
            return [
                self.build_result(
                    title="No Active Steam Account Found",
                    subtitle="Sign into Steam on this PC to change your status",
                    icon_path=self.COMMUNITY_ICON,
                    action=self.build_change_query_action(status_query),
                    Score=self.STATUS_CURRENT_RESULT_SCORE,
                )
            ]

        user_details = self.get_steam_user_details(steamid64)
        account_label = (
            str(user_details.get("persona_name", "") or "").strip()
            or str(user_details.get("account_name", "") or "").strip()
            or "Steam user"
        )
        current_state = self.get_active_local_persona_state()
        current_label = self.get_local_persona_state_label(current_state)
        current_protocol = self.get_local_persona_state_protocol(current_state)

        if current_label:
            current_result = self.build_result(
                title=f"Current Status: {current_label}",
                subtitle=f"Choose a different status for {account_label}",
                icon_path=self.get_status_icon_path(current_protocol),
                action=self.build_change_query_action(status_query),
                Score=self.STATUS_CURRENT_RESULT_SCORE,
            )
        else:
            current_result = self.build_result(
                title="Current Status Unknown",
                subtitle=f"Choose a status for {account_label}",
                icon_path=self.WARNING_ICON,
                action=self.build_change_query_action(status_query),
                Score=self.STATUS_CURRENT_RESULT_SCORE,
            )

        results = [current_result]
        for score_offset, (status_key, status_label) in enumerate(self.STEAM_STATUS_OPTIONS, start=1):
            if current_protocol == status_key:
                continue

            results.append(
                self.build_result(
                    title=status_label,
                    subtitle=f"Set Steam status to {status_label.lower()}",
                    icon_path=self.get_status_icon_path(status_key),
                    action=self.build_action("set_steam_friends_status", status_key),
                    Score=self.STATUS_OPTION_BASE_SCORE - score_offset,
                )
            )

        return results

    def build_owned_api_results(self):
        status_title, status_subtitle = self.get_owned_games_status()
        status_result = self.build_result(
            title=status_title,
            subtitle=status_subtitle,
            icon_path=self.OWNED_ICON,
            Score=19997 if not self.has_owned_api_key() else 20000,
        )
        save_key_result = self.build_result(
            title="Save API Key From Clipboard",
            subtitle="Read the Steam Web API key from the clipboard, encrypt it with DPAPI, and bind it to the active Steam account",
            icon_path=self.CLIPBOARD_ICON,
            action=self.build_action("save_owned_api_key_from_clipboard"),
            Score=19999,
        )
        remove_key_result = self.build_result(
            title="Remove Stored Key",
            subtitle="Delete the encrypted Steam Web API key and clear cached Steam account data",
            icon_path=self.TRASH_ICON,
            action=self.build_action("remove_owned_api_key_action"),
            Score=19998,
        )
        open_key_page_result = self.build_result(
            title="Open Steam Web API Key Page",
            subtitle="Open steamcommunity.com/dev/apikey in your browser",
            icon_path=self.BROWSER_ICON,
            action=self.build_action("open_steam_web_api_key_page"),
            Score=20000,
        )

        if self.has_owned_api_key():
            results = [
                status_result,
                remove_key_result,
            ]
        else:
            results = [
                open_key_page_result,
                save_key_result,
                status_result,
            ]
        return results

    def show_owned_api_message(self, title, subtitle):
        show_msg = getattr(self, "show_msg", None)
        if callable(show_msg):
            try:
                show_msg(title, subtitle, self.OWNED_ICON)
            except Exception:
                pass

    def save_owned_api_key_from_clipboard(self):
        self.ensure_startup_initialized()
        clipboard_text = get_clipboard_text()
        api_key = self.normalize_steam_web_api_key(clipboard_text)
        if not api_key:
            message = "Clipboard does not contain a valid Steam Web API key"
            self.show_owned_api_message("Steam API Key Not Saved", message)
            return message

        steamid64 = self.get_active_steam_user_steamid64()
        if not steamid64:
            message = "No active Steam account found"
            self.show_owned_api_message("Steam API Key Not Saved", message)
            return message

        try:
            owned_app_ids, owned_game_playtimes = self.fetch_owned_app_ids_from_api(api_key, steamid64, timeout=5)
        except Exception as error:
            self.log("error", f"Failed to validate Steam API key: {error}")
            error_message = str(error).strip()
            if error_message:
                message = f"Steam API key validation failed: {error_message}"
            else:
                message = "Steam API key validation failed"
            self.show_owned_api_message("Steam API Key Not Saved", message)
            return message

        user_details = self.get_steam_user_details(steamid64)
        self.save_owned_api_key(
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
        self.save_owned_games_cache()
        message = f"Steam API key saved and bound to {user_details.get('persona_name') or steamid64}"
        self.show_owned_api_message("Steam API Key Saved", message)
        return message

    def remove_owned_api_key_action(self):
        self.ensure_startup_initialized()
        self.remove_owned_api_key()
        message = "Stored Steam API key removed"
        self.show_owned_api_message("Steam API Key Removed", message)
        return message

    def open_steam_web_api_key_page(self):
        try:
            webbrowser.open("https://steamcommunity.com/dev/apikey")
            return "Steam Web API key page opened"
        except Exception as error:
            self.log("error", f"Failed to open Steam Web API key page: {error}")
            return f"Failed to open Steam Web API key page: {str(error)}"
