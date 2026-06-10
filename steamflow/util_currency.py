LEGACY_COUNTRY_CODE_ALIASES = {
    "uk": "gb",
}

LEGACY_INVALID_COUNTRY_CODES = {
    "eu",
}


def normalize_country_code(country_code, default="us"):
    normalized = str(country_code or "").strip().lower()
    normalized = LEGACY_COUNTRY_CODE_ALIASES.get(normalized, normalized)
    if normalized in LEGACY_INVALID_COUNTRY_CODES:
        return default
    if len(normalized) == 2 and normalized.isascii() and normalized.isalpha():
        return normalized
    return default


def format_price(price_info):
    if not isinstance(price_info, dict):
        return ""

    final_formatted = str(price_info.get("final_formatted", "") or "").strip()
    if final_formatted:
        return final_formatted

    try:
        final = int(price_info["final"])
    except (KeyError, TypeError, ValueError):
        return ""

    currency = str(price_info.get("currency", "") or "").strip().upper()
    amount = f"{final / 100:.2f}"
    return f"{amount} {currency}".strip()
