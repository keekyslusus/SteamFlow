from dataclasses import dataclass
from functools import cached_property

from .localization import plugin_tr


@dataclass(frozen=True)
class AccountProvider:
    plugin: object

    def active_steamid64(self):
        return self.plugin.get_active_steam_user_steamid64()

    def active_user_id(self):
        return self.plugin.get_active_steam_user_id()

    def user_details(self, steamid64):
        return self.plugin.get_steam_user_details(steamid64)

    def switchable_accounts(self):
        return self.plugin.get_switchable_steam_accounts()

    def account_label(self, account_data):
        return self.plugin.get_steam_account_label(account_data)

    def active_account_ownership_state(self, app_id):
        return self.plugin.get_active_account_ownership_state(app_id)

    def has_multiple_known_accounts(self):
        return self.plugin.has_multiple_known_steam_accounts()

    def owned_api_key(self):
        return self.plugin.get_owned_api_key()

    def has_owned_api_key(self):
        return self.plugin.has_owned_api_key()

    def api_key_bound_to_active_user(self):
        return self.plugin.is_owned_api_key_bound_to_active_user()


@dataclass(frozen=True)
class StoreProvider:
    plugin: object

    def app_details_metadata(self, app_id, allow_network_on_miss=True, fetch_timeout=1.5):
        if fetch_timeout == 1.5:
            return self.plugin.get_app_details_metadata(
                app_id,
                allow_network_on_miss=allow_network_on_miss,
            )
        return self.plugin.get_app_details_metadata(
            app_id,
            allow_network_on_miss=allow_network_on_miss,
            fetch_timeout=fetch_timeout,
        )

    def refund_state_for_local_game(self, app_id, allow_network_on_miss=False):
        return self.plugin.get_refund_state_for_local_game(
            app_id,
            allow_network_on_miss=allow_network_on_miss,
        )

    def process_game_data(
        self,
        game_data,
        allow_cold_metric_fetch=True,
        allow_cold_appdetails_fetch=None,
        appdetails_timeout=1.5,
        require_appdetails=False,
        hide_hardware=False,
    ):
        if (
            allow_cold_appdetails_fetch is None
            and appdetails_timeout == 1.5
            and not require_appdetails
            and not hide_hardware
        ):
            return self.plugin.process_game_data(
                game_data,
                allow_cold_metric_fetch=allow_cold_metric_fetch,
            )
        return self.plugin.process_game_data(
            game_data,
            allow_cold_metric_fetch=allow_cold_metric_fetch,
            allow_cold_appdetails_fetch=allow_cold_appdetails_fetch,
            appdetails_timeout=appdetails_timeout,
            require_appdetails=require_appdetails,
            hide_hardware=hide_hardware,
        )

    def search_steam_api(self, search_term):
        return self.plugin.search_steam_api(search_term)

    def process_store_results(
        self,
        api_results,
        skipped_app_ids=None,
        allow_cold_metric_fetch=True,
        allow_cold_appdetails_fetch=None,
        cold_metric_fetch_limit=None,
        appdetails_timeout=1.5,
        require_appdetails=False,
        hide_hardware=False,
    ):
        if (
            allow_cold_appdetails_fetch is None
            and cold_metric_fetch_limit is None
            and appdetails_timeout == 1.5
            and not require_appdetails
            and not hide_hardware
        ):
            return self.plugin.process_store_results(
                api_results,
                skipped_app_ids=skipped_app_ids,
                allow_cold_metric_fetch=allow_cold_metric_fetch,
            )
        return self.plugin.process_store_results(
            api_results,
            skipped_app_ids=skipped_app_ids,
            allow_cold_metric_fetch=allow_cold_metric_fetch,
            allow_cold_appdetails_fetch=allow_cold_appdetails_fetch,
            cold_metric_fetch_limit=cold_metric_fetch_limit,
            appdetails_timeout=appdetails_timeout,
            require_appdetails=require_appdetails,
            hide_hardware=hide_hardware,
        )

    def store_collection_games(self, collection_name):
        return self.plugin.get_store_collection_games(collection_name)

    def store_collection_label(self, collection_name):
        return self.plugin.get_store_collection_label(collection_name)


@dataclass(frozen=True)
class ResultProvider:
    plugin: object

    def build_action(self, method, *parameters):
        return self.plugin.build_action(method, *parameters)

    def build_change_query_action(self, query, requery=True, keep_open=True):
        return self.plugin.build_change_query_action(query, requery=requery, keep_open=keep_open)

    def build_plugin_query(self, *parts):
        return self.plugin.build_plugin_query(*parts)

    def build_context_data(self, **kwargs):
        return self.plugin.build_context_data(**kwargs)

    def build_result(self, title, subtitle, icon_path=None, action=None, context_data=None, **extra_fields):
        return self.plugin.build_result(
            title=title,
            subtitle=subtitle,
            icon_path=icon_path,
            action=action,
            context_data=context_data,
            **extra_fields,
        )

    def add_result(self, result):
        return self.plugin.add_result(result)


