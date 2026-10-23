using SteamFlow.Caching;

namespace SteamFlow.Tests;

public class TimedCacheTests
{
    private readonly ManualTime time = new();
    private int fetches;

    [Fact]
    public async Task FreshValue_IsServedWithoutFetching()
    {
        var cache = new TimedCache<int, string>(time, TimeSpan.FromMinutes(1), TimeSpan.Zero);

        await cache.GetAsync(1, Fetch("a"));
        time.Advance(TimeSpan.FromSeconds(30));

        Assert.Equal("a", await cache.GetAsync(1, Fetch("b")));
        Assert.Equal(1, fetches);
    }

    [Fact]
    public async Task ValueLifetime_CanDependOnTheValue()
    {
        var cache = new TimedCache<int, string>(time, TimeSpan.FromDays(30), TimeSpan.Zero, value => value == "soon" ? TimeSpan.FromHours(1) : TimeSpan.FromDays(30));
        await cache.GetAsync(1, Fetch("soon"));
        await cache.GetAsync(2, Fetch("released"));
        time.Advance(TimeSpan.FromHours(2));

        await cache.GetAsync(1, Fetch("released"));
        await cache.GetAsync(2, Fetch("never"));

        Assert.Equal("released", cache.Peek(1));
        Assert.Equal("released", cache.Peek(2));
        Assert.Equal(3, fetches);
    }

    [Fact]
    public async Task StaleValue_IsServedWhileRefreshRuns()
    {
        var cache = new TimedCache<int, string>(time, TimeSpan.FromMinutes(1), TimeSpan.Zero);
        var refresh = new TaskCompletionSource<string?>();
        await cache.GetAsync(1, Fetch("a"));
        time.Advance(TimeSpan.FromMinutes(2));

        Assert.Equal("a", await cache.GetAsync(1, () => refresh.Task));
        Assert.Equal("a", await cache.GetAsync(1, Fetch("never")));

        refresh.SetResult("b");
        Assert.Equal("b", await cache.GetAsync(1, Fetch("never")));
        Assert.Equal(1, fetches);
    }

    [Fact]
    public async Task StaleValue_WithinMaxStale_IsServedWhileRefreshRuns()
    {
        var cache = new TimedCache<int, string>(time, TimeSpan.FromMinutes(1), TimeSpan.Zero, maxStale: TimeSpan.FromMinutes(10));
        var refresh = new TaskCompletionSource<string?>();
        await cache.GetAsync(1, Fetch("a"));
        time.Advance(TimeSpan.FromMinutes(9));

        Assert.Equal("a", await cache.GetAsync(1, () => refresh.Task));
    }

    [Fact]
    public async Task StaleValue_OlderThanMaxStale_WaitsForRefresh()
    {
        var cache = new TimedCache<int, string>(time, TimeSpan.FromMinutes(1), TimeSpan.Zero, maxStale: TimeSpan.FromMinutes(10));
        var refresh = new TaskCompletionSource<string?>();
        await cache.GetAsync(1, Fetch("a"));
        time.Advance(TimeSpan.FromMinutes(11));

        var first = cache.GetAsync(1, () => refresh.Task);
        var second = cache.GetAsync(1, Fetch("never"));
        Assert.False(first.IsCompleted);
        Assert.False(second.IsCompleted);
        Assert.Null(cache.Peek(1));

        refresh.SetResult("b");
        Assert.Equal("b", await first);
        Assert.Equal("b", await second);
        Assert.Equal(1, fetches);
    }

    [Fact]
    public async Task FailedRefresh_StopsServingValueOlderThanMaxStale()
    {
        var cache = new TimedCache<int, string>(time, TimeSpan.FromMinutes(1), TimeSpan.FromMinutes(30), maxStale: TimeSpan.FromMinutes(10));
        await cache.GetAsync(1, Fetch("a"));
        time.Advance(TimeSpan.FromMinutes(2));

        Assert.Equal("a", await cache.GetAsync(1, Fetch(null)));
        time.Advance(TimeSpan.FromMinutes(9));

        Assert.Null(await cache.GetAsync(1, Fetch("never")));
        Assert.Null(cache.Peek(1));
    }

    [Fact]
    public async Task FailedRefresh_AfterMaxStale_IsRetriedAndServesFreshValue()
    {
        var cache = new TimedCache<int, string>(time, TimeSpan.FromMinutes(1), TimeSpan.FromMinutes(1), maxStale: TimeSpan.FromMinutes(10));
        await cache.GetAsync(1, Fetch("a"));
        time.Advance(TimeSpan.FromMinutes(11));

        Assert.Null(await cache.GetAsync(1, Fetch(null)));
        time.Advance(TimeSpan.FromMinutes(2));

        Assert.Equal("b", await cache.GetAsync(1, Fetch("b")));
    }

    [Fact]
    public async Task Failure_IsRetriedAfterFailureTtl()
    {
        var cache = new TimedCache<int, string>(time, TimeSpan.FromHours(1), TimeSpan.FromMinutes(1));

        Assert.Null(await cache.GetAsync(1, Fetch(null)));
        Assert.Null(await cache.GetAsync(1, Fetch("a")));
        time.Advance(TimeSpan.FromMinutes(2));

        Assert.Equal("a", await cache.GetAsync(1, Fetch("a")));
    }

    [Fact]
    public async Task FailedRefresh_KeepsServingLastGoodValue()
    {
        var cache = new TimedCache<int, string>(time, TimeSpan.FromMinutes(1), TimeSpan.FromMinutes(5));
        await cache.GetAsync(1, Fetch("a"));
        time.Advance(TimeSpan.FromMinutes(2));

        Assert.Equal("a", await cache.GetAsync(1, Fetch(null)));
        Assert.Equal("a", await cache.GetAsync(1, Fetch("never")));
    }

    [Fact]
    public async Task Peek_ReturnsLastGoodValue()
    {
        var cache = new TimedCache<int, string>(time, TimeSpan.FromMinutes(1), TimeSpan.Zero);

        Assert.Null(cache.Peek(1));
        await cache.GetAsync(1, Fetch("a"));

        Assert.Equal("a", cache.Peek(1));
    }

    private Func<Task<string?>> Fetch(string? value) => () =>
    {
        fetches++;
        return Task.FromResult(value);
    };

    private sealed class ManualTime : TimeProvider
    {
        private DateTimeOffset now = new(2026, 10, 21, 12, 0, 0, TimeSpan.Zero);

        public override DateTimeOffset GetUtcNow() => now;

        public void Advance(TimeSpan by) => now += by;
    }
}
