using SteamFlow.Caching;
using SteamFlow.Diagnostics;
using SteamFlow.Localization;

namespace SteamFlow.Store;

public sealed class StoreCatalog
{
    private const string FallbackCountryCode = "us";

    private static readonly TimeSpan SlowSearch = TimeSpan.FromSeconds(1);

    private readonly StoreApi api;
    private readonly StoreRequests requests;
    private readonly Translator text;
    private readonly PluginLog log;
    private readonly TimedCache<string, string> region;
    private readonly TimedCache<(string Term, string Country, string Language), IReadOnlyList<StoreSearchItem>> searches;
    private readonly TimedCache<(int AppId, string Language), AppDetails> details;
    private readonly TimedCache<(string AppIds, string Country), IReadOnlyDictionary<int, StorePrice>> prices;
    private readonly TimedCache<int, ReviewSummary> reviews;
    private readonly TimedCache<int, PlayerCount> players;
    private readonly TimedCache<(string Country, string Language), FeaturedCollections> featured;

    // appdetails is rate limited per IP, and a large wishlist would otherwise ask for hundreds of apps at once.
    private readonly SemaphoreSlim detailsSlots = new(6);

    public StoreCatalog(StoreApi api, StoreRequests requests, Translator text, PluginLog log, TimeProvider time)
    {
        this.api = api;
        this.requests = requests;
        this.text = text;
        this.log = log;
        region = new(time, TimeSpan.FromHours(24), TimeSpan.FromMinutes(10));
        // Failed searches are not kept: retyping the same term should retry right away.
        searches = new(time, TimeSpan.FromSeconds(30), TimeSpan.Zero);
        // An unreleased game becomes purchasable on release day, and with sleep instead of shutdown
        // Flow can keep this cache for weeks.
        details = new(
            time,
            TimeSpan.FromDays(30),
            TimeSpan.FromHours(6),
            app => app.ComingSoon ? TimeSpan.FromHours(1) : TimeSpan.FromDays(30));
        // Results show what is cached and are not rebuilt when a background refresh lands, so an old price
        // would stay on screen; past maxStale the result waits for the fresh one instead.
        prices = new(time, TimeSpan.FromSeconds(30), TimeSpan.FromSeconds(30), maxStale: TimeSpan.FromMinutes(10));
        reviews = new(time, TimeSpan.FromHours(4), TimeSpan.FromMinutes(10));
        players = new(time, TimeSpan.FromMinutes(4), TimeSpan.FromMinutes(1), maxStale: TimeSpan.FromMinutes(30));
        featured = new(time, TimeSpan.FromMinutes(20), TimeSpan.FromMinutes(5));
    }

    private string Language => text.Get("steamflow_steam_language");

    public void WarmUp() => _ = CountryCodeAsync();

    public async Task<string> CountryCodeAsync() =>
        await region.GetAsync("country", () => requests.Quietly("Country code request", token => api.FetchCountryCodeAsync(token))) ?? FallbackCountryCode;

    public async Task<IReadOnlyList<StoreSearchItem>> SearchAsync(string term)
    {
        var country = await CountryCodeAsync();
        var language = Language;
        var items = await searches.GetAsync(
            (term.ToLowerInvariant(), country, language),
            async () =>
            {
                var started = log.StartTiming();
                using var timeout = new CancellationTokenSource(StoreRequests.Timeout);
                var found = await api.SearchAsync(term, country, language, timeout.Token);
                log.Slow("Store search request", started, SlowSearch, $"'{term}'");
                return found;
            });
        return items ?? [];
    }

    // Top sellers and specials come from one request, so both lists share one cache entry.
    public async Task<FeaturedCollections?> FeaturedAsync()
    {
        var country = await CountryCodeAsync();
        var language = Language;
        return await featured.GetAsync(
            (country, language),
            async () =>
            {
                var started = log.StartTiming();
                using var timeout = new CancellationTokenSource(StoreRequests.Timeout);
                var collections = await api.FeaturedAsync(country, language, timeout.Token);
                log.Slow("Featured collections request", started, SlowSearch);
                return collections;
            });
    }

    public Task<AppDetails?> DetailsAsync(int appId)
    {
        var language = Language;
        return details.GetAsync((appId, language), async () =>
        {
            var country = await CountryCodeAsync();
            await detailsSlots.WaitAsync();
            try
            {
                return await requests.Quietly("App details request", token => api.AppDetailsAsync(appId, country, language, token), $"app {appId}");
            }
            finally
            {
                detailsSlots.Release();
            }
        });
    }

    public AppDetails? PeekDetails(int appId) => details.Peek((appId, Language));

    public async Task<IReadOnlyDictionary<int, StorePrice>> PricesAsync(IReadOnlyCollection<int> appIds)
    {
        if (appIds.Count == 0)
        {
            return new Dictionary<int, StorePrice>();
        }

        var country = await CountryCodeAsync();
        var result = await prices.GetAsync(
            (string.Join(',', appIds.Order()), country),
            () => requests.Quietly("Prices request", token => api.PricesAsync(appIds, country, token), $"{appIds.Count} apps"));
        return result ?? new Dictionary<int, StorePrice>();
    }

    public Task<ReviewSummary?> ReviewsAsync(int appId) =>
        reviews.GetAsync(appId, () => requests.Quietly("Reviews request", token => api.ReviewsAsync(appId, token), $"app {appId}"));

    public Task<PlayerCount?> PlayersAsync(int appId) =>
        players.GetAsync(appId, () => requests.Quietly("Player count request", token => api.CurrentPlayersAsync(appId, token), $"app {appId}"));
}
