from urllib.parse import quote_plus
from pathlib import Path

from .hooks import (
    ensure_startup_initialized_if_needed,
    log_exception_if_supported,
    log_if_supported,
    reset_plugin_query_if_supported,
    schedule_installed_games_refresh_if_supported,
)
from .localization import plugin_tr
from .os_integration import (
    STEAM_FRIENDS_STATUS_URIS,
    STEAM_FRIENDS_URI,
    STEAM_GAMES_URI,
    STEAM_SETTINGS_URI,
    STEAM_STORE_SPECIALS_URL,
    STEAM_STORE_TOP_SELLERS_URL,
    build_steam_discussions_uri,
    build_steam_friend_game_uri,
    build_steam_friend_join_game_uri,
    build_steam_friend_message_uri,
    build_steam_game_properties_uri,
    build_steam_guides_uri,
    build_steam_install_uri,
    build_steam_join_lobby_uri,
    build_steam_library_details_uri,
    build_steam_profile_uri,
    build_steam_profile_url,
    build_steam_refund_uri,
    build_steam_screenshots_uri,
    build_steam_store_uri,
    build_steam_store_url,
    build_steam_store_specials_uri,
    build_steam_store_top_sellers_uri,
    build_steam_trade_offer_uri,
    build_steam_uninstall_uri,
    build_steam_wishlist_uri,
    build_steam_wishlist_url,
    open_uri,
    open_web_url,
    run_executable,
)


