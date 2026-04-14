CURRENCY_DATA = {
    "ae": {"symbol": "AED", "is_prefixed": True, "decimal_digits": 2, "decimal_separator": ".", "thousands_separator": ","},
    "ar": {"symbol": "$", "is_prefixed": True, "decimal_digits": 2, "decimal_separator": ".", "thousands_separator": ","},
    "au": {"symbol": "$", "is_prefixed": True, "decimal_digits": 2, "decimal_separator": ".", "thousands_separator": ","},
    "az": {"symbol": "$", "is_prefixed": True, "decimal_digits": 2, "decimal_separator": ".", "thousands_separator": ","},
    "br": {"symbol": "R$", "is_prefixed": True, "decimal_digits": 2, "decimal_separator": ",", "thousands_separator": "."},
    "ca": {"symbol": "$", "is_prefixed": True, "decimal_digits": 2, "decimal_separator": ".", "thousands_separator": ","},
    "ch": {"symbol": "CHF", "is_prefixed": True, "decimal_digits": 2, "decimal_separator": ".", "thousands_separator": "'"},
    "cl": {"symbol": "$", "is_prefixed": True, "decimal_digits": 0, "decimal_separator": ",", "thousands_separator": "."},
    "cn": {"symbol": "¥", "is_prefixed": True, "decimal_digits": 2, "decimal_separator": ".", "thousands_separator": ","},
    "co": {"symbol": "$", "is_prefixed": True, "decimal_digits": 0, "decimal_separator": ",", "thousands_separator": "."},
    "cr": {"symbol": "₡", "is_prefixed": True, "decimal_digits": 2, "decimal_separator": ",", "thousands_separator": "."},
    "eu": {"symbol": "€", "is_prefixed": False, "decimal_digits": 2, "decimal_separator": ",", "thousands_separator": "."},
    "hk": {"symbol": "HK$", "is_prefixed": True, "decimal_digits": 2, "decimal_separator": ".", "thousands_separator": ","},
    "id": {"symbol": "Rp", "is_prefixed": True, "decimal_digits": 0, "decimal_separator": ",", "thousands_separator": "."},
    "il": {"symbol": "₪", "is_prefixed": True, "decimal_digits": 2, "decimal_separator": ".", "thousands_separator": ","},
    "in": {"symbol": "₹", "is_prefixed": True, "decimal_digits": 2, "decimal_separator": ".", "thousands_separator": ","},
    "jp": {"symbol": "¥", "is_prefixed": True, "decimal_digits": 0, "decimal_separator": ".", "thousands_separator": ","},
    "kr": {"symbol": "₩", "is_prefixed": True, "decimal_digits": 0, "decimal_separator": ".", "thousands_separator": ","},
    "kw": {"symbol": "KD", "is_prefixed": True, "decimal_digits": 3, "decimal_separator": ".", "thousands_separator": ","},
    "kz": {"symbol": "₸", "is_prefixed": False, "decimal_digits": 2, "decimal_separator": ",", "thousands_separator": " "},
    "mx": {"symbol": "$", "is_prefixed": True, "decimal_digits": 2, "decimal_separator": ".", "thousands_separator": ","},
    "my": {"symbol": "RM", "is_prefixed": True, "decimal_digits": 2, "decimal_separator": ".", "thousands_separator": ","},
    "no": {"symbol": "kr", "is_prefixed": False, "decimal_digits": 2, "decimal_separator": ",", "thousands_separator": " "},
    "nz": {"symbol": "$", "is_prefixed": True, "decimal_digits": 2, "decimal_separator": ".", "thousands_separator": ","},
    "pe": {"symbol": "S/.", "is_prefixed": True, "decimal_digits": 2, "decimal_separator": ",", "thousands_separator": "."},
    "ph": {"symbol": "₱", "is_prefixed": True, "decimal_digits": 2, "decimal_separator": ".", "thousands_separator": ","},
    "pk": {"symbol": "$", "is_prefixed": True, "decimal_digits": 2, "decimal_separator": ".", "thousands_separator": ","},
    "pl": {"symbol": "zł", "is_prefixed": False, "decimal_digits": 2, "decimal_separator": ",", "thousands_separator": " "},
    "qa": {"symbol": "QR", "is_prefixed": True, "decimal_digits": 2, "decimal_separator": ".", "thousands_separator": ","},
    "ru": {"symbol": "₽", "is_prefixed": False, "decimal_digits": 2, "decimal_separator": ",", "thousands_separator": " "},
    "sa": {"symbol": "SR", "is_prefixed": True, "decimal_digits": 2, "decimal_separator": ".", "thousands_separator": ","},
    "sg": {"symbol": "$", "is_prefixed": True, "decimal_digits": 2, "decimal_separator": ".", "thousands_separator": ","},
    "th": {"symbol": "฿", "is_prefixed": True, "decimal_digits": 2, "decimal_separator": ".", "thousands_separator": ","},
    "tr": {"symbol": "₺", "is_prefixed": False, "decimal_digits": 2, "decimal_separator": ",", "thousands_separator": "."},
    "tw": {"symbol": "NT$", "is_prefixed": True, "decimal_digits": 2, "decimal_separator": ".", "thousands_separator": ","},
    "ua": {"symbol": "₴", "is_prefixed": False, "decimal_digits": 2, "decimal_separator": ",", "thousands_separator": " "},
    "uk": {"symbol": "£", "is_prefixed": True, "decimal_digits": 2, "decimal_separator": ".", "thousands_separator": ","},
    "us": {"symbol": "$", "is_prefixed": True, "decimal_digits": 2, "decimal_separator": ".", "thousands_separator": ","},
    "uy": {"symbol": "$U", "is_prefixed": True, "decimal_digits": 2, "decimal_separator": ",", "thousands_separator": "."},
    "vn": {"symbol": "₫", "is_prefixed": False, "decimal_digits": 0, "decimal_separator": ".", "thousands_separator": "."},
    "za": {"symbol": "R", "is_prefixed": True, "decimal_digits": 2, "decimal_separator": ".", "thousands_separator": ","},
}

