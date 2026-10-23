using System.Globalization;
using System.Net;
using System.Text.Json;
using System.Text.RegularExpressions;

namespace SteamFlow.Friends;

public enum Presence
{
    Playing,
    Online,
    Away,
    Offline,
}

public sealed record Friend(
    ulong SteamId64,
    string Name,
    string? AvatarUrl,
    int PersonaState,
    DateTimeOffset? LastLogoff,
    int? GameId,
    string GameName,
    ulong? LobbyId,
    bool HasServer)
{
    public uint AccountId => unchecked((uint)SteamId64);

    public Presence Presence =>
        GameId is not null || GameName.Length > 0 ? Presence.Playing
        : PersonaState is 1 or 5 or 6 ? Presence.Online
        : PersonaState is 2 or 3 or 4 ? Presence.Away
        : Presence.Offline;
}

public sealed record JoinDetails(int AppId, bool Joinable, ulong? LobbyId);

public sealed class FriendsListUnavailableException(string message) : Exception(message);

public sealed partial class FriendsApi(HttpClient http)
{
    private const string WebApiUrl = "https://api.steampowered.com";
    private const int SummariesBatch = 100;

    // A private friend list answers 401/403, which is a state to show rather than an error to retry.
    public async Task<IReadOnlyList<Friend>> FriendsAsync(string apiKey, ulong steamId64, CancellationToken token)
    {
        using var response = await http.GetAsync($"{WebApiUrl}/ISteamUser/GetFriendList/v1/?key={apiKey}&steamid={steamId64}&relationship=friend", token);
        if (response.StatusCode is HttpStatusCode.Unauthorized or HttpStatusCode.Forbidden)
        {
            throw new FriendsListUnavailableException("Steam friend list is private");
        }

        response.EnsureSuccessStatusCode();
        var ids = ParseFriendIds(await response.Content.ReadAsStringAsync(token));
        var friends = new List<Friend>();
        foreach (var batch in ids.Chunk(SummariesBatch))
        {
            friends.AddRange(ParseSummaries(await http.GetStringAsync(
                $"{WebApiUrl}/ISteamUser/GetPlayerSummaries/v2/?key={apiKey}&steamids={string.Join(',', batch)}", token)));
        }

        return friends;
    }

    public async Task<IReadOnlySet<uint>> FavoritesAsync(string accessToken, CancellationToken token) =>
        ParseFavorites(await http.GetStringAsync($"{WebApiUrl}/IFriendsListService/GetFavorites/v1/?access_token={accessToken}", token));

    // Rich presence and private lobby data are only visible to friends, so this call needs the session token.
    public async Task<IReadOnlyDictionary<ulong, JoinDetails>> JoinDetailsAsync(string accessToken, IEnumerable<ulong> steamIds, CancellationToken token)
    {
        var input = Uri.EscapeDataString(JsonSerializer.Serialize(new { steamids = steamIds.Select(id => id.ToString(CultureInfo.InvariantCulture)) }));
        return ParseJoinDetails(await http.GetStringAsync(
            $"{WebApiUrl}/IPlayerService/GetPlayerLinkDetails/v1/?access_token={accessToken}&input_json={input}", token));
    }

    public static IReadOnlyList<ulong> ParseFriendIds(string json)
    {
        using var document = JsonDocument.Parse(json);
        if (!document.RootElement.TryGetProperty("friendslist", out var list)
            || !list.TryGetProperty("friends", out var friends)
            || friends.ValueKind != JsonValueKind.Array)
        {
            throw new FriendsListUnavailableException("Steam returned no friend list");
        }

        return friends.EnumerateArray()
            .Select(friend => UInt64(friend, "steamid"))
            .OfType<ulong>()
            .Distinct()
            .ToList();
    }

    public static IReadOnlyList<Friend> ParseSummaries(string json)
    {
        using var document = JsonDocument.Parse(json);
        if (!document.RootElement.TryGetProperty("response", out var response)
            || !response.TryGetProperty("players", out var players)
            || players.ValueKind != JsonValueKind.Array)
        {
            return [];
        }

        var friends = new List<Friend>();
        foreach (var player in players.EnumerateArray())
        {
            if (UInt64(player, "steamid") is not { } steamId64)
            {
                continue;
            }

            var lastLogoff = Int64(player, "lastlogoff");
            var server = String(player, "gameserverip");
            friends.Add(new Friend(
                steamId64,
                String(player, "personaname") ?? "",
                String(player, "avatarmedium") ?? String(player, "avatar"),
                (int)(Int64(player, "personastate") ?? 0),
                lastLogoff > 0 ? DateTimeOffset.FromUnixTimeSeconds(lastLogoff.Value) : null,
                // Non-Steam games and mods report 64-bit game ids that are not app ids.
                UInt64(player, "gameid") is <= int.MaxValue and var gameId ? (int)gameId : null,
                String(player, "gameextrainfo") ?? "",
                UInt64(player, "lobbysteamid") is > 0 and var lobby ? lobby : null,
                UInt64(player, "gameserversteamid") is > 0 || (server is { Length: > 0 } && server is not ("0" or "0.0.0.0" or "0.0.0.0:0"))));
        }

        return friends;
    }

