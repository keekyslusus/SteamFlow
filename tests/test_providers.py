import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LIB_PATH = PROJECT_ROOT / "lib"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(LIB_PATH) not in sys.path:
    sys.path.insert(0, str(LIB_PATH))

from steamflow.providers import SteamPluginProviders, get_plugin_providers


class ProviderHarness:
    def __init__(self):
        self.calls = []

    def get_active_steam_user_steamid64(self):
        self.calls.append("active")
        return "steamid"

    def get_active_steam_user_id(self):
        self.calls.append("active-user-id")
        return "123"

    def get_steam_user_details(self, steamid64):
        self.calls.append(("user", steamid64))
        return {"persona_name": "Alice"}

    def get_owned_api_key(self):
        self.calls.append("key")
        return "apikey"

    def has_owned_api_key(self):
        self.calls.append("has-key")
        return True

    def is_owned_api_key_bound_to_active_user(self):
        self.calls.append("bound")
        return True

    def get_active_account_ownership_state(self, app_id):
        self.calls.append(("ownership", app_id))
        return "owned"

    def has_multiple_known_steam_accounts(self):
        self.calls.append("multiple-accounts")
        return True

    def get_app_details_metadata(self, app_id, allow_network_on_miss=True, fetch_timeout=1.5):
        self.calls.append(("metadata", app_id, allow_network_on_miss, fetch_timeout))
        return {"name": "Portal"}

    def process_game_data(
        self,
        game_data,
        allow_cold_metric_fetch=True,
        allow_cold_appdetails_fetch=None,
        appdetails_timeout=1.5,
        require_appdetails=False,
        hide_hardware=False,
    ):
        self.calls.append(
            (
                "process",
                game_data,
                allow_cold_metric_fetch,
                allow_cold_appdetails_fetch,
                appdetails_timeout,
                require_appdetails,
                hide_hardware,
            )
        )
        return {"Title": game_data["name"]}

    def search_steam_api(self, search_term):
        self.calls.append(("search", search_term))
        return {"games": [], "error": None}

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
        self.calls.append(
            (
                "store-results",
                api_results,
                skipped_app_ids,
                allow_cold_metric_fetch,
                allow_cold_appdetails_fetch,
                cold_metric_fetch_limit,
                appdetails_timeout,
                require_appdetails,
                hide_hardware,
            )
        )
        return []

    def get_store_collection_games(self, collection_name):
        self.calls.append(("store-collection", collection_name))
        return {"games": [], "error": None}

    def get_store_collection_label(self, collection_name):
        return "Top Sellers"

    def get_refund_state_for_local_game(self, app_id, allow_network_on_miss=False):
        self.calls.append(("refund", app_id, allow_network_on_miss))
        return "likely"

    def get_country_code(self):
        self.calls.append("country")
        return "us"

    def get_blacklisted_app_ids(self):
        return {"228980"}

    def should_show_achievements(self):
        return True

    def should_offer_refund_shortcut(self):
        return True

    def should_detect_owned_games(self):
        return True

    def should_show_prices(self):
        return True

    def should_show_positive_reviews(self):
        return True

    def should_show_last_played(self):
        return True

    def should_hide_hidden_games(self):
        return True

    def should_show_platforms(self):
        return True

    def should_show_playtime(self):
        return True

    def should_show_player_count(self):
        return True

    def get_steam_language(self):
        return "english"

    def should_sort_local_by_recent(self):
        return True

    def get_platform_suffix(self, platforms):
        return " (Win)" if platforms.get("windows") else ""

    def is_owned_app(self, app_id):
        return str(app_id) == "570"

    def get_owned_game_playtime_minutes(self, app_id):
        return 100

    def get_installed_games_items(self):
        return [("570", "Dota 2")]

    def get_install_path(self, app_id):
        return f"C:/Steam/{app_id}"

    def get_installed_game_status(self, app_id):
        return "Installed"

    def get_live_local_game_status(self, app_id, fallback_status=""):
        return f"Live {fallback_status}"

    def get_playtime_minutes(self, app_id):
        return 120

    def get_last_played_timestamp(self, app_id):
        return 123

    def get_local_achievement_progress(self, app_id):
        return (1, 2)

    def get_local_game_account_notice(self, app_id):
        return " | Current account"

    def get_local_game_icon(self, app_id):
        return "icon"

    def has_current_account_local_data(self, app_id):
        return True

    def get_active_profile_status(self):
        return "Online"

    def get_active_steam_avatar_icon(self):
        return "avatar"

    def get_current_players(self, app_id):
        return 42

    def format_player_count(self, player_count):
        return f" | players={player_count}"

    def get_download_control_action_for_status(self, status_label):
        return "pause" if status_label == "Updating" else ""

    def ensure_startup_initialized(self):
        self.calls.append("startup")

    def refresh_user_scoped_local_state_if_needed(self):
        self.calls.append("refresh-local")

    def update_installed_games(self):
        self.calls.append("update-games")

    def cleanup_caches_if_needed(self):
        self.calls.append("cleanup")

    def start_metric_refresh(self, pending_set_name, key, refresh_method):
        self.calls.append(("start-metric", pending_set_name, key, refresh_method))

    def finish_metric_refresh(self, pending_set_name, key):
        self.calls.append(("finish-metric", pending_set_name, key))

    def save_metric_caches(self, force=False):
        self.calls.append(("save-metrics", force))

    def mark_timing(self, timings, stage_name, start_time):
        timings.append((stage_name, 1))

    def log_query_profile(self, search_term, timings, total_ms, result_count):
        self.calls.append(("query-profile", search_term, result_count))

    def log_exception(self, message):
        self.calls.append(("exception", message))

    def is_help_query(self, search_term):
        return search_term == "?"

    def build_help_results(self):
        return [{"Title": "Help"}]

    def is_wishlist_query(self, search_term):
        return search_term == "wishlist"

    def get_wishlist_query_text(self, search_term):
        return ""

    def build_wishlist_results(self, search_term=""):
        return [{"Title": "Wishlist"}]

    def is_switch_account_query(self, search_term):
        return False

    def build_switch_account_results(self):
        return []

    def is_status_query(self, search_term):
        return False

    def build_status_results(self):
        return []

    def is_owned_api_query(self, search_term):
        return False

    def build_owned_api_results(self):
        return []

    def get_store_collection_query(self, search_term):
        return "specials" if search_term == "deals" else None

    def normalize_steam_web_api_key(self, value):
        return str(value or "").strip().upper()

    def save_owned_games_cache(self):
        self.calls.append("save-owned")

    def clear_owned_games_cache(self):
        self.calls.append("clear-owned")

    def load_wishlist_cache(self):
        self.calls.append("load-wishlist")

    def save_wishlist_cache(self):
        self.calls.append("save-wishlist")

    def clear_wishlist_cache(self):
        self.calls.append("clear-wishlist")

    def get_wishlist_items(self):
        return [{"appid": "570"}], None

    def build_action(self, method, *parameters):
        return {"method": method, "parameters": list(parameters)}

    def build_plugin_query(self, *parts):
        return "steam " + " ".join(parts)

    def build_context_data(self, **kwargs):
        return dict(kwargs)

    def build_result(self, title, subtitle, icon_path=None, action=None, context_data=None, **extra_fields):
        result = {"Title": title, "SubTitle": subtitle, "IcoPath": icon_path, "Action": action}
        result.update(extra_fields)
        return result

    def add_result(self, result):
        self.calls.append(("add", result))