@dataclass(frozen=True)
class SettingsProvider:
    plugin: object

    def country_code(self):
        return self.plugin.get_country_code()

    def blacklisted_app_ids(self):
        return self.plugin.get_blacklisted_app_ids()

    def should_show_prices(self):
        return self.plugin.should_show_prices()

    def should_show_positive_reviews(self):
        return self.plugin.should_show_positive_reviews()

    def should_show_achievements(self):
        return self.plugin.should_show_achievements()

    def should_offer_refund_shortcut(self):
        return self.plugin.should_offer_refund_shortcut()

    def should_detect_owned_games(self):
        return self.plugin.should_detect_owned_games()

    def should_show_steamdb_context_menu(self):
        return self.plugin.should_show_steamdb_context_menu()

    def should_show_csrin_context_menu(self):
        return self.plugin.should_show_csrin_context_menu()

    def should_show_last_played(self):
        return self.plugin.should_show_last_played()

    def should_hide_hidden_games(self):
        return self.plugin.should_hide_hidden_games()

    def should_show_platforms(self):
        return self.plugin.should_show_platforms()

    def should_show_playtime(self):
        return self.plugin.should_show_playtime()

    def should_show_player_count(self):
        return self.plugin.should_show_player_count()

    def should_sort_local_by_recent(self):
        return self.plugin.should_sort_local_by_recent()

    def platform_suffix(self, platforms):
        return self.plugin.get_platform_suffix(platforms)

    def language(self):
        get_language = getattr(self.plugin, "get_language", None)
        return get_language() if callable(get_language) else "en"

    def steam_language(self):
        get_steam_language = getattr(self.plugin, "get_steam_language", None)
        return get_steam_language() if callable(get_steam_language) else "english"

    def tr(self, key, default=None, **values):
        return plugin_tr(self.plugin, key, default=default, **values)


@dataclass(frozen=True)
class LocalProvider:
    plugin: object

    def install_path(self, app_id):
        return self.plugin.get_install_path(app_id)

    def installed_games_items(self):
        return self.plugin.get_installed_games_items()

    def installed_game_status(self, app_id):
        return self.plugin.get_installed_game_status(app_id)

    def live_game_status(self, app_id, fallback_status=""):
        get_live_status = getattr(self.plugin, "get_live_local_game_status", None)
        if callable(get_live_status):
            return str(get_live_status(app_id, fallback_status) or fallback_status or "")
        return str(fallback_status or "")

    def playtime_minutes(self, app_id):
        return self.plugin.get_playtime_minutes(app_id)

    def last_played_timestamp(self, app_id):
        return self.plugin.get_last_played_timestamp(app_id)

    def achievement_progress(self, app_id):
        return self.plugin.get_local_achievement_progress(app_id)

    def game_account_notice(self, app_id):
        return self.plugin.get_local_game_account_notice(app_id)

    def game_icon(self, app_id):
        return self.plugin.get_local_game_icon(app_id)

    def has_current_account_data(self, app_id):
        return self.plugin.has_current_account_local_data(app_id)

    def active_persona_state(self):
        return self.plugin.get_active_local_persona_state()

    def persona_state_label(self, persona_state):
        return self.plugin.get_local_persona_state_label(persona_state)

    def persona_state_protocol(self, persona_state):
        return self.plugin.get_local_persona_state_protocol(persona_state)


@dataclass(frozen=True)
class ProfileProvider:
    plugin: object

    def active_status(self):
        return self.plugin.get_active_profile_status()

    def active_avatar_icon(self):
        return self.plugin.get_active_steam_avatar_icon()

    def is_owned_app(self, app_id):
        return self.plugin.is_owned_app(app_id)

    def owned_game_playtime_minutes(self, app_id):
        return self.plugin.get_owned_game_playtime_minutes(app_id)


@dataclass(frozen=True)
class MetricsProvider:
    plugin: object

    def current_players(self, app_id):
        return self.plugin.get_current_players(app_id)

    def format_player_count(self, player_count):
        return self.plugin.format_player_count(player_count)


@dataclass(frozen=True)
class DownloadProvider:
    plugin: object

    def action_for_status(self, status_label):
        get_action = getattr(self.plugin, "get_download_control_action_for_status", None)
        if not callable(get_action):
            return ""
        return str(get_action(status_label) or "")


