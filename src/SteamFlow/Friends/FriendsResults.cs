using System.Globalization;
using Flow.Launcher.Plugin;
using SteamFlow.Localization;
using SteamFlow.Steam;
using SteamFlow.WebApi;

namespace SteamFlow.Friends;

// Completion rebuilds the list once the statuses of friends in game that were not cached yet arrived.
public sealed record FriendsQuery(List<Result> Results, Func<Task<List<Result>>>? Completion = null);

public sealed class FriendsResults(
    IPublicAPI api,
    Translator text,
    FriendsService friends,
    FriendPresence presence,
    FriendMenu menu,
    SteamClient steam,
    TimeProvider time)
{
    public const string Command = "friends";

    private const int MaxResults = 15;
    private const int TopScore = 20500;

    private static readonly string[] Aliases = ["friends", "friend"];

    // Returns the search text after the command, or null when the query is not a friends query.
    public static string? SearchFrom(string term)
    {
        var trimmed = term.Trim();
        foreach (var alias in Aliases)
        {
            if (trimmed.Equals(alias, StringComparison.OrdinalIgnoreCase))
            {
                return "";
            }

            if (trimmed.StartsWith(alias + " ", StringComparison.OrdinalIgnoreCase))
            {
                return trimmed[(alias.Length + 1)..].Trim();
            }
        }

        return null;
    }

    public async Task<FriendsQuery> QueryAsync(string actionKeyword, string search)
    {
        var view = await friends.CurrentAsync();
        if (view.Unavailable != ApiUnavailable.None)
        {
            return new FriendsQuery([Unavailable(view.Unavailable, actionKeyword)]);
        }

        if (view.Problem != FriendsProblem.None)
        {
            return new FriendsQuery([Message(text.Get("steamflow_friends_unavailable"),
                text.Get(view.Problem == FriendsProblem.Private ? "steamflow_friends_private" : "steamflow_friends_request_failed"))]);
        }

        var matches = Sort(view.Friends, search, view.Favorites);
        if (matches.Count == 0)
        {
            return new FriendsQuery([Message(
                search.Length > 0 ? text.Format("steamflow_friends_no_matches", search) : text.Get("steamflow_friends_empty"),
                text.Get("steamflow_friends_empty_subtitle"))]);
        }

        var shown = matches.Take(MaxResults).ToList();
        var statuses = presence.Load(shown);
        List<Result> BuildAll() => shown
            .Select((friend, index) => Build(
                friend,
                view.Favorites.Contains(friend.AccountId) && friend.Presence != Presence.Offline,
                TopScore - index,
                statuses.TryGetValue(friend.SteamId64, out var status) && status.IsCompletedSuccessfully ? status.Result : null))
            .ToList();

        // The list never waits for statuses that are not cached yet; they arrive with a second publish.
        return new FriendsQuery(
            BuildAll(),
            statuses.Values.All(status => status.IsCompleted) ? null : async () =>
            {
                await Task.WhenAll(statuses.Values);
                return BuildAll();
            });
    }

    // Ranks matches on the name first, then the game, then the id; favorites lead within a rank unless offline.
    public static List<Friend> Sort(IEnumerable<Friend> friends, string search, IReadOnlySet<uint> favorites)
    {
        var query = search.Trim();
        int Rank(Friend friend)
        {
            if (query.Length == 0)
            {
                return 0;
            }

            var comparison = StringComparison.CurrentCultureIgnoreCase;
            return friend.Name.Equals(query, comparison) ? 0
                : friend.Name.StartsWith(query, comparison) ? 1
                : friend.Name.Contains(query, comparison) ? 2
                : friend.GameName.StartsWith(query, comparison) ? 3
                : friend.GameName.Contains(query, comparison) ? 4
                : friend.SteamId64.ToString(CultureInfo.InvariantCulture).Contains(query, StringComparison.Ordinal) ? 5
                : 6;
        }

        return friends
            .Select(friend => (Friend: friend, Rank: Rank(friend)))
            .Where(entry => entry.Rank < 6)
            .OrderBy(entry => entry.Rank)
            .ThenBy(entry => favorites.Contains(entry.Friend.AccountId) && entry.Friend.Presence != Presence.Offline ? 0 : 1)
            .ThenBy(entry => entry.Friend.Presence)
            .ThenBy(entry => entry.Friend.Name.Length > 0 ? entry.Friend.Name : entry.Friend.SteamId64.ToString(CultureInfo.InvariantCulture), StringComparer.CurrentCultureIgnoreCase)
            .Select(entry => entry.Friend)
            .ToList();
    }

    private Result Build(Friend friend, bool favorite, int score, string? status)
    {
        var subtitle = friend.Presence == Presence.Playing && friend.GameName.Length > 0
            ? text.Format("steamflow_profile_playing", friend.GameName)
            : text.Get(string.Create(CultureInfo.InvariantCulture, $"steamflow_persona_state_{(friend.PersonaState is >= 0 and <= 7 ? friend.PersonaState : 0)}"));
        if (friend.Presence == Presence.Playing && status is { Length: > 0 })
        {
            subtitle = text.Format("steamflow_friends_rich_presence", subtitle, status);
        }

        if (friend.Presence == Presence.Offline && friend.LastLogoff is { } lastLogoff)
        {
            subtitle = text.Format("steamflow_friends_last_seen", subtitle, LastSeen(lastLogoff));
        }

        if (favorite)
        {
            subtitle = text.Format("steamflow_friends_favorite", subtitle);
        }

        return new Result
        {
            Title = friend.Name.Length > 0 ? friend.Name : friend.SteamId64.ToString(CultureInfo.InvariantCulture),
            SubTitle = subtitle,
            // Steam avatars are square, so Flow can draw them straight from the URL without distortion.
            IcoPath = friend.AvatarUrl ?? (friend.Presence == Presence.Offline ? Icons.Offline : Icons.Online),
            Score = score,
            ContextData = new ResultMenu(() => menu.Build(friend)),
            Action = _ =>
            {
                steam.OpenChat(friend.SteamId64);
                return true;
            },
        };
    }

    private string LastSeen(DateTimeOffset lastLogoff)
    {
        var minutes = (int)Math.Max(0, (time.GetUtcNow() - lastLogoff).TotalMinutes);
        if (minutes < 60)
        {
            return text.Format("steamflow_minutes_ago", minutes);
        }

        if (minutes < 24 * 60)
        {
            return text.Format("steamflow_hours_ago", minutes / 60);
        }

        if (minutes < 7 * 24 * 60)
        {
            return text.Format("steamflow_days_short_ago", minutes / (24 * 60));
        }

        var seen = lastLogoff.ToLocalTime().DateTime;
        return seen.Year == time.GetLocalNow().Year
            ? text.Format("steamflow_date_short", seen)
            : text.Format("steamflow_date_short_with_year", seen);
    }

    private Result Unavailable(ApiUnavailable reason, string actionKeyword)
    {
        var apiQuery = PluginQuery.Build(actionKeyword, ApiResults.Command);
        var result = Message(text.Get("steamflow_friends_unavailable"), reason switch
        {
            ApiUnavailable.NoKey => text.Format("steamflow_friends_unavailable_no_key", apiQuery),
            _ => text.Get("steamflow_friends_unavailable_no_account"),
        });
        if (reason == ApiUnavailable.NoKey)
        {
            result.Action = _ =>
            {
                api.ChangeQuery(apiQuery, requery: true);
                return false;
            };
        }

        return result;
    }

    private static Result Message(string title, string subtitle) => new()
    {
        Title = title,
        SubTitle = subtitle,
        IcoPath = Icons.Friends,
        Score = TopScore,
    };
}
