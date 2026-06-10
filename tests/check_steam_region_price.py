import json
import sys
import urllib.error
import urllib.parse
import urllib.request


DEFAULT_APP_ID = "2483190"
USER_AGENT = "Mozilla/5.0"


def configure_console():
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if callable(reconfigure):
        reconfigure(encoding="utf-8", errors="replace")


def normalize_country_code(value):
    country_code = str(value or "").strip().lower()
    if len(country_code) != 2 or not country_code.isascii() or not country_code.isalpha():
        raise ValueError("Country code must be two ASCII letters, for example: us, kz, de, gb.")
    return country_code


def fetch_app_details(app_id, country_code):
    query = urllib.parse.urlencode(
        {
            "appids": str(app_id),
            "cc": country_code,
            "l": "en",
        }
    )
    url = f"https://store.steampowered.com/api/appdetails?{query}"
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=10) as response:
        payload = json.loads(response.read().decode("utf-8"))

    result = payload.get(str(app_id), {})
    if not isinstance(result, dict) or not result.get("success"):
        raise RuntimeError("Steam did not return app details.")

    details = result.get("data", {})
    if not isinstance(details, dict):
        raise RuntimeError("Steam returned invalid app details.")
    return url, details


def print_price(app_id, country_code):
    url, details = fetch_app_details(app_id, country_code)
    price = details.get("price_overview")

    print()
    print(f"App:      {details.get('name', app_id)} ({app_id})")
    print(f"Country:  {country_code}")
    print(f"Request:  {url}")

    if details.get("is_free") is True:
        print("Price:    Free")
        return

    if not isinstance(price, dict):
        print("Price:    unavailable for this region")
        return

    print(f"Currency: {price.get('currency', '')}")
    print(f"Initial:  {price.get('initial_formatted', '')}  [raw: {price.get('initial', '')}]")
    print(f"Final:    {price.get('final_formatted', '')}  [raw: {price.get('final', '')}]")
    print(f"Discount: {price.get('discount_percent', 0)}%")


def main():
    configure_console()
    app_id = str(sys.argv[1]).strip() if len(sys.argv) > 1 else DEFAULT_APP_ID
    print(f"Steam regional price checker. App ID: {app_id}")
    print("Enter an ISO 3166-1 alpha-2 country code. Examples: us, kz, de, gb.")
    print("Press Enter without a code to exit.")

    while True:
        try:
            raw_country_code = input("\nCountry code: ")
        except EOFError:
            return 0

        if not raw_country_code.strip():
            return 0

        try:
            print_price(app_id, normalize_country_code(raw_country_code))
        except ValueError as error:
            print(f"Invalid input: {error}")
        except urllib.error.URLError as error:
            print(f"Request failed: {error}")
        except Exception as error:
            print(f"Error: {error}")


if __name__ == "__main__":
    raise SystemExit(main())
