using SteamFlow.Library;
using SteamFlow.Settings;

namespace SteamFlow.Tests;

public class LibrarySubtitlesTests
{
    private static readonly DateTime Now = new(2026, 10, 21, 15, 0, 0);

    [Theory]
    [InlineData(0, "0m")]
    [InlineData(59, "59m")]
    [InlineData(90, "1.5h")]
    [InlineData(6000, "100.0h")]
    public void Playtime_UsesMinutesUnderAnHour(int minutes, string expected) =>
        Assert.Equal(expected, Subtitles().FormatPlaytime(minutes));

    [Theory]
    [InlineData("2026-10-21 01:00", "Today")]
    [InlineData("2026-10-20 23:59", "Yesterday")]
    [InlineData("2026-10-14 12:00", "7 days ago")]
    [InlineData("2026-10-13 12:00", "Oct 13")]
    [InlineData("2025-12-31 12:00", "Dec 31, 2025")]
    public void LastPlayed_IsRelativeForTheLastWeek(string playedAt, string expected) =>
        Assert.Equal(expected, Subtitles().FormatLastPlayed(DateTime.Parse(playedAt), Now));

    [Fact]
    public void Build_JoinsEnabledParts()
    {
        var game = Game(new PlayActivity(90, null), new AchievementProgress(3, 10), hasCurrentAccountData: true);

        Assert.Equal("Launch game | 1.5h | 3/10", Subtitles().Build(game, hasMultipleAccounts: true));
    }

    [Fact]
    public void Build_HidesZeroAchievementsFromAnotherAccount()
    {
        var game = Game(null, new AchievementProgress(0, 10), hasCurrentAccountData: false);

        Assert.Equal("Launch game", Subtitles().Build(game, hasMultipleAccounts: false));
    }

    [Fact]
    public void Build_FlagsMissingAccountDataOnlyWithSeveralAccounts()
    {
        var game = Game(null, null, hasCurrentAccountData: false);

        Assert.Equal("Launch game | No current-account data", Subtitles().Build(game, hasMultipleAccounts: true));
    }

    [Fact]
    public void Build_RespectsSettings()
    {
        var settings = new PluginSettings { ShowPlaytime = false, ShowAchievements = false, ShowLastPlayed = false };
        var game = Game(new PlayActivity(90, DateTimeOffset.Now), new AchievementProgress(3, 10), hasCurrentAccountData: true);

        Assert.Equal("Launch game", Subtitles(settings).Build(game, hasMultipleAccounts: false));
    }

    [Fact]
    public void Blacklist_IgnoresJunkEntries() =>
        Assert.Equal(
            new HashSet<int> { 228980, 570 },
            new PluginSettings { BlacklistedAppIds = " 228980, abc,570;-5" }.BlacklistedAppIdSet());

    private static LibrarySubtitles Subtitles(PluginSettings? settings = null) =>
        new(EnglishText.Translator(), settings ?? new PluginSettings(), TimeProvider.System);

    private static LibraryGame Game(PlayActivity? activity, AchievementProgress? achievements, bool hasCurrentAccountData) =>
        new(570, "Dota 2", @"C:\games\dota", null, activity, achievements, hasCurrentAccountData);
}
