using SteamFlow.Library;
using SteamFlow.Settings;
using SteamFlow.Store;

namespace SteamFlow.Tests;

public class StoreSubtitlesTests
{
    private static readonly StoreSearchItem Gungeon =
        new(311690, "app", "Enter the Gungeon");

    private static readonly AppDetails Released = new("game", "Enter the Gungeon", false, false, "5 Apr, 2016");

    [Fact]
    public void Build_JoinsReviewsPlayersPriceAndRelease()
    {
        var data = new StoreItemData(Gungeon, Released, new StorePrice("820₸", 80), new ReviewSummary(95, 90079), new PlayerCount(1683));

        Assert.Equal(
            "Open in Store | 👍 95% | 🌐 1,683 | 820₸ -80% | 5 Apr, 2016",
            Subtitles(new PluginSettings()).Build(data));
    }

    [Fact]
    public void Build_FreeAndComingSoonReplacePrice()
    {
        var free = new StoreItemData(Gungeon, Released with { IsFree = true, ReleaseDate = "" }, null, null, null);
        var upcoming = new StoreItemData(Gungeon, Released with { ComingSoon = true, ReleaseDate = "To be announced" }, null, null, null);

        Assert.Equal("Open in Store | Free", Subtitles(new PluginSettings()).Build(free));
        Assert.Equal("Open in Store | Coming soon", Subtitles(new PluginSettings()).Build(upcoming));
    }

    [Fact]
    public void Build_HidesMetricsForDlcAndUnreleasedGames()
    {
        var reviews = new ReviewSummary(90, 10);
        var dlc = new StoreItemData(Gungeon with { Name = "Gungeon Soundtrack" }, null, null, reviews, new PlayerCount(5));
        var upcoming = new StoreItemData(Gungeon, Released with { ComingSoon = true, ReleaseDate = "" }, null, reviews, new PlayerCount(5));

        Assert.Equal("Open in Store", Subtitles(new PluginSettings()).Build(dlc));
        Assert.Equal("Open in Store | Coming soon", Subtitles(new PluginSettings()).Build(upcoming));
    }

    [Fact]
    public void Build_RespectsSettings()
    {
        var settings = new PluginSettings { ShowPrices = false, ShowPlayerCount = false, ShowPositiveReviews = false };
        var data = new StoreItemData(Gungeon, Released with { ReleaseDate = "" }, new StorePrice("820₸", 0), new ReviewSummary(90, 10), new PlayerCount(5));

        Assert.Equal("Open in Store", Subtitles(settings).Build(data));
    }

    [Theory]
    [InlineData(88, "👍 88%")]
    [InlineData(40, "👍 40%")]
    [InlineData(39, "👎 39%")]
    [InlineData(0, "👎 0%")]
    public void Reviews_TurnNegativeBelowFortyPercent(int percent, string expected) =>
        Assert.Equal(expected, Subtitles(new PluginSettings()).FormatReviews(new ReviewSummary(percent, 100)));

    [Theory]
    [InlineData(null, "game", false, RefundState.Unclear)]
    [InlineData(90, "game", false, RefundState.Likely)]
    [InlineData(120, "game", false, RefundState.None)]
    [InlineData(90, "game", true, RefundState.None)]
    [InlineData(90, "dlc", false, RefundState.None)]
    public void Refund_NeedsPaidGameUnderTwoHours(int? playtime, string type, bool isFree, RefundState expected)
    {
        var game = new LibraryGame(1, "Game", @"C:\g", null, new PlayActivity(playtime, null), null, HasCurrentAccountData: true);

        Assert.Equal(expected, RefundEligibility.Evaluate(game, new AppDetails(type, "Game", isFree, false, "")));
    }

    [Fact]
    public void Refund_NeedsCurrentAccountDataAndDetails()
    {
        var foreign = new LibraryGame(1, "Game", @"C:\g", null, null, null, HasCurrentAccountData: false);
        var own = foreign with { HasCurrentAccountData = true };

        Assert.Equal(RefundState.None, RefundEligibility.Evaluate(foreign, Released));
        Assert.Equal(RefundState.None, RefundEligibility.Evaluate(own, null));
    }

    private static StoreSubtitles Subtitles(PluginSettings settings) => new(EnglishText.Translator(), settings);
}
