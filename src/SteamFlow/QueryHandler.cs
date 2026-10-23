using Flow.Launcher.Plugin;
using SteamFlow.Accounts;
using SteamFlow.Diagnostics;
using SteamFlow.Friends;
using SteamFlow.Help;
using SteamFlow.Library;
using SteamFlow.Localization;
using SteamFlow.Status;
using SteamFlow.Store;
using SteamFlow.WebApi;
using SteamFlow.Wishlist;

namespace SteamFlow;

public sealed class QueryHandler(
    IPublicAPI api,
    Translator text,
    LibraryResults library,
    StoreResults store,
    StatusResults status,
    ApiResults apiResults,
    WishlistResults wishlist,
    SwitchResults switchAccounts,
    FriendsResults friends,
    HelpResults help,
    PluginLog log)
{
    private static readonly TimeSpan SlowQuery = TimeSpan.FromSeconds(1);

    // Steam refreshes the progress of running downloads at this rate, so refreshing faster would show nothing new.
    private static readonly TimeSpan LiveRefreshInterval = TimeSpan.FromSeconds(10);

    private static readonly HashSet<string> StatusAliases = [StatusResults.Command, "statuses"];

    // The whole query has to match, so a store search for a game called "Deals" needs more words.
    private static readonly Dictionary<string, StoreCollection> CollectionAliases = new()
    {
        ["top"] = StoreCollection.TopSellers,
        ["seller"] = StoreCollection.TopSellers,
        ["sellers"] = StoreCollection.TopSellers,
        ["top seller"] = StoreCollection.TopSellers,
        ["top sellers"] = StoreCollection.TopSellers,
        ["special"] = StoreCollection.Specials,
        ["specials"] = StoreCollection.Specials,
        ["deal"] = StoreCollection.Specials,
        ["deals"] = StoreCollection.Specials,
    };

    // The first answer is returned right away; when slower details arrive, the full list is sent through publish.
    public async Task<List<Result>> QueryAsync(Query query, CancellationToken token, Action<List<Result>> publish)
    {
        var term = query.Search.Trim();
        var command = string.Join(' ', term.ToLowerInvariant().Split(' ', StringSplitOptions.RemoveEmptyEntries));

        var started = log.StartTiming();
        if (term.Length == 0)
        {
            var empty = Respond(await EmptyAsync(), EmptyAsync, token, publish);
            log.Slow("Empty query", started, SlowQuery);
            return empty;
        }

        void PublishInOrder(List<Result> results) => publish(InOwnOrder(results));
        if (await CommandAsync(query, term, command, token, PublishInOrder) is { } commandResults)
        {
            return InOwnOrder(commandResults);
        }

        var search = Respond(await SearchAsync(term, token), () => SearchAsync(term, token), token, publish);
        log.Slow("Search", started, SlowQuery, $"'{term}'");
        return search;
    }

    // Commands list items in an order of their own (current status first, friends by presence, wishlist by date),
    // which Flow would otherwise reshuffle by lifting items that were picked before. Game searches keep that boost.
    private static List<Result> InOwnOrder(List<Result> results)
    {
        foreach (var result in results)
        {
            result.AddSelectedCount = false;
        }

        return results;
    }

    private async Task<List<Result>?> CommandAsync(
        Query query,
        string term,
        string command,
        CancellationToken token,
        Action<List<Result>> publish)
    {
        if (command == HelpResults.Command)
        {
            return help.Build(query.ActionKeyword);
        }

        if (StatusAliases.Contains(command))
        {
            return await status.QueryAsync(query.ActionKeyword);
        }

        if (WishlistResults.SearchFrom(term) is { } wishlistSearch)
        {
            var wishlistQuery = await wishlist.QueryAsync(query.ActionKeyword, wishlistSearch, token);
            if (wishlistQuery.Completion is { } completion)
            {
                PublishLater(token, publish, completion);
            }

            return wishlistQuery.Results;
        }

        if (FriendsResults.SearchFrom(term) is { } friendsSearch)
        {
            var friendsQuery = await friends.QueryAsync(query.ActionKeyword, friendsSearch);
            if (friendsQuery.Completion is { } completion)
            {
                PublishLater(token, publish, completion);
            }

            return friendsQuery.Results;
        }

        if (SwitchResults.Aliases.Contains(command))
        {
            return await switchAccounts.QueryAsync();
        }

        if (ApiResults.Aliases.Contains(command))
        {
            RefreshOnReopen(apiResults.QueryAsync, token, publish);
            return await apiResults.QueryAsync();
        }

        if (CollectionAliases.TryGetValue(command, out var collection))
        {
            return await CollectionAsync(collection, token, publish);
        }

        return null;
    }

    private async Task<Answer> EmptyAsync()
    {
        var empty = await library.EmptyQueryAsync();
        return new Answer(empty.Results, empty.Completion, empty.Live);
    }

    private async Task<Answer> SearchAsync(string term, CancellationToken token)
    {
        var localTask = library.SearchAsync(term, token);
        var storeTask = store.SearchAsync(term, token);
        var local = await localTask;
        var storeSearch = await storeTask;

        async Task<List<Result>> CompleteAsync()
        {
            var localResults = local.Completion is { } localCompletion ? await localCompletion : local.Results;
            var storeResults = storeSearch.Completion is { } storeCompletion ? await storeCompletion : storeSearch.Results;
            return Merge(term, localResults, local, storeResults, storeSearch.Error);
        }

        return new Answer(
            Merge(term, local.Results, local, storeSearch.Results, storeSearch.Error),
            local.Completion is null && storeSearch.Completion is null ? null : CompleteAsync(),
            local.Live);
    }

    private List<Result> Respond(Answer answer, Func<Task<Answer>> again, CancellationToken token, Action<List<Result>> publish)
    {
        if (answer.Completion is { } completion)
        {
            PublishLater(token, publish, () => completion);
        }

        if (answer.Live)
        {
            RefreshWhileLive(again, token, publish);
        }

        return answer.Results;
    }

    // Download progress keeps moving while the window stays open on the same query, but Flow only asks again
    // when the query changes. Flow cancels the token on the next query, which ends the loop; a hidden window is
    // skipped rather than ending it, because reopening on the same query does not always ask again.
    private void RefreshWhileLive(Func<Task<Answer>> again, CancellationToken token, Action<List<Result>> publish) =>
        _ = Task.Run(async () =>
        {
            try
            {
                using var timer = new PeriodicTimer(LiveRefreshInterval);
                while (await timer.WaitForNextTickAsync(token))
                {
                    if (!api.IsMainWindowVisible())
                    {
                        continue;
                    }

                    var answer = await again();
                    var results = answer.Completion is { } completion ? await completion : answer.Results;
                    if (token.IsCancellationRequested)
                    {
                        return;
                    }

                    publish(results);
                    if (!answer.Live)
                    {
                        return;
                    }
                }
            }
            catch (OperationCanceledException)
            {
            }
            catch (Exception ex)
            {
                log.Error("Download progress refresh failed", ex);
            }
        });

    // Reopening the window on the same query shows the old results without asking again, so a menu that depends on
    // something outside Flow, like the clipboard, is rebuilt each time the window appears. The next query cancels
    // the token, which unsubscribes.
    private void RefreshOnReopen(Func<Task<List<Result>>> again, CancellationToken token, Action<List<Result>> publish)
    {
        void OnVisibilityChanged(object sender, VisibilityChangedEventArgs args)
        {
            if (!args.IsVisible || token.IsCancellationRequested)
            {
                return;
            }

            PublishLater(token, publish, again);
        }

        api.VisibilityChanged += OnVisibilityChanged;
        token.Register(() => api.VisibilityChanged -= OnVisibilityChanged);
    }

    private async Task<List<Result>> CollectionAsync(StoreCollection collection, CancellationToken token, Action<List<Result>> publish)
    {
        var label = text.Get(collection == StoreCollection.TopSellers ? "steamflow_collection_top_sellers" : "steamflow_collection_specials");
        var storeSearch = await store.CollectionAsync(collection, await library.OwnedInstalledOrHiddenAsync(), token);

        if (storeSearch.Completion is { } completion)
        {
            PublishLater(token, publish, async () => WithEmptyState(label, await completion, storeSearch.Error));
        }

        return WithEmptyState(label, storeSearch.Results, storeSearch.Error);
    }

    private void PublishLater(CancellationToken token, Action<List<Result>> publish, Func<Task<List<Result>>> complete) =>
        _ = Task.Run(async () =>
        {
            try
            {
                var results = await complete();
                if (!token.IsCancellationRequested)
                {
                    publish(results);
                }
            }
            catch (Exception ex)
            {
                // Nothing awaits this task, so a failure would otherwise vanish silently.
                log.Error("Publishing completed results failed", ex);
            }
        });

    private List<Result> Merge(
        string term,
        IEnumerable<Result> localResults,
        LocalSearch local,
        IEnumerable<StoreResult> storeResults,
        string? storeError)
    {
        var results = localResults.ToList();
        results.AddRange(storeResults
            .Where(item => !local.AppIds.Contains(item.AppId) && !local.HiddenAppIds.Contains(item.AppId))
            .Select(item => item.Result));
        return results.Count > 0 ? results : [EmptyState(term, storeError)];
    }

    private List<Result> WithEmptyState(string label, IEnumerable<StoreResult> storeResults, string? storeError)
    {
        var results = storeResults.Select(item => item.Result).ToList();
        return results.Count > 0 ? results : [EmptyState(label, storeError)];
    }

    private Result EmptyState(string term, string? error) => new()
    {
        Title = error is null ? text.Format("steamflow_no_games_found", term) : text.Format("steamflow_search_failed", term),
        SubTitle = error ?? text.Get("steamflow_try_different_search"),
        IcoPath = Icons.Steam,
    };
}

// Completion rebuilds the results once slower details arrive; Live asks for them to be refreshed while open.
internal sealed record Answer(List<Result> Results, Task<List<Result>>? Completion, bool Live);
