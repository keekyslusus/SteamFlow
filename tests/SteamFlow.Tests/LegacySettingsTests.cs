using System.Text.Json.Nodes;
using SteamFlow.Settings;

namespace SteamFlow.Tests;

public class LegacySettingsTests
{
    [Fact]
    public void PythonSettings_AreCopiedByName()
    {
        var settings = new PluginSettings();

        LegacySettings.Apply(settings, (JsonObject)JsonNode.Parse("""
            {
              "enable_smokeapi_context_menu": true,
              "show_steamdb_context_menu": false,
              "show_achievements": false,
              "show_last_played": true,
              "hide_hidden_games": false,
              "show_player_count": false,
              "show_playtime": "false",
              "show_platforms": true,
              "show_positive_reviews": false,
              "show_csrin_context_menu": false,
              "show_prices": false,
              "sort_local_by_recent": false,
              "enable_perf_logging": true,
              "blacklisted_app_ids": "228980, 570"
            }
            """)!);

        Assert.True(settings.EnableSmokeApiContextMenu);
        Assert.False(settings.ShowSteamDbContextMenu);
        Assert.False(settings.ShowAchievements);
        Assert.True(settings.ShowLastPlayed);
        Assert.False(settings.HideHiddenGames);
        Assert.False(settings.ShowPlayerCount);
        Assert.False(settings.ShowPlaytime);
        Assert.False(settings.ShowPositiveReviews);
        Assert.False(settings.ShowCsRinContextMenu);
        Assert.False(settings.ShowPrices);
        Assert.False(settings.SortLocalByRecent);
        Assert.Equal("228980, 570", settings.BlacklistedAppIds);
    }

    [Fact]
    public void MissingOrOddValues_KeepTheDefaults()
    {
        var settings = new PluginSettings();

        LegacySettings.Apply(settings, (JsonObject)JsonNode.Parse("""{"show_prices": "maybe", "show_playtime": null}""")!);

        Assert.True(settings.ShowPrices);
        Assert.True(settings.ShowPlaytime);
        Assert.Equal("228980", settings.BlacklistedAppIds);
        Assert.True(settings.ShowGuidesContextMenu);
    }

    [Fact]
    public void Import_IgnoresAMissingOrBrokenFile()
    {
        var file = Path.Combine(Path.GetTempPath(), "steamflow-tests-" + Guid.NewGuid().ToString("N") + ".json");
        Assert.False(LegacySettings.Import(new PluginSettings(), file, TestLog.Discard()));

        File.WriteAllText(file, "{ not json");
        try
        {
            Assert.False(LegacySettings.Import(new PluginSettings(), file, TestLog.Discard()));
        }
        finally
        {
            File.Delete(file);
        }
    }
}
