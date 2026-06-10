import ctypes
import json
import locale
import sys
from functools import lru_cache
from pathlib import Path


DEFAULT_LOCALE = "en"
SUPPORTED_LOCALES = frozenset({"en", "de", "es-ES", "fr", "ja", "ko", "pl", "pt-BR", "ru", "zh-Hans", "zh-Hant"})
STEAM_LANGUAGE_BY_LOCALE = {
    "en": "english",
    "de": "german",
    "es-ES": "spanish",
    "fr": "french",
    "ja": "japanese",
    "ko": "koreana",
    "pl": "polish",
    "pt-BR": "brazilian",
    "ru": "russian",
    "zh-Hans": "schinese",
    "zh-Hant": "tchinese",
}

_LOCALES_DIR = Path(__file__).resolve().parent / "locales"
_ZH_HANS_REGIONS = {"cn", "sg"}
_ZH_HANT_REGIONS = {"tw", "hk", "mo"}


def normalize_locale(value):
    raw_value = str(value or "").strip().replace("_", "-")
    if not raw_value or raw_value.lower() == "auto":
        return DEFAULT_LOCALE

    display_locale_aliases = {
        "auto (system language)": DEFAULT_LOCALE,
        "system": DEFAULT_LOCALE,
        "english": "en",
        "german": "de",
        "deutsch": "de",
        "spanish": "es-ES",
        "spanish - spain": "es-ES",
        "spanish (spain)": "es-ES",
        "espanol": "es-ES",
        "french": "fr",
        "francais": "fr",
        "français": "fr",
        "japanese": "ja",
        "日本語": "ja",
        "korean": "ko",
        "한국어": "ko",
        "polish": "pl",
        "polski": "pl",
        "portuguese": "pt-BR",
        "portuguese - brazil": "pt-BR",
        "portuguese (brazil)": "pt-BR",
        "portugues": "pt-BR",
        "português": "pt-BR",
        "português - brasil": "pt-BR",
        "português (brasil)": "pt-BR",
        "español": "es-ES",
        "russian": "ru",
        "русский": "ru",
        "simplified chinese": "zh-Hans",
        "chinese simplified": "zh-Hans",
        "traditional chinese": "zh-Hant",
        "chinese traditional": "zh-Hant",
    }
    display_alias = display_locale_aliases.get(raw_value.lower())
    if display_alias:
        return display_alias

    parts = [part for part in raw_value.split("-") if part]
    language = parts[0].lower() if parts else ""
    qualifiers = {part.lower() for part in parts[1:]}

    if language == "zh":
        if "hans" in qualifiers or qualifiers & _ZH_HANS_REGIONS:
            return "zh-Hans"
        if "hant" in qualifiers or qualifiers & _ZH_HANT_REGIONS:
            return "zh-Hant"
        return "zh-Hans"
    if language == "en":
        return "en"
    if language == "de":
        return "de"
    if language == "es":
        return "es-ES"
    if language == "fr":
        return "fr"
    if language == "ja":
        return "ja"
    if language == "ko":
        return "ko"
    if language == "pl":
        return "pl"
    if language == "pt":
        return "pt-BR"
    if language == "ru":
        return "ru"
    return DEFAULT_LOCALE


def detect_windows_preferred_ui_locale():
    if sys.platform != "win32":
        return ""

    try:
        kernel32 = ctypes.windll.kernel32
        get_languages = kernel32.GetUserPreferredUILanguages
        get_languages.argtypes = [
            ctypes.c_ulong,
            ctypes.POINTER(ctypes.c_ulong),
            ctypes.c_wchar_p,
            ctypes.POINTER(ctypes.c_ulong),
        ]
        get_languages.restype = ctypes.c_int

        MUI_LANGUAGE_NAME = 0x8
        language_count = ctypes.c_ulong(0)
        buffer_length = ctypes.c_ulong(0)
        get_languages(MUI_LANGUAGE_NAME, ctypes.byref(language_count), None, ctypes.byref(buffer_length))
        if buffer_length.value <= 0:
            return ""

        buffer = ctypes.create_unicode_buffer(buffer_length.value)
        if not get_languages(MUI_LANGUAGE_NAME, ctypes.byref(language_count), buffer, ctypes.byref(buffer_length)):
            return ""
        return str(buffer.value or "").split("\0", 1)[0]
    except Exception:
        return ""


def detect_system_locale():
    windows_locale = detect_windows_preferred_ui_locale()
    if windows_locale:
        return normalize_locale(windows_locale)

    try:
        fallback_locale = locale.getlocale()[0] or locale.getdefaultlocale()[0]
    except Exception:
        fallback_locale = ""
    return normalize_locale(fallback_locale)


def resolve_configured_locale(configured_locale):
    configured_locale = str(configured_locale or "auto").strip()
    if configured_locale.lower() in {"auto", "auto (system language)", "system"}:
        return detect_system_locale()
    return normalize_locale(configured_locale)


@lru_cache(maxsize=8)
def load_locale_messages(locale_name):
    normalized = normalize_locale(locale_name)
    path = _LOCALES_DIR / f"{normalized}.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        data = {}
    return data if isinstance(data, dict) else {}


def _format_message(template, values):
    if not values:
        return template
    try:
        return template.format(**values)
    except Exception:
        return template


class Localizer:
    def __init__(self, locale_name=DEFAULT_LOCALE):
        self.locale = normalize_locale(locale_name)
        self.messages = load_locale_messages(self.locale)
        self.fallback_messages = load_locale_messages(DEFAULT_LOCALE)

    @property
    def steam_language(self):
        return STEAM_LANGUAGE_BY_LOCALE.get(self.locale, STEAM_LANGUAGE_BY_LOCALE[DEFAULT_LOCALE])

    def tr(self, key, default=None, **values):
        template = self.messages.get(key)
        if template is None:
            template = self.fallback_messages.get(key)
        if template is None:
            template = default if default is not None else key
        return _format_message(str(template), values)


def plugin_tr(plugin, key, default=None, **values):
    translator = getattr(plugin, "tr", None)
    if callable(translator):
        return translator(key, default=default, **values)
    return Localizer(DEFAULT_LOCALE).tr(key, default=default, **values)
