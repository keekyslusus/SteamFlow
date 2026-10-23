using System.Globalization;
using System.Text.Json;
using SteamFlow.Library;

namespace SteamFlow.WebApi;

public sealed record OwnedGames(IReadOnlySet<int> AppIds, IReadOnlyDictionary<int, int> PlaytimeMinutes)
{
    public static readonly OwnedGames None = new(new HashSet<int>(), new Dictionary<int, int>());
}

public sealed record ProfileSummary(int PersonaState, string GameName);

public sealed record AvatarFrame(string Id, string ImageUrl);

public sealed record WishlistItem(int AppId, DateTimeOffset DateAdded);

public sealed record ServiceResponse(int StatusCode, int? EResult)
{
    public bool Unauthorized => StatusCode is 401 or 403;

    public bool Succeeded => StatusCode == 200 && EResult == 1;
}

public sealed class SteamWebApi(HttpClient http)
{
    private const string WebApiUrl = "https://api.steampowered.com";

    // Steam answers 401/403 for a wrong key, which surfaces as an HttpRequestException with that status.
    public async Task<OwnedGames> OwnedGamesAsync(string apiKey, ulong steamId64, CancellationToken token)
    {
        using var response = await http.GetAsync(
            string.Create(CultureInfo.InvariantCulture,
                $"{WebApiUrl}/IPlayerService/GetOwnedGames/v1/?key={apiKey}&steamid={steamId64}&include_played_free_games=1&include_appinfo=0"),
            token);
        response.EnsureSuccessStatusCode();
        return ParseOwnedGames(await response.Content.ReadAsStringAsync(token));
    }

    public async Task<ProfileSummary?> PlayerSummaryAsync(string apiKey, ulong steamId64, CancellationToken token) =>
        ParsePlayerSummary(await GetAsync($"{WebApiUrl}/ISteamUser/GetPlayerSummaries/v2/?key={apiKey}&steamids={steamId64}", token));

    public async Task<AvatarFrame?> AvatarFrameAsync(string apiKey, ulong steamId64, CancellationToken token) =>
        ParseAvatarFrame(await GetAsync($"{WebApiUrl}/IPlayerService/GetAvatarFrame/v1/?key={apiKey}&steamid={steamId64}", token));

    // The player list carries every achievement with an "achieved" flag, so it gives the total as well.
    // Games without stats answer 400, which the caller treats like missing data.
    public async Task<AchievementProgress?> PlayerAchievementsAsync(string apiKey, ulong steamId64, int appId, CancellationToken token) =>
        ParsePlayerAchievements(await GetAsync(
            $"{WebApiUrl}/ISteamUserStats/GetPlayerAchievements/v1/?key={apiKey}&steamid={steamId64}&appid={appId}&l=en", token));

    public async Task<IReadOnlyList<WishlistItem>> WishlistAsync(string apiKey, ulong steamId64, CancellationToken token) =>
        ParseWishlist(await GetAsync($"{WebApiUrl}/IWishlistService/GetWishlist/v1/?key={apiKey}&steamid={steamId64}", token));

    // Service methods answer 200 for most logical failures and report them in X-eresult (1 means OK),
    // so the status code alone does not prove the wishlist changed.
    public async Task<ServiceResponse> MutateWishlistAsync(string accessToken, int appId, bool add, CancellationToken token)
    {
        var method = add ? "AddToWishlist" : "RemoveFromWishlist";
        using var request = new HttpRequestMessage(HttpMethod.Post, $"{WebApiUrl}/IWishlistService/{method}/v1/")
        {
            Content = new FormUrlEncodedContent(new Dictionary<string, string>
            {
                ["access_token"] = accessToken,
                ["appid"] = appId.ToString(CultureInfo.InvariantCulture),
            }),
        };
        request.Headers.Add("Origin", "https://store.steampowered.com");
        request.Headers.Referrer = new Uri("https://store.steampowered.com/");
        using var response = await http.SendAsync(request, token);
        var eresult = response.Headers.TryGetValues("x-eresult", out var values)
            && int.TryParse(values.FirstOrDefault(), NumberStyles.Integer, CultureInfo.InvariantCulture, out var code)
                ? code
                : (int?)null;
        return new ServiceResponse((int)response.StatusCode, eresult);
    }

