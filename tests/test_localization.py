import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LIB_PATH = PROJECT_ROOT / "lib"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(LIB_PATH) not in sys.path:
    sys.path.insert(0, str(LIB_PATH))

from steamflow.localization import (
    DEFAULT_LOCALE,
    SUPPORTED_LOCALES,
    Localizer,
    normalize_locale,
    resolve_configured_locale,
)


class LocalizationTests(unittest.TestCase):
    def test_only_english_is_supported(self):
        self.assertEqual(DEFAULT_LOCALE, "en")
        self.assertEqual(SUPPORTED_LOCALES, frozenset({"en"}))

    def test_normalize_locale_forces_english(self):
        for locale_name in ("", "auto", "English", "de", "ru-RU", "zh-Hant"):
            with self.subTest(locale_name=locale_name):
                self.assertEqual(normalize_locale(locale_name), "en")

    def test_configured_locale_is_ignored_while_localization_is_disabled(self):
        self.assertEqual(resolve_configured_locale("auto"), "en")
        self.assertEqual(resolve_configured_locale("Russian"), "en")

    def test_localizer_formats_english_values(self):
        self.assertEqual(
            Localizer("en").tr("ui.no_games_found", search_term="portal"),
            "No games found for 'portal'",
        )

    def test_localizer_uses_english_for_non_english_request(self):
        localizer = Localizer("ru")

        self.assertEqual(localizer.locale, "en")
        self.assertEqual(localizer.tr("ui.launch_steam"), "Launch Steam")
        self.assertEqual(localizer.steam_language, "english")


if __name__ == "__main__":
    unittest.main()
