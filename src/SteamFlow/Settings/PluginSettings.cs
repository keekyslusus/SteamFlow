using System.Globalization;

namespace SteamFlow.Settings;

public sealed class PluginSettings
{
    public string BlacklistedAppIds { get; set; } = "228980";

    public bool ShowPlaytime { get; set; } = true;

    public bool ShowLastPlayed { get; set; } = true;

    public bool ShowAchievements { get; set; } = true;

    public bool SortLocalByRecent { get; set; } = true;

    public bool HideHiddenGames { get; set; } = true;

    public bool ShowPrices { get; set; } = true;

    public bool ShowPlayerCount { get; set; } = true;

    public bool ShowPositiveReviews { get; set; } = true;

    public bool ShowSteamDbContextMenu { get; set; } = true;

    public bool ShowCsRinContextMenu { get; set; }

    public bool ShowProtonDbContextMenu { get; set; }

    public bool ShowGuidesContextMenu { get; set; } = true;

    public bool ShowDiscussionsContextMenu { get; set; } = true;

    public bool ShowScreenshotsContextMenu { get; set; }

    public bool ShowPropertiesContextMenu { get; set; }

    public bool EnableSmokeApiContextMenu { get; set; }

    public IReadOnlySet<int> BlacklistedAppIdSet() =>
        BlacklistedAppIds
            .Split([',', ' ', ';'], StringSplitOptions.RemoveEmptyEntries)
            .Select(part => int.TryParse(part, NumberStyles.None, CultureInfo.InvariantCulture, out var appId) ? appId : -1)
            .Where(appId => appId > 0)
            .ToHashSet();
}
