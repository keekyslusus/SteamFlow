using System.Text.Json;
using SteamFlow.Caching;
using SteamFlow.Diagnostics;
using SteamFlow.Session;
using SteamFlow.Store;
using SteamFlow.WebApi;

namespace SteamFlow.Friends;

public enum FriendsProblem
{
    None,
    Private,
    RequestFailed,
}

public sealed record FriendsView(ApiUnavailable Unavailable, FriendsProblem Problem, IReadOnlyList<Friend> Friends, IReadOnlySet<uint> Favorites);

public sealed record JoinCandidate(ulong SteamId64, string Name, int AppId, ulong? LobbyId);

public sealed class FriendsService
{
    private static readonly TimeSpan FavoritesDeadline = TimeSpan.FromMilliseconds(800);

    private readonly ApiAccess access;
    private readonly FriendsApi api;
    private readonly SteamSessionTokens tokens;
    private readonly StoreRequests requests;
    private readonly PluginLog log;
    private readonly TimedCache<ulong, FriendList> lists;
    private readonly TimedCache<ulong, IReadOnlySet<uint>> favorites;
    private readonly TimedCache<ulong, IReadOnlyDictionary<ulong, JoinDetails>> joinDetails;
    private readonly Lock gate = new();
    private ulong? lastOwner;

    public FriendsService(
        ApiAccess access,
        FriendsApi api,
        SteamSessionTokens tokens,
        StoreRequests requests,
        PluginLog log,
        TimeProvider time)
    {
        this.access = access;
        this.api = api;
        this.tokens = tokens;
        this.requests = requests;
        this.log = log;
        // Presence changes by the minute; a short lifetime keeps "playing" accurate without a request per keystroke.
        lists = new(time, TimeSpan.FromSeconds(10), TimeSpan.FromMinutes(1));
        favorites = new(time, TimeSpan.FromMinutes(1), TimeSpan.FromMinutes(5));
        joinDetails = new(time, TimeSpan.FromSeconds(30), TimeSpan.FromMinutes(1));
    }

    public async Task<FriendsView> CurrentAsync()
    {
        var state = await access.StateAsync();
        if (state.Bound is not { } bound)
        {
            return new FriendsView(state.Reason, FriendsProblem.None, [], new HashSet<uint>());
        }

        Remember(bound.SteamId64);
        var list = await lists.GetAsync(bound.SteamId64, () => FetchAsync(bound));
        if (list is null || list.Problem != FriendsProblem.None)
        {
            return new FriendsView(ApiUnavailable.None, list?.Problem ?? FriendsProblem.RequestFailed, [], new HashSet<uint>());
        }

        var favoriteIds = favorites.GetAsync(bound.SteamId64, () => FetchFavoritesAsync(bound.SteamId64));
        await Task.WhenAny(favoriteIds, Task.Delay(FavoritesDeadline));
        PrefetchJoinDetails(bound.SteamId64, list.Friends);
        return new FriendsView(
            ApiUnavailable.None,
            FriendsProblem.None,
            list.Friends,
            favoriteIds.IsCompletedSuccessfully ? favoriteIds.Result ?? new HashSet<uint>() : new HashSet<uint>());
    }

    // The empty query never waits for the network: it uses the last list and refreshes it for next time.
    public async Task<IReadOnlyDictionary<int, IReadOnlyList<string>>> PlayingByAppAsync()
    {
        if (await access.CurrentAsync() is not { } bound)
        {
            return new Dictionary<int, IReadOnlyList<string>>();
        }

        Remember(bound.SteamId64);
        var list = lists.GetAsync(bound.SteamId64, () => FetchAsync(bound));
        var friends = list.IsCompletedSuccessfully ? list.Result?.Friends ?? [] : lists.Peek(bound.SteamId64)?.Friends ?? [];
        PrefetchJoinDetails(bound.SteamId64, friends);
        return friends
            .Where(friend => friend.GameId is not null)
            .GroupBy(friend => friend.GameId!.Value)
            .ToDictionary(
                group => group.Key,
                group => (IReadOnlyList<string>)group.Select(friend => friend.Name).Order(StringComparer.CurrentCultureIgnoreCase).ToList());
    }