@dataclass(frozen=True)
class RuntimeProvider:
    plugin: object

    def ensure_startup_initialized(self):
        return self.plugin.ensure_startup_initialized()

    def refresh_user_scoped_local_state_if_needed(self):
        return self.plugin.refresh_user_scoped_local_state_if_needed()

    def update_installed_games(self):
        return self.plugin.update_installed_games()

    def cleanup_caches_if_needed(self):
        return self.plugin.cleanup_caches_if_needed()

    def start_metric_refresh(self, pending_set_name, key, refresh_method):
        return self.plugin.start_metric_refresh(pending_set_name, key, refresh_method)

    def finish_metric_refresh(self, pending_set_name, key):
        return self.plugin.finish_metric_refresh(pending_set_name, key)

    def save_metric_caches(self, force=False):
        return self.plugin.save_metric_caches(force=force)

    def mark_timing(self, timings, stage_name, start_time):
        return self.plugin.mark_timing(timings, stage_name, start_time)

    def log_query_profile(self, search_term, timings, total_ms, result_count):
        return self.plugin.log_query_profile(search_term, timings, total_ms, result_count)

    def log_exception(self, message):
        return self.plugin.log_exception(message)

    def log(self, level, message):
        return self.plugin.log(level, message)


@dataclass(frozen=True)
class OwnedApiProvider:
    plugin: object

    def status(self):
        return self.plugin.get_owned_games_status()

    def normalize_key(self, value):
        return self.plugin.normalize_steam_web_api_key(value)

    def fetch_owned_app_ids(self, api_key, steamid64, timeout=5):
        return self.plugin.fetch_owned_app_ids_from_api(api_key, steamid64, timeout=timeout)

    def save_key(self, api_key, steamid64, persona_name=None, account_name=None):
        return self.plugin.save_owned_api_key(
            api_key,
            steamid64,
            persona_name=persona_name,
            account_name=account_name,
        )

    def remove_key(self):
        return self.plugin.remove_owned_api_key()

    def save_owned_games_cache(self):
        return self.plugin.save_owned_games_cache()

    def clear_owned_games_cache(self):
        return self.plugin.clear_owned_games_cache()


@dataclass(frozen=True)
class QueryCommandProvider:
    plugin: object

    def is_help_query(self, search_term):
        return self.plugin.is_help_query(search_term)

    def build_help_results(self):
        return self.plugin.build_help_results()

    def is_wishlist_query(self, search_term):
        return self.plugin.is_wishlist_query(search_term)

    def get_wishlist_query_text(self, search_term):
        return self.plugin.get_wishlist_query_text(search_term)

    def build_wishlist_results(self, search_term=""):
        return self.plugin.build_wishlist_results(search_term)

    def is_switch_account_query(self, search_term):
        return self.plugin.is_switch_account_query(search_term)

    def build_switch_account_results(self):
        return self.plugin.build_switch_account_results()

    def is_status_query(self, search_term):
        return self.plugin.is_status_query(search_term)

    def build_status_results(self):
        return self.plugin.build_status_results()

    def is_owned_api_query(self, search_term):
        return self.plugin.is_owned_api_query(search_term)

    def build_owned_api_results(self):
        return self.plugin.build_owned_api_results()

    def get_store_collection_query(self, search_term):
        return self.plugin.get_store_collection_query(search_term)


@dataclass(frozen=True)
class WishlistProvider:
    plugin: object

    def load_cache(self):
        return self.plugin.load_wishlist_cache()

    def save_cache(self):
        return self.plugin.save_wishlist_cache()

    def clear_cache(self):
        return self.plugin.clear_wishlist_cache()

    def items(self):
        return self.plugin.get_wishlist_items()


@dataclass(frozen=True)
class SteamPluginProviders:
    plugin: object

    @cached_property
    def account(self):
        return AccountProvider(self.plugin)

    @cached_property
    def store(self):
        return StoreProvider(self.plugin)

    @cached_property
    def results(self):
        return ResultProvider(self.plugin)

    @cached_property
    def settings(self):
        return SettingsProvider(self.plugin)

    @cached_property
    def local(self):
        return LocalProvider(self.plugin)

    @cached_property
    def profile(self):
        return ProfileProvider(self.plugin)

    @cached_property
    def metrics(self):
        return MetricsProvider(self.plugin)

    @cached_property
    def download(self):
        return DownloadProvider(self.plugin)

    @cached_property
    def runtime(self):
        return RuntimeProvider(self.plugin)

    @cached_property
    def commands(self):
        return QueryCommandProvider(self.plugin)

    @cached_property
    def owned_api(self):
        return OwnedApiProvider(self.plugin)

    @cached_property
    def wishlist(self):
        return WishlistProvider(self.plugin)


def get_plugin_providers(plugin):
    providers = getattr(plugin, "providers", None)
    if providers is None:
        providers = SteamPluginProviders(plugin)
        setattr(plugin, "providers", providers)
    return providers
