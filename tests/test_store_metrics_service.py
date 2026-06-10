import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LIB_PATH = PROJECT_ROOT / "lib"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(LIB_PATH) not in sys.path:
    sys.path.insert(0, str(LIB_PATH))

from steamflow.store_metrics_service import (
    build_review_score_url,
    build_store_result_subtitle,
    build_store_result_title,
    fetch_current_players_with_http_get,
    fetch_player_achievement_progress_with_http_get,
    format_discount_percent,
    format_player_count,
    format_review_score,
    format_store_price_or_availability,
    normalize_store_game_data,
    should_show_release_date_text,
    supports_live_metrics,
)


class StoreMetricsServiceTests(unittest.TestCase):
    def test_review_score_url_localizes_summary_description(self):
        self.assertEqual(
            build_review_score_url("570", steam_language="brazilian"),
            "https://store.steampowered.com/appreviews/570?json=1&language=all&purchase_type=all&num_per_page=0&l=brazilian",
        )

    def test_normalize_store_game_data_merges_appdetails_without_losing_fallbacks(self):
        normalized = normalize_store_game_data(
            {
                "id": "570",
                "name": "Old Name",
                "type": "app",
                "platforms": {"windows": True},
                "price": {"final": 10},
                "is_free": False,
            },
            {
                "type": "game",
                "name": "Dota 2",
                "capsule_image": "capsule.jpg",
                "has_price": False,
                "price": None,
                "coming_soon": False,
                "release_date_text": "",
            },
        )

        self.assertEqual(normalized["name"], "Dota 2")
        self.assertEqual(normalized["store_type"], "game")
        self.assertEqual(normalized["tiny_image"], "capsule.jpg")
        self.assertEqual(normalized["price"], {"final": 10})
        self.assertFalse(normalized["is_free"])

    def test_formatters_keep_store_subtitle_parts_consistent(self):
        self.assertEqual(format_discount_percent({"initial": 2000, "final": 1000}), " -50%")
        self.assertEqual(format_player_count("1234"), " | \U0001F465 1,234")
        self.assertEqual(
            format_review_score({"total_positive": 80, "total_reviews": 100, "review_score_desc": "Very Positive"}),
            " | 80% (Very Positive)",
        )
        self.assertFalse(should_show_release_date_text({"release_date_text": "To be announced"}))
        self.assertTrue(should_show_release_date_text({"release_date_text": "10 Feb, 2026"}))

    def test_release_date_placeholder_uses_localized_coming_soon_label(self):
        self.assertFalse(
            should_show_release_date_text(
                {
                    "coming_soon": True,
                    "release_date_text": "Скоро Выйдет",
                },
                labels={"coming_soon": "Скоро выйдет"},
            )
        )

        self.assertTrue(
            should_show_release_date_text(
                {
                    "coming_soon": False,
                    "release_date_text": "Скоро выйдет",
                },
                labels={"coming_soon": "Скоро выйдет"},
            )
        )

    def test_store_price_uses_formatted_value_returned_by_steam(self):
        price_text = format_store_price_or_availability(
            {
                "price": {
                    "final": 599,
                    "currency": "USD",
                    "final_formatted": "$5.99",
                },
            },
            country_code="uz",
        )

        self.assertEqual(price_text, " | $5.99")

    def test_supports_live_metrics_filters_non_games_and_excluded_names(self):
        excluded = ("soundtrack", "demo")

        self.assertTrue(supports_live_metrics({"type": "app", "store_type": "game", "name": "Portal"}, excluded))
        self.assertFalse(supports_live_metrics({"type": "app", "store_type": "dlc", "name": "Portal DLC"}, excluded))
        self.assertFalse(supports_live_metrics({"type": "app", "store_type": "game", "name": "Portal Soundtrack"}, excluded))

    def test_result_title_and_subtitle_are_built_from_metric_parts(self):
        self.assertEqual(build_store_result_title("Portal", is_owned=True), "\U0001F3AE Portal [Owned]")
        self.assertEqual(
            build_store_result_subtitle(
                {"platforms": {"windows": True}},
                is_owned=False,
                platform_suffix=" (Win)",
                review_score_text=" | 95%",
                player_count_text=" | \U0001F465 1,000",
                price_text=" | Free",
            ),
            "Open in Steam store (Win) | 95% | \U0001F465 1,000 | Free",
        )

    def test_result_subtitle_hides_localized_coming_soon_release_date_duplicate(self):
        from steamflow.store_metrics_service import build_store_game_result_spec

        result = build_store_game_result_spec(
            {
                "id": "2709910",
                "name": "Five Nights at Cobson's",
                "coming_soon": True,
                "release_date_text": "Скоро выйдет",
                "is_free": False,
                "price": None,
                "result_source": "wishlist",
            },
            is_owned=False,
            icon_path="icon",
            labels={
                "coming_soon": "Скоро выйдет",
                "store_subtitle": "Открыть в магазине Steam",
            },
        )

        self.assertEqual(result["subtitle"].count("Скоро выйдет"), 1)
        self.assertIn("Открыть в магазине Steam | Скоро выйдет", result["subtitle"])

    def test_fetch_helpers_parse_steam_payloads(self):
        calls = []

        def http_get(url, **kwargs):
            calls.append((url, kwargs))
            if "GetNumberOfCurrentPlayers" in url:
                return SimpleNamespace(data=json.dumps({"response": {"result": 1, "player_count": 42}}).encode("utf-8"))
            return SimpleNamespace(
                data=json.dumps({"playerstats": {"achievements": [{"achieved": 1}, {"achieved": 0}]}}).encode("utf-8")
            )

        self.assertEqual(fetch_current_players_with_http_get(http_get, "570"), 42)
        self.assertEqual(fetch_player_achievement_progress_with_http_get(http_get, "KEY", "steamid", "570"), 1)
        self.assertIn("appid=570", calls[0][0])
        self.assertEqual(calls[0][1]["headers"]["User-Agent"], "Mozilla/5.0")


if __name__ == "__main__":
    unittest.main()
