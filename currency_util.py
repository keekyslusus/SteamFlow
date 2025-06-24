CURRENCY_DATA = {
    'au': {'symbol': '$', 'is_prefixed': True, 'decimal_digits': 2, 'decimal_separator': '.', 'thousands_separator': ','},
    'br': {'symbol': 'R$', 'is_prefixed': True, 'decimal_digits': 2, 'decimal_separator': ',', 'thousands_separator': '.'},
    'uk': {'symbol': '£', 'is_prefixed': True, 'decimal_digits': 2, 'decimal_separator': '.', 'thousands_separator': ','},
    'ca': {'symbol': '$', 'is_prefixed': True, 'decimal_digits': 2, 'decimal_separator': '.', 'thousands_separator': ','},
    'cl': {'symbol': '$', 'is_prefixed': True, 'decimal_digits': 0, 'decimal_separator': ',', 'thousands_separator': '.'},
    'cn': {'symbol': '¥', 'is_prefixed': True, 'decimal_digits': 2, 'decimal_separator': '.', 'thousands_separator': ','},
    'az': {'symbol': '$', 'is_prefixed': True, 'decimal_digits': 2, 'decimal_separator': '.', 'thousands_separator': ','},
    'co': {'symbol': '$', 'is_prefixed': True, 'decimal_digits': 0, 'decimal_separator': ',', 'thousands_separator': '.'},
    'cr': {'symbol': '₡', 'is_prefixed': True, 'decimal_digits': 2, 'decimal_separator': ',', 'thousands_separator': '.'},
    'eu': {'symbol': '€', 'is_prefixed': False, 'decimal_digits': 2, 'decimal_separator': ',', 'thousands_separator': '.'},
    'hk': {'symbol': 'HK$', 'is_prefixed': True, 'decimal_digits': 2, 'decimal_separator': '.', 'thousands_separator': ','},
    'in': {'symbol': '₹', 'is_prefixed': True, 'decimal_digits': 2, 'decimal_separator': '.', 'thousands_separator': ','},
    'id': {'symbol': 'Rp', 'is_prefixed': True, 'decimal_digits': 0, 'decimal_separator': ',', 'thousands_separator': '.'},
    'il': {'symbol': '₪', 'is_prefixed': True, 'decimal_digits': 2, 'decimal_separator': '.', 'thousands_separator': ','},
    'jp': {'symbol': '¥', 'is_prefixed': True, 'decimal_digits': 0, 'decimal_separator': '.', 'thousands_separator': ','},
    'kz': {'symbol': '₸', 'is_prefixed': False, 'decimal_digits': 2, 'decimal_separator': ',', 'thousands_separator': ' '},
    'kw': {'symbol': 'KD', 'is_prefixed': True, 'decimal_digits': 3, 'decimal_separator': '.', 'thousands_separator': ','},
    'ar': {'symbol': '$', 'is_prefixed': True, 'decimal_digits': 2, 'decimal_separator': '.', 'thousands_separator': ','},
    'my': {'symbol': 'RM', 'is_prefixed': True, 'decimal_digits': 2, 'decimal_separator': '.', 'thousands_separator': ','},
    'tr': {'symbol': '₺', 'is_prefixed': False, 'decimal_digits': 2, 'decimal_separator': ',', 'thousands_separator': '.'},
    'mx': {'symbol': '$', 'is_prefixed': True, 'decimal_digits': 2, 'decimal_separator': '.', 'thousands_separator': ','},
    'nz': {'symbol': '$', 'is_prefixed': True, 'decimal_digits': 2, 'decimal_separator': '.', 'thousands_separator': ','},
    'no': {'symbol': 'kr', 'is_prefixed': False, 'decimal_digits': 2, 'decimal_separator': ',', 'thousands_separator': ' '},
    'pe': {'symbol': 'S/.', 'is_prefixed': True, 'decimal_digits': 2, 'decimal_separator': ',', 'thousands_separator': '.'},
    'ph': {'symbol': '₱', 'is_prefixed': True, 'decimal_digits': 2, 'decimal_separator': '.', 'thousands_separator': ','},
    'pl': {'symbol': 'zł', 'is_prefixed': False, 'decimal_digits': 2, 'decimal_separator': ',', 'thousands_separator': ' '},
    'qa': {'symbol': 'QR', 'is_prefixed': True, 'decimal_digits': 2, 'decimal_separator': '.', 'thousands_separator': ','},
    'ru': {'symbol': '₽', 'is_prefixed': False, 'decimal_digits': 2, 'decimal_separator': ',', 'thousands_separator': ' '},
    'sa': {'symbol': 'SR', 'is_prefixed': True, 'decimal_digits': 2, 'decimal_separator': '.', 'thousands_separator': ','},
    'sg': {'symbol': '$', 'is_prefixed': True, 'decimal_digits': 2, 'decimal_separator': '.', 'thousands_separator': ','},
    'za': {'symbol': 'R', 'is_prefixed': True, 'decimal_digits': 2, 'decimal_separator': '.', 'thousands_separator': ','},
    'pk': {'symbol': '$', 'is_prefixed': True, 'decimal_digits': 2, 'decimal_separator': '.', 'thousands_separator': ','},
    'kr': {'symbol': '₩', 'is_prefixed': True, 'decimal_digits': 0, 'decimal_separator': '.', 'thousands_separator': ','},
    'ch': {'symbol': 'CHF', 'is_prefixed': True, 'decimal_digits': 2, 'decimal_separator': '.', 'thousands_separator': '\''},
    'tw': {'symbol': 'NT$', 'is_prefixed': True, 'decimal_digits': 2, 'decimal_separator': '.', 'thousands_separator': ','},
    'th': {'symbol': '฿', 'is_prefixed': True, 'decimal_digits': 2, 'decimal_separator': '.', 'thousands_separator': ','},
    'ae': {'symbol': 'AED', 'is_prefixed': True, 'decimal_digits': 2, 'decimal_separator': '.', 'thousands_separator': ','},
    'us': {'symbol': '$', 'is_prefixed': True, 'decimal_digits': 2, 'decimal_separator': '.', 'thousands_separator': ','},
    'ua': {'symbol': '₴', 'is_prefixed': False, 'decimal_digits': 2, 'decimal_separator': ',', 'thousands_separator': ' '},
    'uy': {'symbol': '$U', 'is_prefixed': True, 'decimal_digits': 2, 'decimal_separator': ',', 'thousands_separator': '.'},
    'vn': {'symbol': '₫', 'is_prefixed': False, 'decimal_digits': 0, 'decimal_separator': '.', 'thousands_separator': '.'},
}

def format_price(price_int, country_code='us'):

    if price_int == 0:
        return "Free"
    
    info = CURRENCY_DATA.get(country_code, CURRENCY_DATA['us'])

    symbol = info['symbol']
    is_prefixed = info['is_prefixed']
    decimal_digits = info['decimal_digits']
    decimal_separator = info['decimal_separator']
    thousands_separator = info['thousands_separator']

    amount = price_int / (10 ** decimal_digits)

    if decimal_digits > 0:
        format_string = f"{{:,.{decimal_digits}f}}" 
        num_str = format_string.format(amount)
    else:
        num_str = f"{int(amount):,}"

    if thousands_separator == '.' and decimal_separator == ',':
        num_str = num_str.replace(',', 'TEMP').replace('.', decimal_separator).replace('TEMP', thousands_separator)
    elif thousands_separator != ',' and decimal_separator != '.':
        num_str = num_str.replace(',', thousands_separator)

    if is_prefixed:
        return f"{symbol}{num_str}"
    else:
        return f"{num_str} {symbol}"