class ProviderTests(unittest.TestCase):
    def test_get_plugin_providers_lazily_attaches_provider_registry(self):
        harness = ProviderHarness()

        providers = get_plugin_providers(harness)

        self.assertIsInstance(providers, SteamPluginProviders)
        self.assertIs(get_plugin_providers(harness), providers)

    def test_account_store_settings_and_result_providers_delegate_to_plugin(self):
        harness = ProviderHarness()
        providers = SteamPluginProviders(harness)

        self.assertEqual(providers.account.active_steamid64(), "steamid")
        self.assertEqual(providers.account.active_user_id(), "123")
        self.assertEqual(providers.account.owned_api_key(), "apikey")
        self.assertTrue(providers.account.has_owned_api_key())
        self.assertTrue(providers.account.api_key_bound_to_active_user())
        self.assertEqual(providers.account.user_details("steamid"), {"persona_name": "Alice"})
        self.assertEqual(providers.account.active_account_ownership_state("570"), "owned")
        self.assertTrue(providers.account.has_multiple_known_accounts())
        self.assertEqual(
            providers.store.app_details_metadata("570", allow_network_on_miss=False, fetch_timeout=2.0),
            {"name": "Portal"},
        )
        self.assertEqual(
            providers.store.process_game_data(
                {"name": "Portal"},
                allow_cold_metric_fetch=False,
                allow_cold_appdetails_fetch=True,
                appdetails_timeout=2.0,
                require_appdetails=True,
            ),
            {"Title": "Portal"},
        )
        self.assertEqual(providers.store.search_steam_api("portal"), {"games": [], "error": None})
        self.assertEqual(providers.store.process_store_results([], skipped_app_ids={"570"}), [])
        self.assertEqual(
            providers.store.process_store_results([], allow_cold_metric_fetch=False),
            [],
        )
        self.assertEqual(
            providers.store.process_store_results(
                [],
                allow_cold_metric_fetch=True,
                allow_cold_appdetails_fetch=True,
                cold_metric_fetch_limit=3,
                appdetails_timeout=2.0,
                require_appdetails=True,
            ),
            [],
        )
        self.assertEqual(providers.store.store_collection_games("top_sellers"), {"games": [], "error": None})
        self.assertEqual(providers.store.store_collection_label("top_sellers"), "Top Sellers")
        self.assertEqual(providers.store.refund_state_for_local_game("570"), "likely")
        self.assertEqual(providers.settings.country_code(), "us")
        self.assertEqual(providers.settings.blacklisted_app_ids(), {"228980"})
        self.assertTrue(providers.settings.should_offer_refund_shortcut())
        self.assertTrue(providers.settings.should_detect_owned_games())
        self.assertTrue(providers.settings.should_show_prices())
        self.assertTrue(providers.settings.should_show_positive_reviews())
        self.assertTrue(providers.settings.should_hide_hidden_games())
        self.assertTrue(providers.settings.should_show_player_count())
        self.assertEqual(providers.settings.steam_language(), "english")
        self.assertTrue(providers.settings.should_sort_local_by_recent())
        self.assertEqual(providers.settings.platform_suffix({"windows": True}), " (Win)")
        self.assertEqual(providers.local.installed_games_items(), [("570", "Dota 2")])
        self.assertEqual(providers.local.live_game_status("570", "Installed"), "Live Installed")
        self.assertEqual(providers.profile.active_status(), "Online")
        self.assertEqual(providers.profile.active_avatar_icon(), "avatar")
        self.assertTrue(providers.profile.is_owned_app("570"))
        self.assertEqual(providers.profile.owned_game_playtime_minutes("570"), 100)
        self.assertEqual(providers.metrics.current_players("570"), 42)
        self.assertEqual(providers.metrics.format_player_count(42), " | players=42")
        self.assertEqual(providers.download.action_for_status("Updating"), "pause")
        self.assertEqual(providers.results.build_action("open", "570"), {"method": "open", "parameters": ["570"]})
        self.assertEqual(providers.results.build_plugin_query("api"), "steam api")
        self.assertEqual(providers.results.build_context_data(app_id="570"), {"app_id": "570"})
        self.assertEqual(providers.results.build_result("Title", "Subtitle")["Title"], "Title")
        providers.results.add_result({"Title": "Result"})
        providers.runtime.ensure_startup_initialized()
        providers.runtime.start_metric_refresh("pending", "570", "refresh")
        providers.runtime.finish_metric_refresh("pending", "570")
        self.assertTrue(providers.commands.is_help_query("?"))
        self.assertEqual(providers.commands.build_help_results(), [{"Title": "Help"}])
        self.assertEqual(providers.commands.get_store_collection_query("deals"), "specials")
        self.assertEqual(providers.owned_api.normalize_key(" abcd "), "ABCD")
        providers.owned_api.save_owned_games_cache()
        providers.owned_api.clear_owned_games_cache()
        providers.wishlist.load_cache()
        providers.wishlist.save_cache()
        providers.wishlist.clear_cache()
        self.assertEqual(providers.wishlist.items(), ([{"appid": "570"}], None))
        self.assertIn(("start-metric", "pending", "570", "refresh"), harness.calls)
        self.assertIn(("finish-metric", "pending", "570"), harness.calls)
        self.assertIn("save-owned", harness.calls)
        self.assertIn("clear-owned", harness.calls)
        self.assertIn("load-wishlist", harness.calls)
        self.assertIn("save-wishlist", harness.calls)
        self.assertIn("clear-wishlist", harness.calls)


if __name__ == "__main__":
    unittest.main()
