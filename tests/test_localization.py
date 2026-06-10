import sys
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LIB_PATH = PROJECT_ROOT / "lib"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(LIB_PATH) not in sys.path:
    sys.path.insert(0, str(LIB_PATH))

from steamflow.localization import Localizer, normalize_locale, resolve_configured_locale


class LocalizationTests(unittest.TestCase):
    def test_normalize_locale_maps_chinese_regions_to_script_locales(self):
        self.assertEqual(normalize_locale("zh-CN"), "zh-Hans")
        self.assertEqual(normalize_locale("zh-SG"), "zh-Hans")
        self.assertEqual(normalize_locale("zh-TW"), "zh-Hant")
        self.assertEqual(normalize_locale("zh-HK"), "zh-Hant")

    def test_normalize_locale_falls_back_to_english(self):
        self.assertEqual(normalize_locale("it-IT"), "en")
        self.assertEqual(normalize_locale(""), "en")

    def test_normalize_locale_accepts_settings_display_values(self):
        self.assertEqual(normalize_locale("English"), "en")
        self.assertEqual(normalize_locale("German"), "de")
        self.assertEqual(normalize_locale("Deutsch"), "de")
        self.assertEqual(normalize_locale("Spanish - Spain"), "es-ES")
        self.assertEqual(normalize_locale("French"), "fr")
        self.assertEqual(normalize_locale("Polish"), "pl")
        self.assertEqual(normalize_locale("Polski"), "pl")
        self.assertEqual(normalize_locale("Portuguese - Brazil"), "pt-BR")
        self.assertEqual(normalize_locale("Russian"), "ru")
        self.assertEqual(normalize_locale("Simplified Chinese"), "zh-Hans")
        self.assertEqual(normalize_locale("Traditional Chinese"), "zh-Hant")

    def test_normalize_locale_accepts_spanish_locale_values(self):
        self.assertEqual(normalize_locale("es"), "es-ES")
        self.assertEqual(normalize_locale("es-ES"), "es-ES")
        self.assertEqual(normalize_locale("Español"), "es-ES")

    def test_normalize_locale_accepts_german_locale_values(self):
        self.assertEqual(normalize_locale("de"), "de")
        self.assertEqual(normalize_locale("de-DE"), "de")

    def test_normalize_locale_accepts_french_locale_values(self):
        self.assertEqual(normalize_locale("fr"), "fr")
        self.assertEqual(normalize_locale("fr-FR"), "fr")
        self.assertEqual(normalize_locale("Français"), "fr")

    def test_normalize_locale_accepts_polish_locale_values(self):
        self.assertEqual(normalize_locale("pl"), "pl")
        self.assertEqual(normalize_locale("pl-PL"), "pl")
        self.assertEqual(normalize_locale("Polish"), "pl")

    def test_normalize_locale_accepts_portuguese_brazil_locale_values(self):
        self.assertEqual(normalize_locale("pt"), "pt-BR")
        self.assertEqual(normalize_locale("pt-BR"), "pt-BR")
        self.assertEqual(normalize_locale("Portuguese (Brazil)"), "pt-BR")

    def test_normalize_locale_accepts_russian_locale_values(self):
        self.assertEqual(normalize_locale("ru"), "ru")
        self.assertEqual(normalize_locale("ru-RU"), "ru")
        self.assertEqual(normalize_locale("Русский"), "ru")

    def test_localizer_uses_locale_then_english_fallback(self):
        localizer = Localizer("zh-Hans")

        self.assertEqual(localizer.tr("ui.launch_steam"), "启动 Steam")
        self.assertEqual(localizer.tr("action.game_launched"), "\u6e38\u620f\u5df2\u542f\u52a8")

    def test_localizer_formats_values(self):
        self.assertEqual(
            Localizer("en").tr("ui.no_games_found", search_term="portal"),
            "No games found for 'portal'",
        )

    def test_localizer_uses_russian_locale(self):
        self.assertEqual(Localizer("ru").tr("ui.launch_steam"), "Запустить Steam")
        self.assertEqual(Localizer("ru").steam_language, "russian")

    def test_localizer_uses_german_locale(self):
        self.assertEqual(Localizer("de").tr("ui.launch_steam"), "Steam starten")
        self.assertEqual(Localizer("de").steam_language, "german")

    def test_localizer_uses_spanish_spain_locale(self):
        self.assertEqual(Localizer("es-ES").tr("ui.launch_steam"), "Iniciar Steam")
        self.assertEqual(Localizer("es-ES").steam_language, "spanish")

    def test_localizer_uses_french_locale(self):
        self.assertEqual(Localizer("fr").tr("ui.launch_steam"), "Lancer Steam")
        self.assertEqual(Localizer("fr").steam_language, "french")

    def test_localizer_uses_polish_locale(self):
        self.assertEqual(Localizer("pl").tr("ui.launch_steam"), "Uruchom Steam")
        self.assertEqual(Localizer("pl").steam_language, "polish")

    def test_localizer_uses_portuguese_brazil_locale(self):
        self.assertEqual(Localizer("pt-BR").tr("ui.launch_steam"), "Iniciar Steam")
        self.assertEqual(Localizer("pt-BR").steam_language, "brazilian")

    def test_auto_locale_uses_detected_system_locale(self):
        with patch("steamflow.localization.detect_system_locale", return_value="zh-Hant"):
            self.assertEqual(resolve_configured_locale("auto"), "zh-Hant")
            self.assertEqual(resolve_configured_locale("Auto (system language)"), "zh-Hant")


if __name__ == "__main__":
    unittest.main()
