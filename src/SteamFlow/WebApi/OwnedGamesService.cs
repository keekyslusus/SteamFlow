using System.Globalization;
using System.Text.Json;
using SteamFlow.Diagnostics;

namespace SteamFlow.WebApi;

public enum Ownership
{
    Unknown,
    Owned,
    NotOwned,
}

// What the plugin knows about the active account's games: an app missing from a stale list may just be new.
public sealed record OwnedView(bool Bound, bool Fresh, OwnedGames Games, DateTimeOffset? LastSync)
{
    public static readonly OwnedView None = new(false, false, OwnedGames.None, null);

    public Ownership StateOf(int appId) =>
        !Bound ? Ownership.Unknown
        : Games.AppIds.Contains(appId) ? Ownership.Owned
        : Fresh ? Ownership.NotOwned
        : Ownership.Unknown;

    public bool IsOwned(int appId) => StateOf(appId) == Ownership.Owned;

    public int? PlaytimeMinutes(int appId) => Games.PlaytimeMinutes.TryGetValue(appId, out var minutes) ? minutes : null;
}

// Each account's list is cached in its own file, so switching accounts shows the last known list right away.
public sealed class OwnedGamesService(ApiAccess access, SteamWebApi api, string cacheFolder, PluginLog log, TimeProvider time)
{
    private static readonly TimeSpan Lifetime = TimeSpan.FromHours(24);
    private static readonly TimeSpan RetryDelay = TimeSpan.FromMinutes(10);
    private static readonly TimeSpan RequestTimeout = TimeSpan.FromSeconds(5);

    private readonly Lock gate = new();
    private readonly Dictionary<ulong, CachedOwnedGames?> cache = [];
    private readonly Dictionary<ulong, DateTimeOffset> lastAttempts = [];
    private readonly HashSet<ulong> refreshing = [];

    public void WarmUp() => _ = CurrentAsync();

    public async Task<OwnedView> CurrentAsync()
    {
        if (await access.CurrentAsync() is not { } bound)
        {
            return OwnedView.None;
        }

        var current = Cached(bound.SteamId64);
        var fresh = current is not null && time.GetUtcNow() - current.LastSync < Lifetime;
        if (!fresh)
        {
            StartRefresh(bound.Key, bound.SteamId64);
        }

        return new OwnedView(true, fresh, current?.Games ?? OwnedGames.None, current?.LastSync);
    }

    public async Task<OwnedGames> FetchAsync(string apiKey, ulong steamId64)
    {
        using var timeout = new CancellationTokenSource(RequestTimeout);
        return await api.OwnedGamesAsync(apiKey, steamId64, timeout.Token);
    }

    public void Store(ulong steamId64, OwnedGames games)
    {
        var entry = new CachedOwnedGames(steamId64, time.GetUtcNow(), games);
        lock (gate)
        {
            cache[steamId64] = entry;
        }

        Save(entry);
    }

    public void Clear(ulong steamId64)
    {
        lock (gate)
        {
            cache[steamId64] = null;
            lastAttempts.Remove(steamId64);
        }

        try
        {
            File.Delete(CacheFile(steamId64));
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
        }
    }

    private CachedOwnedGames? Cached(ulong steamId64)
    {
        lock (gate)
        {
            if (!cache.TryGetValue(steamId64, out var entry))
            {
                entry = Load(steamId64);
                cache[steamId64] = entry;
            }

            return entry;
        }
    }

    private void StartRefresh(string apiKey, ulong steamId64)
    {
        lock (gate)
        {
            var now = time.GetUtcNow();
            if (refreshing.Contains(steamId64)
                || (lastAttempts.TryGetValue(steamId64, out var lastAttempt) && now - lastAttempt < RetryDelay))
            {
                return;
            }

            refreshing.Add(steamId64);
            lastAttempts[steamId64] = now;
        }

        _ = Task.Run(async () =>
        {
            try
            {
                using var timeout = new CancellationTokenSource(RequestTimeout);
                Store(steamId64, await api.OwnedGamesAsync(apiKey, steamId64, timeout.Token));
            }
            catch (Exception ex) when (ex is HttpRequestException or OperationCanceledException or JsonException)
            {
                log.Warn("Owned games sync failed", ex);
            }
            finally
            {
                lock (gate)
                {
                    refreshing.Remove(steamId64);
                }
            }
        });
    }

    private string CacheFile(ulong steamId64) =>
        Path.Combine(cacheFolder, steamId64.ToString(CultureInfo.InvariantCulture) + ".json");

    private CachedOwnedGames? Load(ulong steamId64)
    {
        try
        {
            var path = CacheFile(steamId64);
            if (!File.Exists(path))
            {
                return null;
            }

            using var document = JsonDocument.Parse(File.ReadAllText(path));
            var root = document.RootElement;
            var appIds = root.GetProperty("app_ids").EnumerateArray().Select(id => id.GetInt32()).ToHashSet();
            var playtime = root.GetProperty("playtime").EnumerateObject()
                .ToDictionary(entry => int.Parse(entry.Name, CultureInfo.InvariantCulture), entry => entry.Value.GetInt32());
            return new CachedOwnedGames(
                ulong.Parse(root.GetProperty("steamid64").GetString()!, CultureInfo.InvariantCulture),
                DateTimeOffset.FromUnixTimeSeconds(root.GetProperty("last_sync").GetInt64()),
                new OwnedGames(appIds, playtime));
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or JsonException
            or KeyNotFoundException or InvalidOperationException or FormatException or OverflowException)
        {
            return null;
        }
    }

    private void Save(CachedOwnedGames entry)
    {
        try
        {
            Directory.CreateDirectory(cacheFolder);
            File.WriteAllText(CacheFile(entry.SteamId64), JsonSerializer.Serialize(new Dictionary<string, object>
            {
                ["steamid64"] = entry.SteamId64.ToString(CultureInfo.InvariantCulture),
                ["last_sync"] = entry.LastSync.ToUnixTimeSeconds(),
                ["app_ids"] = entry.Games.AppIds.Order().ToArray(),
                ["playtime"] = entry.Games.PlaytimeMinutes.ToDictionary(
                    item => item.Key.ToString(CultureInfo.InvariantCulture), item => item.Value),
            }));
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
        }
    }

    private sealed record CachedOwnedGames(ulong SteamId64, DateTimeOffset LastSync, OwnedGames Games);
}
