using System.Text;
using SteamFlow.Localization;
using SteamFlow.Library;
using SteamFlow.Settings;

namespace SteamFlow.Store;

public sealed record StoreItemData(
    StoreSearchItem Item,
    AppDetails? Details,
    StorePrice? Price,
    ReviewSummary? Reviews,
    PlayerCount? Players,
    string? ImagePath = null,
    bool IsOwned = false,
    int? OwnedPlaytimeMinutes = null,
    AchievementProgress? OwnedAchievements = null,
    string? Suffix = null);

public sealed class StoreSubtitles(Translator text, PluginSettings settings)
{
    private const string Separator = " | ";

    private static readonly string[] ReleaseDatePlaceholders = ["coming soon", "to be announced", "tba", "tbd"];

    private static readonly string[] NonGameNamePatterns =
    [
        "soundtrack", "demo", "dlc", "art book", "artbook", "digital artbook", "digital art book",
        "supporter pack", "starter pack", "upgrade pack", "season pass", "expansion pass",
        "character creator", "cosmetic pack",
    ];

    public string Build(StoreItemData data)
    {
        var subtitle = new StringBuilder(text.Get(data.IsOwned ? "steamflow_store_subtitle_owned" : "steamflow_store_subtitle"));

        var live = SupportsLiveMetrics(data.Item, data.Details);
        if (live && settings.ShowPositiveReviews && data.Reviews is { TotalReviews: > 0 } reviews)
        {
            subtitle.Append(Separator).Append(FormatReviews(reviews));
        }

        if (live && settings.ShowPlayerCount && data.Players is { Value: > 0 } players)
        {
            subtitle.Append(Separator).Append(text.Format("steamflow_player_count", players.Value));
        }

        if (data.IsOwned && data.OwnedPlaytimeMinutes is { } minutes)
        {
            subtitle.Append(Separator).Append(PlaytimeText.Format(text, minutes));
        }

        if (data.IsOwned && settings.ShowAchievements && data.OwnedAchievements is { Total: > 0 } achievements)
        {
            subtitle.Append(Separator).Append(text.Format("steamflow_achievements", achievements.Unlocked, achievements.Total));
        }

        if (settings.ShowPrices && !data.IsOwned && FormatPrice(data) is { } price)
        {
            subtitle.Append(Separator).Append(price);
        }

        if (ShouldShowReleaseDate(data.Details))
        {
            subtitle.Append(Separator).Append(data.Details!.ReleaseDate);
        }

        if (data.Suffix is { Length: > 0 } suffix)
        {
            subtitle.Append(Separator).Append(suffix);
        }

        return subtitle.ToString();
    }

    // Players and reviews only mean something for released base games, not DLC, soundtracks or demos.
    public static bool SupportsLiveMetrics(StoreSearchItem item, AppDetails? details) =>
        item.Type == "app"
        && (details is null || ((details.Type is "" or "game") && !details.ComingSoon))
        && item.Name.Length > 0
        && !NonGameNamePatterns.Any(pattern => item.Name.Contains(pattern, StringComparison.OrdinalIgnoreCase));

    public string FormatReviews(ReviewSummary reviews)
    {
        var ratio = reviews.TotalPositive * 100.0 / reviews.TotalReviews;
        var percent = (int)Math.Round(ratio, MidpointRounding.ToEven);
        // Steam labels everything under 40% positive as Mostly Negative or worse; compare before rounding so 39.6% is not shown as positive.
        return text.Format(ratio < 40 ? "steamflow_store_reviews_negative" : "steamflow_store_reviews_positive", percent);
    }

    private string? FormatPrice(StoreItemData data)
    {
        if (data.Details?.IsFree == true)
        {
            return text.Get("steamflow_store_free");
        }

        if (data.Price is { } price)
        {
            return price.DiscountPercent > 0
                ? text.Format("steamflow_store_price_discounted", price.Final, price.DiscountPercent)
                : price.Final;
        }

        return data.Details?.ComingSoon == true ? text.Get("steamflow_store_coming_soon") : null;
    }

    private bool ShouldShowReleaseDate(AppDetails? details)
    {
        if (details is not { ReleaseDate.Length: > 0 })
        {
            return false;
        }

        var normalized = Normalize(details.ReleaseDate);
        return !ReleaseDatePlaceholders.Contains(normalized)
            && !(details.ComingSoon && normalized == Normalize(text.Get("steamflow_store_coming_soon")));
    }

    private static string Normalize(string value) =>
        string.Join(' ', value.Trim().ToLowerInvariant().Split(' ', StringSplitOptions.RemoveEmptyEntries));
}