    // Menus are built synchronously, so they combine the cached friend list with cached private join details.
    public IReadOnlyList<JoinCandidate> CachedJoinCandidates(int appId, ulong? onlyFriend = null)
    {
        ulong? owner;
        lock (gate)
        {
            owner = lastOwner;
        }

        if (owner is not { } ownerId || lists.Peek(ownerId)?.Friends is not { } friends)
        {
            return [];
        }

        return Candidates(friends, joinDetails.Peek(ownerId), appId, onlyFriend);
    }

    // A friend's lobby can close between showing the menu and clicking it, so joining checks again first.
    public async Task<JoinCandidate?> ConfirmJoinAsync(JoinCandidate candidate)
    {
        if (await access.CurrentAsync() is not { } bound)
        {
            return null;
        }

        var friends = (await FetchAsync(bound))?.Friends ?? [];
        var details = await FetchJoinDetailsAsync(bound.SteamId64, friends.Where(friend => friend.GameId is not null).Select(friend => friend.SteamId64).ToList());
        if (details is not null)
        {
            joinDetails.Set(bound.SteamId64, details);
        }

        return Candidates(friends, details, candidate.AppId, candidate.SteamId64).FirstOrDefault();
    }

    public static IReadOnlyList<JoinCandidate> Candidates(
        IEnumerable<Friend> friends,
        IReadOnlyDictionary<ulong, JoinDetails>? details,
        int appId,
        ulong? onlyFriend)
    {
        var candidates = new List<JoinCandidate>();
        foreach (var friend in friends)
        {
            if (friend.GameId != appId || (onlyFriend is { } only && friend.SteamId64 != only))
            {
                continue;
            }

            // Public lobby or server data is enough; otherwise the friend's private rich presence decides.
            if (friend.LobbyId is not null || friend.HasServer)
            {
                candidates.Add(new JoinCandidate(friend.SteamId64, friend.Name, appId, friend.LobbyId));
            }
            else if (details?.GetValueOrDefault(friend.SteamId64) is { Joinable: true } detail && detail.AppId == appId)
            {
                candidates.Add(new JoinCandidate(friend.SteamId64, friend.Name, appId, detail.LobbyId));
            }
        }

        return [.. candidates.OrderBy(candidate => candidate.Name, StringComparer.CurrentCultureIgnoreCase)];
    }

    private void Remember(ulong steamId64)
    {
        lock (gate)
        {
            lastOwner = steamId64;
        }
    }

    private void PrefetchJoinDetails(ulong owner, IReadOnlyList<Friend> friends)
    {
        var playing = friends.Where(friend => friend.GameId is not null && friend.LobbyId is null && !friend.HasServer).Select(friend => friend.SteamId64).ToList();
        if (playing.Count > 0)
        {
            _ = joinDetails.GetAsync(owner, () => FetchJoinDetailsAsync(owner, playing));
        }
    }

    private async Task<FriendList?> FetchAsync(BoundKey bound)
    {
        try
        {
            using var timeout = new CancellationTokenSource(StoreRequests.Timeout);
            return new FriendList(await api.FriendsAsync(bound.Key, bound.SteamId64, timeout.Token), FriendsProblem.None);
        }
        catch (FriendsListUnavailableException)
        {
            return new FriendList([], FriendsProblem.Private);
        }
        catch (Exception ex) when (ex is HttpRequestException or OperationCanceledException or JsonException)
        {
            log.Warn("Friends list request failed", ex);
            return null;
        }
    }

    private async Task<IReadOnlySet<uint>?> FetchFavoritesAsync(ulong owner) =>
        await tokens.GetWithoutSteamAsync(owner) is { } token
            ? await requests.Quietly("Friend favorites request", cancel => api.FavoritesAsync(token.Value, cancel))
            : null;

    private async Task<IReadOnlyDictionary<ulong, JoinDetails>?> FetchJoinDetailsAsync(ulong owner, IReadOnlyList<ulong> friendIds) =>
        friendIds.Count > 0 && await tokens.GetWithoutSteamAsync(owner) is { } token
            ? await requests.Quietly("Join details request", cancel => api.JoinDetailsAsync(token.Value, friendIds, cancel))
            : null;

    private sealed record FriendList(IReadOnlyList<Friend> Friends, FriendsProblem Problem);
}
