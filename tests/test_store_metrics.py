import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LIB_PATH = PROJECT_ROOT / "lib"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(LIB_PATH) not in sys.path:
    sys.path.insert(0, str(LIB_PATH))

from steamflow.store_metrics import SteamPluginStoreMetricsMixin


class StoreMetricsHarness(SteamPluginStoreMetricsMixin):
    def should_show_prices(self):
        return True

    def get_country_code(self):
        return "us"

    def is_owned_app(self, app_id):
        return False

    def should_show_positive_reviews(self):
        return False

    def should_show_player_count(self):
        return False

    def should_show_achievements(self):
        return False

    def has_owned_api_key(self):
        return False

    def get_owned_game_playtime_minutes(self, app_id):
        return None

    def get_platform_suffix(self, platforms):
        return ""

    def build_context_data(self, **kwargs):
        return kwargs

    def build_action(self, method, *parameters):
        return {"method": method, "parameters": list(parameters)}

    def build_result(self, title, subtitle, icon_path=None, action=None, context_data=None, **extra_fields):
        result = {"Title": title, "SubTitle": subtitle, "IcoPath": icon_path, "Action": action}
        result.update(extra_fields)
        return result

    def get_app_details_metadata(self, app_id, allow_network_on_miss=True):
        return self.app_details_by_id.get(str(app_id))

    def get_review_score(self, app_id, allow_network_on_miss=True):
        return None

    def get_current_players(self, app_id, allow_network_on_miss=True):
        return None

    def get_owned_store_achievement_progress(self, app_id, allow_network_on_miss=True):
        return None

    def _resolve_game_icon(self, app_id, image_url):
        return "icon"

    def __init__(self):
        self.app_details_by_id = {}


class StoreMetricsTests(unittest.TestCase):
    def test_only_true_free_games_render_free_badge(self):
        harness = StoreMetricsHarness()

        result = harness.format_store_price_or_availability(
            {
                "type": "app",
                "has_price": False,
                "price": None,
                "is_free": False,
            }
        )

        self.assertEqual(result, "")

    def test_coming_soon_games_render_honest_availability_label(self):
        harness = StoreMetricsHarness()

        result = harness.format_store_price_or_availability(
            {
                "type": "app",
                "has_price": False,
                "price": None,
                "is_free": False,
                "coming_soon": True,
            }
        )

        self.assertEqual(result, " | Coming Soon")

    def test_true_free_games_still_render_free_badge(self):
        harness = StoreMetricsHarness()

        result = harness.format_store_price_or_availability(
            {
                "type": "app",
                "has_price": False,
                "price": None,
                "is_free": True,
            }
        )

        self.assertEqual(result, " | Free")

    def test_process_game_data_appends_real_release_date_from_appdetails(self):
        harness = StoreMetricsHarness()
        harness.app_details_by_id["686060"] = {
            "type": "game",
            "is_free": False,
            "name": "Mewgenics",
            "capsule_image": "https://example.com/capsule.jpg",
            "platforms": {"windows": True},
            "has_price": True,
            "price": {"final": 60000},
            "coming_soon": False,
            "release_date_text": "10 Feb, 2026",
        }

        result = harness.process_game_data(
            {
                "type": "app",
                "id": "686060",
                "name": "Mewgenics",
                "platforms": {},
                "tiny_image": None,
                "has_price": True,
                "price": {"final": 60000},
                "is_free": False,
            },
            allow_cold_metric_fetch=False,
        )

        self.assertIn("| 10 Feb, 2026", result["SubTitle"])

    def test_process_game_data_hides_placeholder_release_date_when_coming_soon_is_already_shown(self):
        harness = StoreMetricsHarness()
        harness.app_details_by_id["2949750"] = {
            "type": "game",
            "is_free": False,
            "name": "Margin of the Strange",
            "capsule_image": "https://example.com/capsule.jpg",
            "platforms": {"windows": True},
            "has_price": False,
            "price": None,
            "coming_soon": True,
            "release_date_text": "To be announced",
        }

        result = harness.process_game_data(
            {
                "type": "app",
                "id": "2949750",
                "name": "Margin of the Strange",
                "platforms": {},
                "tiny_image": None,
                "has_price": False,
                "price": None,
                "is_free": False,
            },
            allow_cold_metric_fetch=False,
        )

        self.assertIn("Coming Soon", result["SubTitle"])
        self.assertNotIn("To be announced", result["SubTitle"])

    def test_process_game_data_hides_coming_soon_placeholder_release_date_duplicate(self):
        harness = StoreMetricsHarness()
        harness.app_details_by_id["2709910"] = {
            "type": "game",
            "is_free": False,
            "name": "Five Nights at Cobson's",
            "capsule_image": "https://example.com/capsule.jpg",
            "platforms": {"windows": True},
            "has_price": False,
            "price": None,
            "coming_soon": True,
            "release_date_text": "Coming soon",
        }

        result = harness.process_game_data(
            {
                "type": "app",
                "id": "2709910",
                "name": "Five Nights at Cobson's",
                "platforms": {},
                "tiny_image": None,
                "has_price": False,
                "price": None,
                "is_free": False,
            },
            allow_cold_metric_fetch=False,
        )

        self.assertIn("Coming Soon", result["SubTitle"])
        self.assertEqual(result["SubTitle"].count("Coming Soon"), 1)

    def test_process_game_data_uses_library_details_action_for_owned_games(self):
        harness = StoreMetricsHarness()
        harness.is_owned_app = lambda app_id: True
        harness.app_details_by_id["570"] = {
            "type": "game",
            "is_free": True,
            "name": "Dota 2",
            "capsule_image": "https://example.com/capsule.jpg",
            "platforms": {"windows": True},
            "has_price": False,
            "price": None,
            "coming_soon": False,
            "release_date_text": "",
        }

        result = harness.process_game_data(
            {
                "type": "app",
                "id": "570",
                "name": "Dota 2",
                "platforms": {},
                "tiny_image": None,
                "has_price": False,
                "price": None,
                "is_free": True,
            },
            allow_cold_metric_fetch=False,
        )

        self.assertIn("Owned game, open in Steam library", result["SubTitle"])
        self.assertEqual(result["Title"], "\U0001F3AE Dota 2 [Owned]")
        self.assertEqual(
            result["Action"],
            {"method": "open_steam_library_game_details", "parameters": ["570"]},
        )


if __name__ == "__main__":
    unittest.main()
