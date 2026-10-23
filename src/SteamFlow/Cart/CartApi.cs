using System.Globalization;
using System.Text.Json;
using SteamFlow.WebApi;

namespace SteamFlow.Cart;

// The store moved to an account-wide cart; IAccountCartService accepts JSON input, so no hand-built protobuf
// (the Python plugin's CreateNewShoppingCart + AddPackages + merge route) is needed.
public sealed class CartApi(HttpClient http)
{
    private const string WebApiUrl = "https://api.steampowered.com/IAccountCartService";

    public async Task<int?> PackageForAppAsync(int appId, string countryCode, CancellationToken token) =>
        ParsePackage(
            await http.GetStringAsync(
                $"https://store.steampowered.com/api/appdetails?appids={appId}&cc={countryCode}&filters=packages,package_groups", token),
            appId);

    public async Task<ServiceResponse> AddAsync(string accessToken, string countryCode, int packageId, CancellationToken token)
    {
        var input = JsonSerializer.Serialize(new
        {
            user_country = countryCode.ToUpperInvariant(),
            items = new[] { new { packageid = packageId } },
        });
        using var request = new HttpRequestMessage(HttpMethod.Post, $"{WebApiUrl}/AddItemsToCart/v1/")
        {
            Content = new FormUrlEncodedContent(new Dictionary<string, string>
            {
                ["access_token"] = accessToken,
                ["input_json"] = input,
            }),
        };
        request.Headers.Add("Origin", "https://store.steampowered.com");
        using var response = await http.SendAsync(request, token);
        return new ServiceResponse((int)response.StatusCode, EResult(response));
    }

    public async Task<IReadOnlySet<int>?> PackagesInCartAsync(string accessToken, string countryCode, CancellationToken token)
    {
        var input = Uri.EscapeDataString(JsonSerializer.Serialize(new { user_country = countryCode.ToUpperInvariant() }));
        using var response = await http.GetAsync($"{WebApiUrl}/GetCart/v1/?access_token={accessToken}&input_json={input}", token);
        return response.IsSuccessStatusCode && EResult(response) == 1
            ? ParseCartPackages(await response.Content.ReadAsStringAsync(token))
            : null;
    }

    // The default purchase group is what the store's own "Add to Cart" button buys.
    public static int? ParsePackage(string json, int appId)
    {
        using var document = JsonDocument.Parse(json);
        if (!document.RootElement.TryGetProperty(appId.ToString(CultureInfo.InvariantCulture), out var app)
            || !app.TryGetProperty("data", out var data)
            || data.ValueKind != JsonValueKind.Object)
        {
            return null;
        }

        if (data.TryGetProperty("package_groups", out var groups) && groups.ValueKind == JsonValueKind.Array)
        {
            var ordered = groups.EnumerateArray()
                .Where(group => group.ValueKind == JsonValueKind.Object)
                .OrderBy(group => group.TryGetProperty("name", out var name) && name.GetString() == "default" ? 0 : 1);
            foreach (var group in ordered)
            {
                if (!group.TryGetProperty("subs", out var subs) || subs.ValueKind != JsonValueKind.Array)
                {
                    continue;
                }

                foreach (var sub in subs.EnumerateArray())
                {
                    if (Number(sub, "packageid") is > 0 and var packageId)
                    {
                        return packageId;
                    }
                }
            }
        }

        return data.TryGetProperty("packages", out var packages) && packages.ValueKind == JsonValueKind.Array
            ? packages.EnumerateArray()
                .Where(package => package.ValueKind == JsonValueKind.Number && package.TryGetInt32(out var value) && value > 0)
                .Select(package => (int?)package.GetInt32())
                .FirstOrDefault()
            : null;
    }

    public static IReadOnlySet<int> ParseCartPackages(string json)
    {
        using var document = JsonDocument.Parse(json);
        var packages = new HashSet<int>();
        if (document.RootElement.TryGetProperty("response", out var response)
            && response.TryGetProperty("cart", out var cart)
            && cart.TryGetProperty("line_items", out var items)
            && items.ValueKind == JsonValueKind.Array)
        {
            foreach (var item in items.EnumerateArray())
            {
                if (Number(item, "packageid") is > 0 and var packageId)
                {
                    packages.Add(packageId);
                }
            }
        }

        return packages;
    }

    // Steam writes 64-bit ids as strings and small ones as numbers, so both are accepted here.
    private static int? Number(JsonElement element, string name)
    {
        if (element.ValueKind != JsonValueKind.Object || !element.TryGetProperty(name, out var value))
        {
            return null;
        }

        return value.ValueKind switch
        {
            JsonValueKind.Number when value.TryGetInt32(out var number) => number,
            JsonValueKind.String when int.TryParse(value.GetString(), NumberStyles.None, CultureInfo.InvariantCulture, out var number) => number,
            _ => null,
        };
    }

    private static int? EResult(HttpResponseMessage response) =>
        response.Headers.TryGetValues("x-eresult", out var values)
        && int.TryParse(values.FirstOrDefault(), NumberStyles.Integer, CultureInfo.InvariantCulture, out var code)
            ? code
            : null;
}
