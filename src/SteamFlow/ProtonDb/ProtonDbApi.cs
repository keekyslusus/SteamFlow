using System.Net;
using System.Text.Json;

namespace SteamFlow.ProtonDb;

public sealed record ProtonDbSummary(string Tier, string TrendingTier, int Reports);

public sealed class ProtonDbApi(HttpClient http)
{
    // Not a documented API: it is the JSON the ProtonDB site loads for its own app pages.
    public async Task<ProtonDbSummary?> SummaryAsync(int appId, CancellationToken token)
    {
        using var response = await http.GetAsync($"https://www.protondb.com/api/v1/reports/summaries/{appId}.json", token);
        // Apps nobody has reported on get an HTML 404 page instead of JSON.
        if (response.StatusCode == HttpStatusCode.NotFound)
        {
            return null;
        }

        response.EnsureSuccessStatusCode();
        return ParseSummary(await response.Content.ReadAsStringAsync(token));
    }

    public static ProtonDbSummary? ParseSummary(string json)
    {
        using var document = JsonDocument.Parse(json);
        var root = document.RootElement;
        if (root.ValueKind != JsonValueKind.Object || Tier(root, "tier") is not { } tier)
        {
            return null;
        }

        var reports = root.TryGetProperty("total", out var total) && total.TryGetInt32(out var count) ? count : 0;
        return new ProtonDbSummary(tier, Tier(root, "trendingTier") ?? tier, reports);
    }

    private static string? Tier(JsonElement root, string name) =>
        root.TryGetProperty(name, out var value) && value.ValueKind == JsonValueKind.String && value.GetString() is { Length: > 0 } tier
            ? tier.ToLowerInvariant()
            : null;
}