class SteamPluginActionsMixin:
    STEAM_GAMES_URI = STEAM_GAMES_URI
    STEAM_FRIENDS_STATUS_URIS = STEAM_FRIENDS_STATUS_URIS

    def _log_action_error(self, message):
        log_if_supported(self, "error", message)

    def _log_action_exception(self, message):
        log_exception_if_supported(self, message)

    def _action_message(self, key, **values):
        return plugin_tr(self, key, **values)

    def open_steam_store_page(self, app_id):
        uri = build_steam_store_uri(app_id)
        try:
            open_uri(uri)
            return self._action_message("steam_action.store_opened", app_id=app_id)
        except Exception:
            try:
                open_web_url(build_steam_store_url(app_id))
                return self._action_message("steam_action.store_browser_opened", app_id=app_id)
            except Exception as error:
                self._log_action_error(f"Failed to open Steam store page for app {app_id}: {error}")
                return self._action_message("steam_action.store_failed", error=str(error))

    def open_steam_guides_page(self, app_id):
        uri = build_steam_guides_uri(app_id)
        try:
            open_uri(uri)
            return self._action_message("steam_action.guides_opened", app_id=app_id)
        except Exception as error:
            self._log_action_error(f"Failed to open Steam guides for app {app_id}: {error}")
            return self._action_message("steam_action.guides_failed", error=str(error))

    def open_steam_discussions_page(self, app_id):
        uri = build_steam_discussions_uri(app_id)
        try:
            open_uri(uri)
            return self._action_message("steam_action.discussions_opened", app_id=app_id)
        except Exception as error:
            self._log_action_error(f"Failed to open Steam discussions for app {app_id}: {error}")
            return self._action_message("steam_action.discussions_failed", error=str(error))

    def open_steam_game_properties_page(self, app_id):
        uri = build_steam_game_properties_uri(app_id)
        try:
            open_uri(uri)
            return self._action_message("steam_action.properties_opened", app_id=app_id)
        except Exception as error:
            self._log_action_error(f"Failed to open Steam game properties for app {app_id}: {error}")
            return self._action_message("steam_action.properties_failed", error=str(error))

    def open_steam_screenshots_page(self, app_id):
        uri = build_steam_screenshots_uri(app_id)
        try:
            open_uri(uri)
            return self._action_message("steam_action.screenshots_opened", app_id=app_id)
        except Exception as error:
            self._log_action_error(f"Failed to open Steam recordings and screenshots for app {app_id}: {error}")
            return self._action_message("steam_action.screenshots_failed", error=str(error))

    def open_steam_refund_page(self, app_id):
        uri = build_steam_refund_uri(app_id)
        try:
            open_uri(uri)
            return self._action_message("steam_action.refund_opened", app_id=app_id)
        except Exception as error:
            self._log_action_error(f"Failed to open Steam refund page for app {app_id}: {error}")
            return self._action_message("steam_action.refund_failed", error=str(error))

    def open_steam(self):
        try:
            open_uri(self.STEAM_GAMES_URI)
            return self._action_message("steam_action.opened")
        except Exception:
            ensure_startup_initialized_if_needed(self)
            steam_path = getattr(self, "steam_path", None)
            if steam_path:
                steam_exe = Path(steam_path) / "steam.exe"
                if steam_exe.exists():
                    try:
                        run_executable(steam_exe)
                        return self._action_message("steam_action.opened")
                    except Exception:
                        self._log_action_exception("Failed to launch steam.exe directly")
            return self._action_message("steam_action.open_failed")

    def open_steam_settings(self):
        try:
            open_uri(STEAM_SETTINGS_URI)
            return self._action_message("steam_action.settings_opened")
        except Exception as error:
            self._log_action_error(f"Failed to open Steam settings: {error}")
            return self._action_message("steam_action.settings_failed", error=str(error))

    def open_steam_friends(self):
        try:
            open_uri(STEAM_FRIENDS_URI)
            return self._action_message("steam_action.friends_opened")
        except Exception as error:
            self._log_action_error(f"Failed to open Steam friends: {error}")
            return self._action_message("steam_action.friends_failed", error=str(error))

    def open_steam_friend_chat(self, steamid64):
        steamid64 = str(steamid64 or "").strip()
        if not steamid64:
            return self._action_message("steam_action.friend_missing")
        try:
            open_uri(build_steam_friend_message_uri(steamid64))
            return self._action_message("steam_action.friend_chat_opened")
        except Exception as error:
            self._log_action_error(f"Failed to open Steam chat for {steamid64}: {error}")
            return self._action_message("steam_action.friend_chat_failed", error=str(error))

    def open_steam_friend_profile(self, steamid64):
        steamid64 = str(steamid64 or "").strip()
        if not steamid64:
            return self._action_message("steam_action.friend_missing")
        try:
            open_uri(build_steam_profile_uri(steamid64))
            return self._action_message("steam_action.friend_profile_opened")
        except Exception:
            try:
                open_web_url(build_steam_profile_url(steamid64))
                return self._action_message("steam_action.friend_profile_browser_opened")
            except Exception as error:
                self._log_action_error(f"Failed to open Steam profile for {steamid64}: {error}")
                return self._action_message("steam_action.friend_profile_failed", error=str(error))

    def open_steam_friend_trade_offer(self, steamid64):
        steamid64 = str(steamid64 or "").strip()
        if not steamid64:
            return self._action_message("steam_action.friend_missing")
        try:
            uri = build_steam_trade_offer_uri(steamid64)
        except ValueError:
            return self._action_message("steam_action.friend_invalid")
        try:
            open_uri(uri)
            return self._action_message("steam_action.friend_trade_opened")
        except Exception as error:
            self._log_action_error(f"Failed to open Steam trade offer for {steamid64}: {error}")
            return self._action_message("steam_action.friend_trade_failed", error=str(error))

    def open_steam_friend_game(self, gameid):
        gameid = str(gameid or "").strip()
        if not gameid:
            return self._action_message("steam_action.friend_game_missing")
        try:
            open_uri(build_steam_friend_game_uri(gameid))
            return self._action_message("steam_action.friend_game_opened")
        except Exception as error:
            self._log_action_error(f"Failed to open Steam game {gameid}: {error}")
            return self._action_message("steam_action.friend_game_failed", error=str(error))

    def join_steam_friend_game(self, steamid64, app_id):
        steamid64 = str(steamid64 or "").strip()
        app_id = str(app_id or "").strip()
        if not steamid64 or not app_id:
            return self._action_message("steam_action.friend_join_missing")
        get_candidates = getattr(self, "get_joinable_friends_for_app", None)
        if not callable(get_candidates):
            return self._action_message("steam_action.friend_join_unavailable")
        candidates = get_candidates(
            app_id,
            only_steamid64=steamid64,
            force_refresh=True,
        )
        candidate = next(
            (
                candidate
                for candidate in candidates or ()
                if (
                    isinstance(candidate, dict)
                    and str(candidate.get("steamid64", "") or "") == steamid64
                )
            ),
            None,
        )
        if candidate is None:
            return self._action_message("steam_action.friend_join_expired")
        lobby_id = str(candidate.get("lobby_id", "") or "").strip()
        try:
            uri = (
                build_steam_join_lobby_uri(app_id, lobby_id, steamid64)
                if lobby_id
                else build_steam_friend_join_game_uri(steamid64)
            )
            open_uri(uri)
            return self._action_message("steam_action.friend_join_opened")
        except Exception as error:
            self._log_action_error(
                f"Failed to join Steam friend game for {steamid64}: {error}"
            )
            return self._action_message(
                "steam_action.friend_join_failed",
                error=str(error),
            )

    def set_steam_friends_status(self, status):
        normalized_status = str(status or "").strip().lower()
        uri = self.STEAM_FRIENDS_STATUS_URIS.get(normalized_status)
        if not uri:
            return self._action_message("steam_action.invalid_status", status=status)

        try:
            open_uri(uri)
            try:
                reset_plugin_query_if_supported(self)
            except Exception:
                self._log_action_exception("Failed to reset launcher query after changing Steam status")
            return self._action_message("steam_action.status_set", status=normalized_status.title())
        except Exception as error:
            self._log_action_error(f"Failed to set Steam friends status to {normalized_status}: {error}")
            return self._action_message("steam_action.status_failed", error=str(error))

    def open_steam_library_game_details(self, app_id):
        uri = build_steam_library_details_uri(app_id)
        try:
            open_uri(uri)
            return self._action_message("steam_action.library_details_opened", app_id=app_id)
        except Exception as error:
            self._log_action_error(f"Failed to open Steam library details for app {app_id}: {error}")
            return self._action_message("steam_action.library_details_failed", error=str(error))

    def open_my_steam_wishlist(self):
        uri = build_steam_wishlist_uri()
        try:
            open_uri(uri)
            return self._action_message("steam_action.wishlist_opened")
        except Exception:
            try:
                open_web_url(build_steam_wishlist_url())
                return self._action_message("steam_action.wishlist_browser_opened")
            except Exception as error:
                self._log_action_error(f"Failed to open Steam wishlist: {error}")
                return self._action_message("steam_action.wishlist_failed", error=str(error))

    def open_steam_top_sellers(self):
        uri = build_steam_store_top_sellers_uri()
        try:
            open_uri(uri)
            return self._action_message("steam_action.top_sellers_opened")
        except Exception:
            try:
                open_web_url(STEAM_STORE_TOP_SELLERS_URL)
                return self._action_message("steam_action.top_sellers_browser_opened")
            except Exception as error:
                self._log_action_error(f"Failed to open Steam top sellers: {error}")
                return self._action_message("steam_action.top_sellers_failed", error=str(error))

    def open_steam_specials(self):
        uri = build_steam_store_specials_uri()
        try:
            open_uri(uri)
            return self._action_message("steam_action.specials_opened")
        except Exception:
            try:
                open_web_url(STEAM_STORE_SPECIALS_URL)
                return self._action_message("steam_action.specials_browser_opened")
            except Exception as error:
                self._log_action_error(f"Failed to open Steam specials: {error}")
                return self._action_message("steam_action.specials_failed", error=str(error))

    def install_steam_game(self, app_id):
        try:
            open_uri(build_steam_install_uri(app_id))
            schedule_installed_games_refresh_if_supported(self, delay_seconds=2)
            return self._action_message("steam_action.install_opened", app_id=app_id)
        except Exception as error:
            self._log_action_error(f"Failed to install Steam game {app_id}: {error}")
            return self._action_message("steam_action.install_failed", error=str(error))

    def uninstall_steam_game(self, app_id):
        try:
            open_uri(build_steam_uninstall_uri(app_id))
            schedule_installed_games_refresh_if_supported(self, delay_seconds=2)
            return self._action_message("steam_action.uninstall_opened", app_id=app_id)
        except Exception as error:
            self._log_action_error(f"Failed to uninstall Steam game {app_id}: {error}")
            return self._action_message("steam_action.uninstall_failed", error=str(error))

    def open_local_files(self, install_path):
        try:
            if install_path and Path(install_path).exists():
                open_uri(install_path)
                return self._action_message("steam_action.local_files_opened")
            return self._action_message("steam_action.local_files_missing")
        except Exception as error:
            self._log_action_error(f"Failed to open local files '{install_path}': {error}")
            return self._action_message("steam_action.local_files_failed", error=str(error))

    def open_steamdb_page(self, app_id):
        try:
            open_web_url(f"https://steamdb.info/app/{app_id}/")
            return self._action_message("steam_action.steamdb_opened", app_id=app_id)
        except Exception as error:
            self._log_action_error(f"Failed to open SteamDB page for app {app_id}: {error}")
            return self._action_message("steam_action.steamdb_failed", error=str(error))

    def search_csrin_page(self, name):
        query = quote_plus(str(name or "").strip())
        if not query:
            return self._action_message("action.csrin_missing_name")

        url = f"https://cs.rin.ru/forum/search.php?keywords={query}&fid[]=10&sr=topics&sf=titleonly"
        try:
            open_web_url(url)
            return self._action_message("action.csrin_opened", name=name)
        except Exception as error:
            self._log_action_error(f"Failed to open CS.RIN.RU search for '{name}': {error}")
            return self._action_message("action.csrin_open_failed", error=str(error))
