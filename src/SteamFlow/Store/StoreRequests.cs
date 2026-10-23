using System.Text.Json;
using SteamFlow.Diagnostics;

namespace SteamFlow.Store;

public sealed class StoreRequests(PluginLog log)
{
    public static readonly TimeSpan Timeout = TimeSpan.FromSeconds(3);

    private static readonly TimeSpan SlowAfter = TimeSpan.FromSeconds(1.5);

    // Store extras are decoration: a failed or slow request leaves the value out instead of failing the query.
    // `what` names the request in the log; `detail` says which one, e.g. the app.
    public async Task<T?> Quietly<T>(string what, Func<CancellationToken, Task<T>> request, string? detail = null) where T : class?
    {
        var started = log.StartTiming();
        try
        {
            using var timeout = new CancellationTokenSource(Timeout);
            var value = await request(timeout.Token);
            log.Slow(what, started, SlowAfter, detail);
            return value;
        }
        catch (Exception ex) when (ex is HttpRequestException or OperationCanceledException or JsonException)
        {
            log.Warn(what + " failed", ex, detail);
            return null;
        }
    }
}
