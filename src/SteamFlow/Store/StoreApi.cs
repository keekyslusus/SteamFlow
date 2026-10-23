using System.Globalization;
using System.Text.Json;

namespace SteamFlow.Store;

public sealed class StoreApi(HttpClient http)
{
    private const string StoreUrl = "https://store.steampowered.com";
    private const string WebApiUrl = "https://api.steampowered.com";

    // Steam geolocates every anonymous store visitor and reports the result in the steamCountry cookie,
    // which is the region its prices are shown in; a HEAD request gets it without downloading the page.
    public async Task<string?> FetchCountryCodeAsync(CancellationToken token)
    {
        using var request = new HttpRequestMessage(HttpMethod.Head, StoreUrl + "/");
        using var response = await http.SendAsync(request, HttpCompletionOption.ResponseHeadersRead, token);
        return response.Headers.TryGetValues("Set-Cookie", out var cookies) ? ParseCountryCookie(cookies) : null;
    }

    public async Task<IReadOnlyList<StoreSearchItem>> SearchAsync(string term, string countryCode, string language, CancellationToken token) =>
        ParseSearch(await http.GetStringAsync(
            $"{StoreUrl}/api/storesearch/?term={Uri.EscapeDataString(term)}&cc={countryCode}&l={language}", token));

    public async Task<FeaturedCollections> FeaturedAsync(string countryCode, string language, CancellationToken token) =>
        ParseFeatured(await http.GetStringAsync($"{StoreUrl}/api/featuredcategories/?cc={countryCode}&l={language}", token));

    public async Task<AppDetails?> AppDetailsAsync(int appId, string countryCode, string language, CancellationToken token) =>
        ParseAppDetails(
            await http.GetStringAsync(
                $"{StoreUrl}/api/appdetails?appids={appId}&cc={countryCode}&l={language}&filters=basic,release_date,developers,publishers", token),
            appId);

    // appdetails accepts several app IDs only with the price_overview filter, which keeps this to one request.
    public async Task<IReadOnlyDictionary<int, StorePrice>> PricesAsync(IReadOnlyCollection<int> appIds, string countryCode, CancellationToken token) =>
        ParsePrices(await http.GetStringAsync(
            $"{StoreUrl}/api/appdetails?appids={string.Join(',', appIds)}&cc={countryCode}&filters=price_overview", token));

    public async Task<byte[]?> DownloadAsync(string url, CancellationToken token)
    {
        using var response = await http.GetAsync(url, token);
        return response.IsSuccessStatusCode ? await response.Content.ReadAsByteArrayAsync(token) : null;
    }

    public async Task<ReviewSummary?> ReviewsAsync(int appId, CancellationToken token) =>
        ParseReviews(await http.GetStringAsync(
            $"{StoreUrl}/appreviews/{appId}?json=1&language=all&purchase_type=all&num_per_page=0", token));

    public async Task<PlayerCount?> CurrentPlayersAsync(int appId, CancellationToken token) =>
        ParsePlayers(await http.GetStringAsync(
            $"{WebApiUrl}/ISteamUserStats/GetNumberOfCurrentPlayers/v1/?appid={appId}", token));

    public static string? ParseCountryCookie(IEnumerable<string> setCookieHeaders)
    {
        const string prefix = "steamCountry=";
        foreach (var header in setCookieHeaders)
        {
            if (!header.StartsWith(prefix, StringComparison.OrdinalIgnoreCase))
            {
                continue;
            }

            var value = Uri.UnescapeDataString(header[prefix.Length..].Split(';')[0]);
            var country = value.Split('|')[0];
            return country.Length == 2 && country.All(char.IsAsciiLetter) ? country.ToLowerInvariant() : null;
        }

        return null;
    }

    public static IReadOnlyList<StoreSearchItem> ParseSearch(string json)
    {
        using var document = JsonDocument.Parse(json);
        if (!document.RootElement.TryGetProperty("items", out var items) || items.ValueKind != JsonValueKind.Array)
        {
            return [];
        }

        var results = new List<StoreSearchItem>();
        foreach (var item in items.EnumerateArray())
        {
            if (Int(item, "id") is not { } appId)
            {
                continue;
            }

            results.Add(new StoreSearchItem(
                appId,
                String(item, "type") ?? "",
                String(item, "name") ?? "",
                String(item, "tiny_image")));
        }

        return results;
    }

    public static FeaturedCollections ParseFeatured(string json)
    {
        using var document = JsonDocument.Parse(json);
        return new FeaturedCollections(
            FeaturedItems(document.RootElement, "top_sellers"),
            FeaturedItems(document.RootElement, "specials"));
    }