COUNTRY_CODE_ALIASES = {
    "at": "eu",
    "be": "eu",
    "cy": "eu",
    "de": "eu",
    "ee": "eu",
    "es": "eu",
    "fi": "eu",
    "fr": "eu",
    "gb": "uk",
    "gr": "eu",
    "hr": "eu",
    "ie": "eu",
    "it": "eu",
    "lt": "eu",
    "lu": "eu",
    "lv": "eu",
    "mt": "eu",
    "nl": "eu",
    "pt": "eu",
    "si": "eu",
    "sk": "eu",
}


def normalize_country_code(country_code, default="us"):
    if not country_code:
        return default

    normalized = str(country_code).strip().lower()
    normalized = COUNTRY_CODE_ALIASES.get(normalized, normalized)
    if normalized in CURRENCY_DATA:
        return normalized
    return default


def get_currency_info(country_code="us"):
    return CURRENCY_DATA[normalize_country_code(country_code)]


def format_price(price_int, country_code="us"):
    if price_int is None:
        return ""

    price_int = int(price_int)
    if price_int == 0:
        return "Free"

    info = get_currency_info(country_code)
    symbol = info["symbol"]
    is_prefixed = info["is_prefixed"]
    decimal_digits = info["decimal_digits"]
    decimal_separator = info["decimal_separator"]
    thousands_separator = info["thousands_separator"]

    is_negative = price_int < 0
    absolute_value = abs(price_int)
    divisor = 10 ** decimal_digits

    if decimal_digits > 0:
        whole_part, fractional_part = divmod(absolute_value, divisor)
        whole_str = f"{whole_part:,}".replace(",", thousands_separator)
        fractional_str = f"{fractional_part:0{decimal_digits}d}"
        number = f"{whole_str}{decimal_separator}{fractional_str}"
    else:
        number = f"{absolute_value:,}".replace(",", thousands_separator)

    if is_negative:
        number = f"-{number}"

    if is_prefixed:
        return f"{symbol}{number}"
    return f"{number} {symbol}"
