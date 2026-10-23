using System.Collections.Concurrent;

namespace SteamFlow.Caching;

// ttlFor lets a value that is expected to change soon expire sooner than the rest. maxStale stops serving an
// expired value once it is old enough to mislead, such as a price from before a sale started.
public sealed class TimedCache<TKey, TValue>(
    TimeProvider time,
    TimeSpan ttl,
    TimeSpan failureTtl,
    Func<TValue, TimeSpan>? ttlFor = null,
    TimeSpan? maxStale = null)
    where TKey : notnull
    where TValue : class
{
    private const int MaxEntries = 2000;

    private readonly ConcurrentDictionary<TKey, Entry> entries = new();
    private readonly TimeSpan staleLimit = maxStale ?? TimeSpan.MaxValue;

    // Fresh values are returned as is; a stale value is still returned while a refresh runs in the background,
    // so a slow Steam endpoint only delays the first query that has nothing cached.
    public Task<TValue?> GetAsync(TKey key, Func<Task<TValue?>> fetch)
    {
        var now = time.GetUtcNow();
        if (!entries.TryGetValue(key, out var entry))
        {
            return Start(key, fetch, now, previous: null, previousAt: default).Current;
        }

        if (!entry.Current.IsCompleted)
        {
            return Fallback(entry, now) is { } previous ? Task.FromResult<TValue?>(previous) : entry.Current;
        }

        var value = entry.Current.IsCompletedSuccessfully ? entry.Current.Result : null;
        if (now - entry.FetchedAt < (value is null ? failureTtl : ttlFor?.Invoke(value) ?? ttl))
        {
            // A failed refresh keeps serving the last good value instead of dropping it.
            return value is null && Fallback(entry, now) is { } previousValue ? Task.FromResult<TValue?>(previousValue) : entry.Current;
        }

        var refreshed = value is null
            ? Start(key, fetch, now, entry.Previous, entry.PreviousAt)
            : Start(key, fetch, now, value, entry.FetchedAt);
        return Fallback(refreshed, now) is { } stale ? Task.FromResult<TValue?>(stale) : refreshed.Current;
    }

    // For callers that learned a newer value some other way, such as re-reading a list after changing it.
    public void Set(TKey key, TValue value) => entries[key] = new Entry(Task.FromResult<TValue?>(value), time.GetUtcNow(), null, default);

    public TValue? Peek(TKey key)
    {
        if (!entries.TryGetValue(key, out var entry))
        {
            return null;
        }

        var now = time.GetUtcNow();
        return entry.Current.IsCompletedSuccessfully && entry.Current.Result is { } value && now - entry.FetchedAt < staleLimit
            ? value
            : Fallback(entry, now);
    }

    private TValue? Fallback(Entry entry, DateTimeOffset now) =>
        entry.Previous is { } previous && now - entry.PreviousAt < staleLimit ? previous : null;

    private Entry Start(TKey key, Func<Task<TValue?>> fetch, DateTimeOffset now, TValue? previous, DateTimeOffset previousAt)
    {
        if (entries.Count >= MaxEntries)
        {
            entries.Clear();
        }

        var entry = new Entry(fetch(), now, previous, previousAt);
        entries[key] = entry;
        return entry;
    }

    private sealed record Entry(Task<TValue?> Current, DateTimeOffset FetchedAt, TValue? Previous, DateTimeOffset PreviousAt);
}
