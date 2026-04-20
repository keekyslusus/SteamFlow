import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LIB_PATH = PROJECT_ROOT / "lib"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(LIB_PATH) not in sys.path:
    sys.path.insert(0, str(LIB_PATH))

from datetime import datetime

from steamflow import util_steam_date


class UtilSteamDateTests(unittest.TestCase):
    def test_format_relative_minutes_ago_uses_minutes_below_one_hour(self):
        self.assertEqual(util_steam_date.format_relative_minutes_ago(5), "5m ago")

    def test_format_relative_minutes_ago_uses_hours_below_one_day(self):
        self.assertEqual(util_steam_date.format_relative_minutes_ago(61), "1h ago")
        self.assertEqual(util_steam_date.format_relative_minutes_ago(180), "3h ago")

    def test_format_relative_minutes_ago_uses_days_after_one_day(self):
        self.assertEqual(util_steam_date.format_relative_minutes_ago(24 * 60), "1d ago")
        self.assertEqual(util_steam_date.format_relative_minutes_ago(3 * 24 * 60), "3d ago")

    def test_format_wishlisted_date_uses_today_and_yesterday_for_recent_dates(self):
        now = datetime(2026, 4, 19, 12, 0, 0)

        self.assertEqual(util_steam_date.format_wishlisted_date(1776592800, now=now), "Today")
        self.assertEqual(util_steam_date.format_wishlisted_date(1776506400, now=now), "Yesterday")

    def test_format_wishlisted_date_uses_days_for_recent_history(self):
        now = datetime(2026, 4, 19, 12, 0, 0)

        self.assertEqual(util_steam_date.format_wishlisted_date(1776420000, now=now), "2d ago")

    def test_format_wishlisted_date_uses_readable_dates_for_older_items(self):
        now = datetime(2026, 4, 19, 12, 0, 0)

        self.assertEqual(util_steam_date.format_wishlisted_date(1775383200, now=now), "Apr 5")
        self.assertEqual(util_steam_date.format_wishlisted_date(1712664000, now=now), "Apr 9, 2024")


if __name__ == "__main__":
    unittest.main()
