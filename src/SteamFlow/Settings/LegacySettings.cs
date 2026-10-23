using System.Text.Json;
using System.Text.Json.Nodes;
using SteamFlow.Diagnostics;

namespace SteamFlow.Settings;

// The Python plugin kept its options in its own Settings.json with snake_case names. They are copied once, when
// this plugin has no settings file yet, so an update from the Python plugin keeps what the user chose.
public static class LegacySettings
{
    public static bool Import(PluginSettings settings, string legacyFile, PluginLog log)
    {
        if (!File.Exists(legacyFile))
        {
            return false;
        }

        try
        {
            if (JsonNode.Parse(File.ReadAllText(legacyFile)) is not JsonObject legacy)
            {
                return false;
            }

            Apply(settings, legacy);
            return true;
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or JsonException)
        {
            log.Warn("Python plugin settings unreadable", ex);
            return false;
        }
    }

    public static void Apply(PluginSettings settings, JsonObject legacy)
    {
        if (Text(legacy, "blacklisted_app_ids") is { } blacklist)
        {
            settings.BlacklistedAppIds = blacklist;
        }

        settings.ShowPlaytime = Flag(legacy, "show_playtime") ?? settings.ShowPlaytime;
        settings.ShowLastPlayed = Flag(legacy, "show_last_played") ?? settings.ShowLastPlayed;
        settings.ShowAchievements = Flag(legacy, "show_achievements") ?? settings.ShowAchievements;
        settings.SortLocalByRecent = Flag(legacy, "sort_local_by_recent") ?? settings.SortLocalByRecent;
        settings.HideHiddenGames = Flag(legacy, "hide_hidden_games") ?? settings.HideHiddenGames;
        settings.ShowPrices = Flag(legacy, "show_prices") ?? settings.ShowPrices;
        settings.ShowPlayerCount = Flag(legacy, "show_player_count") ?? settings.ShowPlayerCount;
        settings.ShowPositiveReviews = Flag(legacy, "show_positive_reviews") ?? settings.ShowPositiveReviews;
        settings.ShowSteamDbContextMenu = Flag(legacy, "show_steamdb_context_menu") ?? settings.ShowSteamDbContextMenu;
        settings.ShowCsRinContextMenu = Flag(legacy, "show_csrin_context_menu") ?? settings.ShowCsRinContextMenu;
        settings.EnableSmokeApiContextMenu = Flag(legacy, "enable_smokeapi_context_menu") ?? settings.EnableSmokeApiContextMenu;
    }

    // Flow's settings panel stores checkboxes as booleans, but an edited file can hold "true" or "false" text.
    private static bool? Flag(JsonObject legacy, string name) =>
        legacy[name] is JsonValue value
            ? value.TryGetValue<bool>(out var flag) ? flag
            : value.TryGetValue<string>(out var text) && bool.TryParse(text, out var parsed) ? parsed
            : null
            : null;

    private static string? Text(JsonObject legacy, string name) =>
        legacy[name] is JsonValue value && value.TryGetValue<string>(out var text) ? text : null;
}
