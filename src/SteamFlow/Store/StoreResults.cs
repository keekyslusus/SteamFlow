using System.Text.Json;
using Flow.Launcher.Plugin;
using SteamFlow.Diagnostics;
using SteamFlow.Library;
using SteamFlow.Localization;
using SteamFlow.Settings;
using SteamFlow.Steam;
using SteamFlow.WebApi;

namespace SteamFlow.Store;

public sealed record StoreResult(int AppId, Result Result);

// Completion is set when some details were still loading; it rebuilds the results once everything arrived.
public sealed record StoreSearch(
    IReadOnlyList<StoreResult> Results,
    string? Error,
    Task<IReadOnlyList<StoreResult>>? Completion = null);

public sealed class StoreResults(
    Translator text,
    PluginSettings settings,
    StoreCatalog catalog,
    StoreImages images,
    StoreSubtitles subtitles,
    GameContextMenu gameMenu,
    OwnedGamesService ownedGames,
    ApiAchievements apiAchievements,
    SteamClient steam,
    PluginLog log)
{
    private const int MaxSearchResults = 5;
    private const int MaxCollectionResults = 10;
    private const int TopScore = 100;

    // Results show after this even if details, metrics or capsules are still loading; they are pushed when ready.
    private static readonly TimeSpan InitialDeadline = TimeSpan.FromMilliseconds(500);

    // Featured lists include hardware (Steam Deck, Steam Machine) that only app details can tell apart from games.
    private static readonly TimeSpan CollectionDetailsDeadline = TimeSpan.FromSeconds(2);

    public async Task<StoreSearch> SearchAsync(string term, CancellationToken token)
    {
        IReadOnlyList<StoreSearchItem> found;
        try
        {
            found = await catalog.SearchAsync(term).WaitAsync(token);
        }
        catch (Exception ex) when (!token.IsCancellationRequested && ex is HttpRequestException or OperationCanceledException or JsonException)
        {
            log.Warn("Store search failed", ex, $"'{term}'");
            return new StoreSearch([], SearchErrorText(ex));
        }

        // Steam's own order decides which five are shown; filtering happens afterwards, like the Python plugin.
        var blacklist = settings.BlacklistedAppIdSet();
        var items = found
            .Take(MaxSearchResults)
            .Where(item => !blacklist.Contains(item.AppId))
            .DistinctBy(item => item.AppId)
            .ToList();
        return await BuildAsync(items, requireDetails: false, token);
    }

    // For lists that already know their apps, such as the wishlist; suffixes are appended to each subtitle.
    public Task<StoreSearch> ListAsync(List<StoreSearchItem> items, IReadOnlyDictionary<int, string> suffixes, CancellationToken token) =>
        BuildAsync(items, requireDetails: false, token, suffixes);

    public async Task<StoreSearch> CollectionAsync(StoreCollection collection, IReadOnlySet<int> excluded, CancellationToken token)
    {
        FeaturedCollections? featured;
        try
        {
            featured = await catalog.FeaturedAsync().WaitAsync(token);
        }
        catch (Exception ex) when (!token.IsCancellationRequested && ex is HttpRequestException or OperationCanceledException or JsonException)
        {
            log.Warn("Featured collections failed", ex, collection.ToString());
            return new StoreSearch([], SearchErrorText(ex));
        }

        var blacklist = settings.BlacklistedAppIdSet();
        var items = (featured?.Get(collection) ?? [])
            .Where(item => !blacklist.Contains(item.AppId) && !excluded.Contains(item.AppId))
            .DistinctBy(item => item.AppId)
            .ToList();
        return await BuildAsync(items, requireDetails: true, token);
    }

    private async Task<StoreSearch> BuildAsync(
        List<StoreSearchItem> items,
        bool requireDetails,
        CancellationToken token,
        IReadOnlyDictionary<int, string>? suffixes = null)
    {
        suffixes ??= new Dictionary<int, string>();
        if (requireDetails)
        {
            items = await WithDetailsAsync(items, token);
        }

        if (items.Count == 0)
        {
            return new StoreSearch([], null);
        }

        var owned = await ownedGames.CurrentAsync();
        var lookups = StartLookups(items, owned);
        var all = lookups.WhenAll();
        await Task.WhenAny(all, Task.Delay(InitialDeadline, token));
        token.ThrowIfCancellationRequested();

        var completion = all.IsCompleted ? null : CompleteAsync(items, lookups, owned, suffixes, all);
        return new StoreSearch(Build(items, lookups, owned, suffixes), null, completion);
    }

    private async Task<List<StoreSearchItem>> WithDetailsAsync(List<StoreSearchItem> items, CancellationToken token)
    {
        var details = items.ToDictionary(item => item.AppId, item => catalog.DetailsAsync(item.AppId));
        await Task.WhenAny(Task.WhenAll(details.Values), Task.Delay(CollectionDetailsDeadline, token));
        token.ThrowIfCancellationRequested();

        return items
            .Where(item => Completed(details[item.AppId]) is { Type: not "hardware" })
            .Take(MaxCollectionResults)
            .ToList();
    }

    private Lookups StartLookups(List<StoreSearchItem> items, OwnedView owned)
    {
        var metricItems = items.Where(item => StoreSubtitles.SupportsLiveMetrics(item, null)).ToList();
        return new Lookups(
            items.ToDictionary(item => item.AppId, item => catalog.DetailsAsync(item.AppId)),
            settings.ShowPrices
                ? catalog.PricesAsync([.. items.Select(item => item.AppId)])
                : Task.FromResult<IReadOnlyDictionary<int, StorePrice>>(new Dictionary<int, StorePrice>()),
            images.Resolve(items),
            settings.ShowPositiveReviews
                ? metricItems.ToDictionary(item => item.AppId, item => catalog.ReviewsAsync(item.AppId))
                : [],
            settings.ShowPlayerCount
                ? metricItems.ToDictionary(item => item.AppId, item => catalog.PlayersAsync(item.AppId))
                : [],
            settings.ShowAchievements
                ? items.Where(item => owned.IsOwned(item.AppId)).ToDictionary(item => item.AppId, item => apiAchievements.ProgressAsync(item.AppId))
                : []);
    }

    private async Task<IReadOnlyList<StoreResult>> CompleteAsync(
        List<StoreSearchItem> items,
        Lookups lookups,
        OwnedView owned,
        IReadOnlyDictionary<int, string> suffixes,
        Task all)
    {
        await all;
        return Build(items, lookups, owned, suffixes);
    }

    private List<StoreResult> Build(List<StoreSearchItem> items, Lookups lookups, OwnedView owned, IReadOnlyDictionary<int, string> suffixes)
    {
        var prices = Completed(lookups.Prices) ?? new Dictionary<int, StorePrice>();
        return items
            .Select((item, index) => new StoreResult(item.AppId, Build(
                new StoreItemData(
                    item,
                    Completed(lookups.Details[item.AppId]),
                    prices.GetValueOrDefault(item.AppId),
                    lookups.Reviews.TryGetValue(item.AppId, out var review) ? Completed(review) : null,
                    lookups.Players.TryGetValue(item.AppId, out var count) ? Completed(count) : null,
                    Completed(lookups.Images[item.AppId]),
                    owned.IsOwned(item.AppId),
                    owned.PlaytimeMinutes(item.AppId),
                    lookups.Achievements.TryGetValue(item.AppId, out var achievements) ? Completed(achievements) : null,
                    suffixes.GetValueOrDefault(item.AppId)),
                TopScore - index)))
            .ToList();
    }

    private Result Build(StoreItemData data, int score)
    {
        var name = data.Details?.Name is { Length: > 0 } detailsName ? detailsName : data.Item.Name;
        var target = new GameMenuTarget(
            data.Item.AppId,
            name,
            "",
            data.Details?.Type,
            data.Details?.ComingSoon ?? false,
            IsOwned: data.IsOwned,
            Wishlistable: data.Details?.Type is null or "" or "game",
            Purchasable: data.Details?.Type is null or "" or "game" && data.Details?.ComingSoon != true && data.Details?.IsFree != true,
            Developers: data.Details?.Developers,
            Publishers: data.Details?.Publishers);
        return new Result
        {
            Title = data.IsOwned ? text.Format("steamflow_store_title_owned", name) : name,
            SubTitle = subtitles.Build(data),
            IcoPath = data.ImagePath ?? Icons.Steam,
            Score = score,
            ContextData = new ResultMenu(() => gameMenu.Build(target)),
            Action = _ =>
            {
                if (data.IsOwned)
                {
                    steam.OpenLibraryDetails(data.Item.AppId);
                }
                else
                {
                    steam.OpenStorePage(data.Item.AppId);
                }

                return true;
            },
        };
    }

    private string SearchErrorText(Exception ex) => ex switch
    {
        OperationCanceledException => text.Get("steamflow_store_search_timeout"),
        HttpRequestException => text.Get("steamflow_store_search_http_error"),
        _ => text.Get("steamflow_store_search_failed"),
    };

    private static T? Completed<T>(Task<T> task) where T : class? =>
        task.IsCompletedSuccessfully ? task.Result : null;

    private sealed record Lookups(
        Dictionary<int, Task<AppDetails?>> Details,
        Task<IReadOnlyDictionary<int, StorePrice>> Prices,
        IReadOnlyDictionary<int, Task<string?>> Images,
        Dictionary<int, Task<ReviewSummary?>> Reviews,
        Dictionary<int, Task<PlayerCount?>> Players,
        Dictionary<int, Task<AchievementProgress?>> Achievements)
    {
        public Task WhenAll() =>
            Task.WhenAll(Details.Values.Cast<Task>()
                .Append(Prices)
                .Concat(Images.Values)
                .Concat(Reviews.Values)
                .Concat(Players.Values)
                .Concat(Achievements.Values));
    }
}
