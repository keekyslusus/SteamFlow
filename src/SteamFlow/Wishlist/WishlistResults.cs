using Flow.Launcher.Plugin;
using SteamFlow.Localization;
using SteamFlow.Store;
using SteamFlow.WebApi;

namespace SteamFlow.Wishlist;

// Completion is set while app details are still loading; it rebuilds the list once every name is known.
public sealed record WishlistQuery(List<Result> Results, Func<Task<List<Result>>>? Completion);

public sealed class WishlistResults(
    IPublicAPI api,
    Translator text,
    WishlistService wishlist,
    StoreCatalog catalog,
    StoreResults store,
    TimeProvider time)
{
    public const string Command = "wishlist";

    private const int MaxResults = 15;
    private const int MessageScore = 20500;
    private const int StatusScore = 20501;

    private static readonly TimeSpan DetailsDeadline = TimeSpan.FromMilliseconds(700);

    // Returns the search text after the command, or null when the query is not a wishlist query.
    // Any word starting with "wishl" counts, so a typo in the rest of the word still opens the wishlist.
    public static string? SearchFrom(string term)
    {
        var parts = term.Trim().Split(' ', 2, StringSplitOptions.RemoveEmptyEntries);
        if (parts.Length > 0 && parts[0].StartsWith("wishl", StringComparison.OrdinalIgnoreCase))
        {
            return parts.Length > 1 ? parts[1].Trim() : "";
        }

        var lowered = term.Trim();
        return lowered.Equals("wish list", StringComparison.OrdinalIgnoreCase) ? ""
            : lowered.StartsWith("wish list ", StringComparison.OrdinalIgnoreCase) ? lowered["wish list ".Length..].Trim()
            : null;
    }

    public async Task<WishlistQuery> QueryAsync(string actionKeyword, string search, CancellationToken token)
    {
        var view = await wishlist.CurrentAsync();
        if (view.Unavailable != ApiUnavailable.None)
        {
            return new WishlistQuery([Unavailable(view.Unavailable, actionKeyword)], null);
        }

        if (view.Items.Count == 0)
        {
            return new WishlistQuery([Message(text.Get("steamflow_wishlist_title"), text.Get("steamflow_wishlist_empty_account"))], null);
        }

        var items = view.Items.OrderByDescending(item => item.DateAdded).ThenBy(item => item.AppId).ToList();
        var details = items.ToDictionary(item => item.AppId, item => catalog.DetailsAsync(item.AppId));
        var allDetails = Task.WhenAll(details.Values);
        await Task.WhenAny(allDetails, Task.Delay(DetailsDeadline, token));
        token.ThrowIfCancellationRequested();

        var first = await BuildAsync(items, details, search, token);
        if (allDetails.IsCompleted)
        {
            return new WishlistQuery(first.Results, first.Completion);
        }

        return new WishlistQuery(first.Results, async () =>
        {
            await allDetails;
            var full = await BuildAsync(items, details, search, token);
            return full.Completion is { } completion ? await completion() : full.Results;
        });
    }

    private async Task<WishlistQuery> BuildAsync(
        List<WishlistItem> items,
        Dictionary<int, Task<AppDetails?>> details,
        string search,
        CancellationToken token)
    {
        var loaded = items
            .Select(item => (Item: item, Details: details[item.AppId].IsCompletedSuccessfully ? details[item.AppId].Result : null))
            .Where(entry => entry.Details is { Name.Length: > 0 })
            .ToList();
        var matching = string.IsNullOrWhiteSpace(search)
            ? loaded
            : loaded.Where(entry => api.FuzzySearch(search, entry.Details!.Name).IsSearchPrecisionScoreMet()).ToList();
        var visible = matching.Take(MaxResults).ToList();

        var storeSearch = await store.ListAsync(
            visible.Select(entry => new StoreSearchItem(
                entry.Item.AppId,
                "app",
                entry.Details!.Name,
                entry.Details.CapsuleUrl)).ToList(),
            visible.ToDictionary(entry => entry.Item.AppId, entry => text.Format("steamflow_wishlist_added_on", AddedText(entry.Item.DateAdded))),
            token);

        var results = new List<Result>();
        var stillLoading = loaded.Count < items.Count;
        if (stillLoading)
        {
            results.Add(Status(loaded.Count, items.Count, search, matching.Count));
        }

        results.AddRange(storeSearch.Results.Select(result => result.Result));
        if (results.Count == 0)
        {
            results.Add(Message(text.Format("steamflow_wishlist_no_matches", search), text.Get("steamflow_wishlist_no_matches_subtitle")));
        }

        Func<Task<List<Result>>>? completion = storeSearch.Completion is { } pending
            ? async () =>
            {
                var completed = (await pending).Select(result => result.Result).ToList();
                return stillLoading ? [Status(loaded.Count, items.Count, search, matching.Count), .. completed] : completed;
            }
            : null;
        return new WishlistQuery(results, completion);
    }

    private string AddedText(DateTimeOffset added)
    {
        var addedOn = added.ToLocalTime().DateTime;
        var now = time.GetLocalNow().DateTime;
        var daysAgo = (now.Date - addedOn.Date).Days;
        return daysAgo switch
        {
            0 => text.Get("steamflow_today"),
            1 => text.Get("steamflow_yesterday"),
            >= 2 and <= 7 => text.Format("steamflow_days_short_ago", daysAgo),
            _ when addedOn.Year == now.Year => text.Format("steamflow_date_short", addedOn),
            _ => text.Format("steamflow_date_short_with_year", addedOn),
        };
    }

    private Result Status(int loaded, int total, string search, int matching)
    {
        var subtitle = text.Format("steamflow_wishlist_loaded", loaded, total);
        if (!string.IsNullOrWhiteSpace(search))
        {
            subtitle = text.Format("steamflow_wishlist_loaded_matches", subtitle, matching);
        }

        return new Result
        {
            Title = string.IsNullOrWhiteSpace(search)
                ? text.Get("steamflow_wishlist_syncing")
                : text.Format("steamflow_wishlist_syncing_search", search),
            SubTitle = subtitle,
            IcoPath = Icons.Owned,
            Score = StatusScore,
        };
    }

    private Result Unavailable(ApiUnavailable reason, string actionKeyword)
    {
        var apiQuery = PluginQuery.Build(actionKeyword, ApiResults.Command);
        var result = Message(text.Get("steamflow_wishlist_unavailable"), reason switch
        {
            ApiUnavailable.NoKey => text.Format("steamflow_wishlist_unavailable_no_key", apiQuery),
            _ => text.Get("steamflow_wishlist_unavailable_no_account"),
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
        IcoPath = Icons.Owned,
        Score = MessageScore,
    };
}
