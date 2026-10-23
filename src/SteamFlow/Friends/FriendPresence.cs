using SteamFlow.Caching;
using SteamFlow.Localization;
using SteamFlow.Store;

namespace SteamFlow.Friends;

// What a friend is doing in their game ("Turbo: Lvl 25 Wraith King"), one mini profile request per friend in game.
public sealed class FriendPresence
{
    private readonly FriendsApi api;
    private readonly StoreRequests requests;
    private readonly Translator text;

    // Keyed by the game too, so a friend who switches games never shows the previous game's status.
    private readonly TimedCache<(uint AccountId, int GameId, string Language), string> statuses;

    // A friends list can have many people in game at once, and steamcommunity.com limits requests per IP.
    private readonly SemaphoreSlim slots = new(4);

    public FriendPresence(FriendsApi api, StoreRequests requests, Translator text, TimeProvider time)
    {
        this.api = api;
        this.requests = requests;
        this.text = text;
        statuses = new(time, TimeSpan.FromMinutes(1), TimeSpan.FromMinutes(1));
    }

    // Each task completes at once when a status is cached, even a stale one being refreshed in the background.
    public IReadOnlyDictionary<ulong, Task<string?>> Load(IEnumerable<Friend> friends)
    {
        var language = text.Get("steamflow_steam_language");
        return friends
            .Where(friend => friend.Presence == Presence.Playing && friend.GameId is not null)
            .DistinctBy(friend => friend.SteamId64)
            .ToDictionary(
                friend => friend.SteamId64,
                friend => statuses.GetAsync((friend.AccountId, friend.GameId!.Value, language), () => FetchAsync(friend.AccountId, language)));
    }

    private async Task<string?> FetchAsync(uint accountId, string language)
    {
        await slots.WaitAsync();
        try
        {
            return await requests.Quietly("Rich presence request", token => api.RichPresenceAsync(accountId, language, token), $"account {accountId}");
        }
        finally
        {
            slots.Release();
        }
    }
}
