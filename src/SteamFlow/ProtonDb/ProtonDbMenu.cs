using Flow.Launcher.Plugin;
using SteamFlow.Caching;
using SteamFlow.Localization;
using SteamFlow.Store;

namespace SteamFlow.ProtonDb;

public sealed class ProtonDbMenu
{
    private readonly IPublicAPI flow;
    private readonly Translator text;
    private readonly ProtonDbApi api;
    private readonly StoreRequests requests;
    private readonly TimedCache<int, ProtonDbSummary> summaries;

    public ProtonDbMenu(IPublicAPI flow, Translator text, ProtonDbApi api, StoreRequests requests, TimeProvider time)
    {
        this.flow = flow;
        this.text = text;
        this.api = api;
        this.requests = requests;
        // A miss also covers apps without reports, so it is retried sooner than a rating expires.
        summaries = new(time, TimeSpan.FromDays(1), TimeSpan.FromMinutes(10));
    }

    // Flow builds a context menu synchronously and cannot update one that is already open, so the menu waits
    // for the rating; StoreRequests bounds that wait by its timeout. Task.Run keeps the request off Flow's
    // UI context, which this call blocks.
    public Result Item(int appId, string name, bool withRating)
    {
        var summary = withRating
            ? Task.Run(() => summaries.GetAsync(
                    appId,
                    () => requests.Quietly("ProtonDB summary request", token => api.SummaryAsync(appId, token), $"app {appId}")))
                .GetAwaiter()
                .GetResult()
            : null;
        return new Result
        {
            Title = text.Get("steamflow_menu_protondb"),
            SubTitle = summary is null ? text.Format("steamflow_menu_protondb_subtitle", name) : Rating(summary),
            IcoPath = Icons.ProtonDb,
            Action = _ =>
            {
                flow.OpenUrl($"https://www.protondb.com/app/{appId}");
                return true;
            },
        };
    }

    public string Rating(ProtonDbSummary summary)
    {
        var reports = text.Format(summary.Reports == 1 ? "steamflow_protondb_reports_one" : "steamflow_protondb_reports", summary.Reports);
        return summary.TrendingTier == summary.Tier
            ? text.Format("steamflow_protondb_rating", TierName(summary.Tier), reports)
            : text.Format("steamflow_protondb_rating_trending", TierName(summary.Tier), TierName(summary.TrendingTier), reports);
    }

    private string TierName(string tier) => tier switch
    {
        "platinum" or "gold" or "silver" or "bronze" or "borked" or "pending" => text.Get("steamflow_protondb_tier_" + tier),
        _ => char.ToUpperInvariant(tier[0]) + tier[1..],
    };
}