    public static IReadOnlySet<uint> ParseFavorites(string json)
    {
        using var document = JsonDocument.Parse(json);
        return document.RootElement.TryGetProperty("response", out var response)
            && response.TryGetProperty("favorites", out var favorites)
            && favorites.ValueKind == JsonValueKind.Array
                ? favorites.EnumerateArray().Select(item => UInt64(item, "accountid")).OfType<ulong>().Select(id => (uint)id).ToHashSet()
                : new HashSet<uint>();
    }

    public static IReadOnlyDictionary<ulong, JoinDetails> ParseJoinDetails(string json)
    {
        using var document = JsonDocument.Parse(json);
        var details = new Dictionary<ulong, JoinDetails>();
        if (!document.RootElement.TryGetProperty("response", out var response)
            || !response.TryGetProperty("accounts", out var accounts)
            || accounts.ValueKind != JsonValueKind.Array)
        {
            return details;
        }

        foreach (var account in accounts.EnumerateArray())
        {
            if (!account.TryGetProperty("public_data", out var publicData)
                || !account.TryGetProperty("private_data", out var privateData)
                || UInt64(publicData, "steamid") is not { } steamId64
                || UInt64(privateData, "game_id") is not (> 0 and var gameId))
            {
                continue;
            }

            var lobby = UInt64(privateData, "lobby_steam_id");
            var hasConnect = ConnectPattern().IsMatch(String(privateData, "rich_presence_kv") ?? "");
            var hasServer = UInt64(privateData, "game_server_ip_address") > 0 && UInt64(privateData, "game_server_port") > 0;
            var isPrivate = privateData.TryGetProperty("game_is_private", out var gameIsPrivate) && gameIsPrivate.ValueKind == JsonValueKind.True;
            details[steamId64] = new JoinDetails(
                (int)gameId,
                !isPrivate && (hasConnect || lobby > 0 || hasServer),
                lobby > 0 ? lobby : null);
        }

        return details;
    }

    // The Web API only has rich presence as raw keys whose text lives in each game's localization, which is not
    // served over HTTP; the community mini profile (the hover card) carries it already rendered in `language`.
    public async Task<string> RichPresenceAsync(uint accountId, string language, CancellationToken token) =>
        ParseRichPresence(await http.GetStringAsync(
            string.Create(CultureInfo.InvariantCulture, $"https://steamcommunity.com/miniprofile/{accountId}/json?l={language}"), token));

    public static string ParseRichPresence(string json)
    {
        using var document = JsonDocument.Parse(json);
        return document.RootElement.ValueKind == JsonValueKind.Object
            && document.RootElement.TryGetProperty("in_game", out var game)
            && String(game, "rich_presence") is { } text
                ? string.Join(' ', text.Split((char[]?)null, StringSplitOptions.RemoveEmptyEntries))
                : "";
    }

    private static string? String(JsonElement element, string name) =>
        element.ValueKind == JsonValueKind.Object && element.TryGetProperty(name, out var value) && value.ValueKind == JsonValueKind.String
            ? value.GetString()!.Trim()
            : null;

    // Steam sends 64-bit ids as strings and small numbers as numbers.
    private static ulong? UInt64(JsonElement element, string name)
    {
        if (element.ValueKind != JsonValueKind.Object || !element.TryGetProperty(name, out var value))
        {
            return null;
        }

        return value.ValueKind switch
        {
            JsonValueKind.Number when value.TryGetUInt64(out var number) => number,
            JsonValueKind.String when ulong.TryParse(value.GetString(), NumberStyles.None, CultureInfo.InvariantCulture, out var number) => number,
            _ => null,
        };
    }

    private static long? Int64(JsonElement element, string name) =>
        element.ValueKind == JsonValueKind.Object && element.TryGetProperty(name, out var value) && value.ValueKind == JsonValueKind.Number && value.TryGetInt64(out var number)
            ? number
            : null;

    [GeneratedRegex("\"connect\"\\s+\"[^\"]+\"", RegexOptions.IgnoreCase)]
    private static partial Regex ConnectPattern();
}
