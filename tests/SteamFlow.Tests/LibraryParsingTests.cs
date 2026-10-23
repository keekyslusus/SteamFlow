using System.Text;
using SteamFlow.Library;
using SteamFlow.Steam;

namespace SteamFlow.Tests;

public class LibraryParsingTests
{
    [Theory]
    [InlineData(4, true)]
    [InlineData(6, true)]
    [InlineData(2, true)]
    [InlineData(1026, true)]
    [InlineData(1, false)]
    [InlineData(0, false)]
    public void IsVisible_HidesGamesThatAreNotInstalledYet(long stateFlags, bool expected) =>
        Assert.Equal(expected, InstalledGamesReader.IsVisible(stateFlags));

    [Fact]
    public void Manifest_ReadsSizeOnDisk()
    {
        var steamApps = Directory.CreateTempSubdirectory("steamflow-manifest").FullName;
        try
        {
            File.WriteAllText(Path.Combine(steamApps, "appmanifest_570.acf"), """
                "AppState"
                {
                    "appid"		"570"
                    "name"		"Dota 2"
                    "StateFlags"		"4"
                    "installdir"		"dota 2 beta"
                    "SizeOnDisk"		"77803000000"
                }
                """);

            var game = Assert.Single(new InstalledGamesReader(TestLog.Discard()).Read([steamApps]));

            Assert.Equal(77_803_000_000, game.SizeOnDisk);
        }
        finally
        {
            Directory.Delete(steamApps, recursive: true);
        }
    }

    [Fact]
    public void PlayActivity_ReadsPlaytimeAndLastPlayedFromEitherAppsCasing()
    {
        const string localConfig = """
            "UserLocalConfigStore"
            {
                "Software"
                {
                    "Valve"
                    {
                        "Steam"
                        {
                            "Apps"
                            {
                                "570" { "Playtime" "125" "LastPlayed" "1700000000" }
                                "730" { "LastPlayed" "0" "Playtime" "0" }
                                "10" { "cloud" { "quota" "1" } }
                            }
                        }
                    }
                }
            }
            """;

        var activity = LocalConfigReader.Parse(new MemoryStream(Encoding.UTF8.GetBytes(localConfig)), accountId: null).Activity;

        Assert.Equal(new PlayActivity(125, DateTimeOffset.FromUnixTimeSeconds(1700000000)), activity[570]);
        Assert.Equal(new PlayActivity(0, null), activity[730]);
        Assert.False(activity.ContainsKey(10));
    }

    [Fact]
    public void HiddenGames_AreAddedMinusRemoved()
    {
        const string cloudStorage = """
            [
              ["user-collections.favorite", {"key": "x", "value": "{\"added\":[1]}"}],
              ["user-collections.hidden", {"key": "y", "value": "{\"id\":\"hidden\",\"added\":[10,20,30],\"removed\":[20]}"}]
            ]
            """;

        Assert.Equal(new HashSet<int> { 10, 30 }, HiddenGamesReader.Parse(cloudStorage));
    }

    [Fact]
    public void HiddenGames_EmptyWhenCollectionMissing() =>
        Assert.Empty(HiddenGamesReader.Parse("""[["other", {"value": "{}"}]]"""));

    [Fact]
    public void AchievementMasks_ComeOnlyFromStatsWithBits()
    {
        var schema = new BinaryKeyValues()
            .BeginObject("311690")
            .BeginObject("stats")
            .BeginObject("1").Text("type", "ACHIEVEMENTS").BeginObject("bits").BeginObject("0").End().BeginObject("2").End().End().End()
            .BeginObject("2").Text("type", "ACHIEVEMENTS").BeginObject("bits").BeginObject("31").End().End().End()
            .BeginObject("3").Text("type", "INT").Text("name", "TABLES_FLIPPED").End()
            .End()
            .End()
            .End()
            .ToStream();

        var masks = AchievementsReader.ReadAchievementMasks(schema);

        Assert.Equal(new Dictionary<string, uint> { ["1"] = 0b101, ["2"] = 1u << 31 }, masks);
    }

    [Fact]
    public void UnlockedAchievements_IgnoreCounterStatsAndUnknownBits()
    {
        var masks = new Dictionary<string, uint> { ["1"] = 0b101, ["2"] = 1u << 31 };
        var stats = new BinaryKeyValues()
            .BeginObject("cache")
            .Int32("crc", 12345)
            .BeginObject("1").Int32("data", 0b111).End()
            .BeginObject("2").Int32("data", -1).End()
            .BeginObject("3").Int32("data", 1403).End()
            .Int32("PendingChanges", 0)
            .End()
            .End()
            .ToStream();

        Assert.Equal(2 + 1, AchievementsReader.CountUnlocked(stats, masks));
    }

    [Fact]
    public void SelectLastKnown_PrefersMostRecentThenNewestTimestamp()
    {
        var older = new SteamAccount(76561198000000001, "old", "", MostRecent: true, Timestamp: 100);
        var newest = new SteamAccount(76561198000000002, "new", "", MostRecent: false, Timestamp: 300);
        var recent = new SteamAccount(76561198000000003, "recent", "", MostRecent: true, Timestamp: 200);

        Assert.Equal(recent, SteamUsers.SelectLastKnown([older, newest, recent]));
        Assert.Equal(newest, SteamUsers.SelectLastKnown([newest with { MostRecent = false }, older with { MostRecent = false }]));
    }

    [Fact]
    public void AccountId_IsSteamId64MinusIndividualOffset() =>
        Assert.Equal(1308474997u, new SteamAccount(76561199268740725, "", "", false, 0).AccountId);

    private sealed class BinaryKeyValues
    {
        private readonly MemoryStream buffer = new();

        public BinaryKeyValues BeginObject(string name) => Write(0, name);

        public BinaryKeyValues Int32(string name, int value)
        {
            Write(2, name);
            buffer.Write(BitConverter.GetBytes(value));
            return this;
        }

        public BinaryKeyValues Text(string name, string value)
        {
            Write(1, name);
            buffer.Write(Encoding.UTF8.GetBytes(value));
            buffer.WriteByte(0);
            return this;
        }

        public BinaryKeyValues End()
        {
            buffer.WriteByte(8);
            return this;
        }

        public Stream ToStream() => new MemoryStream(buffer.ToArray());

        private BinaryKeyValues Write(byte type, string name)
        {
            buffer.WriteByte(type);
            buffer.Write(Encoding.UTF8.GetBytes(name));
            buffer.WriteByte(0);
            return this;
        }
    }
}