    private static List<StoreSearchItem> FeaturedItems(JsonElement root, string collection)
    {
        var results = new List<StoreSearchItem>();
        if (!root.TryGetProperty(collection, out var section)
            || !section.TryGetProperty("items", out var items)
            || items.ValueKind != JsonValueKind.Array)
        {
            return results;
        }

        foreach (var item in items.EnumerateArray())
        {
            if (Int(item, "id") is { } appId)
            {
                results.Add(new StoreSearchItem(
                    appId,
                    "app",
                    String(item, "name") ?? "",
                    String(item, "small_capsule_image")));
            }
        }

        return results;
    }

    public static AppDetails? ParseAppDetails(string json, int appId)
    {
        using var document = JsonDocument.Parse(json);
        if (!document.RootElement.TryGetProperty(appId.ToString(CultureInfo.InvariantCulture), out var app)
            || Bool(app, "success") != true
            || !app.TryGetProperty("data", out var data)
            || data.ValueKind != JsonValueKind.Object)
        {
            return null;
        }

        data.TryGetProperty("release_date", out var release);
        return new AppDetails(
            (String(data, "type") ?? "").Trim().ToLowerInvariant(),
            (String(data, "name") ?? "").Trim(),
            Bool(data, "is_free"),
            Bool(release, "coming_soon") == true,
            (String(release, "date") ?? "").Trim(),
            String(data, "capsule_image"),
            Names(data, "developers"),
            Names(data, "publishers"));
    }

    public static IReadOnlyDictionary<int, StorePrice> ParsePrices(string json)
    {
        using var document = JsonDocument.Parse(json);
        var prices = new Dictionary<int, StorePrice>();
        if (document.RootElement.ValueKind != JsonValueKind.Object)
        {
            return prices;
        }

        foreach (var app in document.RootElement.EnumerateObject())
        {
            // Free and unreleased apps come back with "data": [] instead of an object.
            if (int.TryParse(app.Name, NumberStyles.None, CultureInfo.InvariantCulture, out var appId)
                && app.Value.TryGetProperty("data", out var data)
                && data.ValueKind == JsonValueKind.Object
                && data.TryGetProperty("price_overview", out var price)
                && String(price, "final_formatted") is { Length: > 0 } final)
            {
                prices[appId] = new StorePrice(final, Int(price, "discount_percent") ?? 0);
            }
        }

        return prices;
    }

    public static ReviewSummary? ParseReviews(string json)
    {
        using var document = JsonDocument.Parse(json);
        if (!document.RootElement.TryGetProperty("query_summary", out var summary))
        {
            return null;
        }

        return new ReviewSummary(Int(summary, "total_positive") ?? 0, Int(summary, "total_reviews") ?? 0);
    }

    public static PlayerCount? ParsePlayers(string json)
    {
        using var document = JsonDocument.Parse(json);
        return document.RootElement.TryGetProperty("response", out var response)
            && Int(response, "result") == 1
            && Int(response, "player_count") is { } count
                ? new PlayerCount(count)
                : null;
    }

    private static string? String(JsonElement element, string name) =>
        element.ValueKind == JsonValueKind.Object
        && element.TryGetProperty(name, out var value)
        && value.ValueKind == JsonValueKind.String
            ? value.GetString()
            : null;

    private static List<string> Names(JsonElement element, string name) =>
        element.ValueKind == JsonValueKind.Object
        && element.TryGetProperty(name, out var value)
        && value.ValueKind == JsonValueKind.Array
            ? value.EnumerateArray()
                .Where(item => item.ValueKind == JsonValueKind.String)
                .Select(item => item.GetString()!.Trim())
                .Where(item => item.Length > 0)
                .Distinct(StringComparer.OrdinalIgnoreCase)
                .ToList()
            : [];

    private static int? Int(JsonElement element, string name) =>
        element.ValueKind == JsonValueKind.Object
        && element.TryGetProperty(name, out var value)
        && value.ValueKind == JsonValueKind.Number
        && value.TryGetInt32(out var number)
            ? number
            : null;

    private static bool? Bool(JsonElement element, string name)
    {
        if (element.ValueKind != JsonValueKind.Object || !element.TryGetProperty(name, out var value))
        {
            return null;
        }

        return value.ValueKind switch
        {
            JsonValueKind.True => true,
            JsonValueKind.False => false,
            JsonValueKind.Number when value.TryGetInt32(out var number) && number is 0 or 1 => number == 1,
            _ => null,
        };
    }
}
