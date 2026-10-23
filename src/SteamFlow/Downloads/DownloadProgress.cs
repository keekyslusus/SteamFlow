using SteamFlow.Caching;
using SteamFlow.Library;
using SteamFlow.Session;
using SteamFlow.Steam;
using SteamFlow.Store;

namespace SteamFlow.Downloads;

// Late is set when the request outlived the query's deadline; it never fails.
public sealed record ProgressLookup(IReadOnlyDictionary<int, AppProgress> Known, Task<IReadOnlyDictionary<int, AppProgress>>? Late);

// Progress is decoration on top of the log-based status: it never decides whether a game is updating,
// and a failed request only means no percentage is shown.
public sealed class DownloadProgress(ClientCommApi api, SteamSessionTokens tokens, StoreRequests requests, LocalLibrary library, TimeProvider time)
{
    // Small updates finish before a percentage would be useful, so they never cause a network request.
    public const long MinimumBytes = 1L << 30;

    private static readonly TimeSpan Deadline = TimeSpan.FromMilliseconds(400);
    private static readonly IReadOnlyDictionary<int, AppProgress> Nothing = new Dictionary<int, AppProgress>();

    // Steam's own answer asks clients to refetch updating apps every 10 seconds.
    private readonly TimedCache<ulong, IReadOnlyDictionary<int, AppProgress>> progress =
        new(time, TimeSpan.FromSeconds(10), TimeSpan.FromSeconds(10));

    public static bool Wanted(DownloadView view, int appId, DownloadStatus status) =>
        status == DownloadStatus.Updating && view.Logged.GetValueOrDefault(appId)?.DownloadBytes >= MinimumBytes;

    public async Task<ProgressLookup> ForAsync(bool anyWanted, CancellationToken token)
    {
        if (!anyWanted || (await library.GetAsync()).ActiveAccountId is not { } accountId)
        {
            return new ProgressLookup(Nothing, null);
        }

        var steamId64 = SteamAccount.ToSteamId64(accountId);
        var pending = progress.GetAsync(steamId64, () => FetchAsync(steamId64));
        await Task.WhenAny(pending, Task.Delay(Deadline, token));
        if (pending.IsCompleted)
        {
            return new ProgressLookup((pending.IsCompletedSuccessfully ? pending.Result : null) ?? progress.Peek(steamId64) ?? Nothing, null);
        }

        // Right after a download starts nothing is cached and the two round trips outlast the deadline;
        // the caller pushes the results again once this finishes instead of waiting for the next query.
        return new ProgressLookup(
            progress.Peek(steamId64) ?? Nothing,
            pending.ContinueWith(task => (task.IsCompletedSuccessfully ? task.Result : null) ?? Nothing, TaskScheduler.Default));
    }

    // The client instance changes with every Steam start, so it is looked up again on each refresh.
    private async Task<IReadOnlyDictionary<int, AppProgress>?> FetchAsync(ulong steamId64) =>
        await tokens.GetWithoutSteamAsync(steamId64) is { } token
            ? await requests.Quietly("Download progress request", async cancel =>
                (await api.ClientInstanceAsync(token.Value, cancel)).Instance is { } instance
                    ? await api.ProgressAsync(token.Value, instance, cancel)
                    : null)
            : null;
}