    public static IReadOnlyList<WishlistItem> ParseWishlist(string json)
    {
        using var document = JsonDocument.Parse(json);
        if (!document.RootElement.TryGetProperty("response", out var response)
            || !response.TryGetProperty("items", out var items)
            || items.ValueKind != JsonValueKind.Array)
        {
            return [];
        }

        return items.EnumerateArray()
            .Where(item => Int(item, "appid") is not null)
            .Select(item => new WishlistItem(Int(item, "appid")!.Value, DateTimeOffset.FromUnixTimeSeconds(Long(item, "date_added") ?? 0)))
            .ToList();
    }

    public async Task<byte[]> DownloadAsync(string url, CancellationToken token) =>
        await http.GetByteArrayAsync(url, token);

    public static ProfileSummary? ParsePlayerSummary(string json)
    {
        using var document = JsonDocument.Parse(json);
        if (!document.RootElement.TryGetProperty("response", out var response)
            || !response.TryGetProperty("players", out var players)
            || players.ValueKind != JsonValueKind.Array
            || players.GetArrayLength() == 0)
        {
            return null;
        }

        var player = players[0];
        return new ProfileSummary(
            Int(player, "personastate") ?? 0,
            player.TryGetProperty("gameextrainfo", out var game) && game.ValueKind == JsonValueKind.String ? game.GetString()!.Trim() : "");
    }

    public static AvatarFrame? ParseAvatarFrame(string json)
    {
        const string communityAssets = "https://shared.fastly.steamstatic.com/community_assets/images/";
        using var document = JsonDocument.Parse(json);
        if (!document.RootElement.TryGetProperty("response", out var response)
            || !response.TryGetProperty("avatar_frame", out var frame)
            || frame.ValueKind != JsonValueKind.Object
            || !frame.TryGetProperty("communityitemid", out var idValue))
        {
            return null;
        }

        var image = new[] { "image_small", "image_large" }
            .Select(name => frame.TryGetProperty(name, out var value) && value.ValueKind == JsonValueKind.String ? value.GetString() : null)
            .FirstOrDefault(value => !string.IsNullOrWhiteSpace(value));
        var id = idValue.ValueKind == JsonValueKind.String ? idValue.GetString() : idValue.GetRawText();
        if (string.IsNullOrWhiteSpace(id) || image is null || !id.All(char.IsAsciiDigit))
        {
            return null;
        }

        return new AvatarFrame(id, image.StartsWith("https://", StringComparison.Ordinal) ? image : communityAssets + image.TrimStart('/'));
    }

    public static AchievementProgress? ParsePlayerAchievements(string json)
    {
        using var document = JsonDocument.Parse(json);
        if (!document.RootElement.TryGetProperty("playerstats", out var stats)
            || !stats.TryGetProperty("achievements", out var achievements)
            || achievements.ValueKind != JsonValueKind.Array
            || achievements.GetArrayLength() == 0)
        {
            return null;
        }

        var unlocked = achievements.EnumerateArray()
            .Count(item => Int(item, "achieved") == 1);
        return new AchievementProgress(unlocked, achievements.GetArrayLength());
    }

    // Steam occasionally sends numbers as strings; reading a non-number as one would throw instead of skipping.
    private static int? Int(JsonElement element, string name) =>
        element.ValueKind == JsonValueKind.Object
        && element.TryGetProperty(name, out var value)
        && value.ValueKind == JsonValueKind.Number
        && value.TryGetInt32(out var number)
            ? number
            : null;

    private static long? Long(JsonElement element, string name) =>
        element.ValueKind == JsonValueKind.Object
        && element.TryGetProperty(name, out var value)
        && value.ValueKind == JsonValueKind.Number
        && value.TryGetInt64(out var number)
            ? number
            : null;

    private async Task<string> GetAsync(string url, CancellationToken token)
    {
        using var response = await http.GetAsync(url, token);
        response.EnsureSuccessStatusCode();
        return await response.Content.ReadAsStringAsync(token);
    }

    public static OwnedGames ParseOwnedGames(string json)
    {
        using var document = JsonDocument.Parse(json);
        var appIds = new HashSet<int>();
        var playtime = new Dictionary<int, int>();
        if (!document.RootElement.TryGetProperty("response", out var response)
            || !response.TryGetProperty("games", out var games)
            || games.ValueKind != JsonValueKind.Array)
        {
            return new OwnedGames(appIds, playtime);
        }

        foreach (var game in games.EnumerateArray())
        {
            if (Int(game, "appid") is not { } appId)
            {
                continue;
            }

            appIds.Add(appId);
            playtime[appId] = Int(game, "playtime_forever") ?? 0;
        }

        return new OwnedGames(appIds, playtime);
    }
}
