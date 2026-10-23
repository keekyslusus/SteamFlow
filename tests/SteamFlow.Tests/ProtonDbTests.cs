using System.Net;
using SteamFlow.Library;
using SteamFlow.Localization;
using SteamFlow.ProtonDb;
using SteamFlow.Settings;
using SteamFlow.Steam;
using SteamFlow.Store;

namespace SteamFlow.Tests;

public static class ProtonDbMenus
{
    // The menu item is off by default, so menus built with default settings never ask ProtonDB.
    public static ProtonDbMenu Unused(Translator text) => Responding(text, new StubHandler(HttpStatusCode.OK, ""));

    public static ProtonDbMenu Responding(Translator text, HttpMessageHandler handler) =>
        new(null!, text, new ProtonDbApi(new HttpClient(handler)), new StoreRequests(TestLog.Discard()), TimeProvider.System);
}

public sealed class StubHandler(HttpStatusCode status, string body) : HttpMessageHandler
{
    public int Requests { get; private set; }

    protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
    {
        Requests++;
        return Task.FromResult(new HttpResponseMessage(status) { Content = new StringContent(body) });
    }
}

public class ProtonDbTests
{
    private const string Summary = """
        {"bestReportedTier":"platinum","confidence":"strong","score":0.77,"tier":"gold","total":2743,"trendingTier":"platinum"}
        """;

    [Fact]
    public void Summary_ReadsTiersAndReportCount() =>
        Assert.Equal(new ProtonDbSummary("gold", "platinum", 2743), ProtonDbApi.ParseSummary(Summary));

    [Fact]
    public void Summary_WithoutTierGivesNull() =>
        Assert.Null(ProtonDbApi.ParseSummary("""{"total":3}"""));

    [Fact]
    public void Summary_WithoutTrendingFallsBackToTier() =>
        Assert.Equal(new ProtonDbSummary("silver", "silver", 0), ProtonDbApi.ParseSummary("""{"tier":"Silver"}"""));

    [Fact]
    public void Rating_ShowsTrendingOnlyWhenItDiffers()
    {
        var menu = ProtonDbMenus.Unused(EnglishText.Translator());

        Assert.Equal("Gold | Trending: Platinum | 2,743 reports", menu.Rating(new ProtonDbSummary("gold", "platinum", 2743)));
        Assert.Equal("Gold | 12 reports", menu.Rating(new ProtonDbSummary("gold", "gold", 12)));
        Assert.Equal("Bronze | 1 report", menu.Rating(new ProtonDbSummary("bronze", "bronze", 1)));
        Assert.Equal("Unheard | 2 reports", menu.Rating(new ProtonDbSummary("unheard", "unheard", 2)));
    }

    [Fact]
    public void InstalledGame_FollowsCsRinWithoutAskingProtonDb()
    {
        var handler = new StubHandler(HttpStatusCode.OK, Summary);

        var items = Menu(handler).Build(new GameMenuTarget(1091500, "Cyberpunk 2077", @"C:\games\cp"));

        var index = items.FindIndex(item => item.Title == "Community: Open in ProtonDB");
        Assert.Equal("Community: Search in CS.RIN", items[index - 1].Title);
        Assert.Equal("Open ProtonDB page for Cyberpunk 2077", items[index].SubTitle);
        Assert.Equal(0, handler.Requests);
    }

    [Fact]
    public void GameNotInstalled_ShowsRating()
    {
        var items = Menu(new StubHandler(HttpStatusCode.OK, Summary)).Build(new GameMenuTarget(1091500, "Cyberpunk 2077", "", IsOwned: true));

        Assert.Equal("Gold | Trending: Platinum | 2,743 reports", items.Single(item => item.Title == "Community: Open in ProtonDB").SubTitle);
    }

    [Fact]
    public void MenuItem_IsCachedPerApp()
    {
        var handler = new StubHandler(HttpStatusCode.OK, Summary);
        var menu = Menu(handler);

        menu.Build(new GameMenuTarget(1091500, "Cyberpunk 2077", ""));
        menu.Build(new GameMenuTarget(1091500, "Cyberpunk 2077", ""));

        Assert.Equal(1, handler.Requests);
    }

    [Fact]
    public void MenuItem_WithoutReportsLinksThePage()
    {
        var items = Menu(new StubHandler(HttpStatusCode.NotFound, "<html>Page not found</html>")).Build(new GameMenuTarget(9999999, "New Game", ""));

        Assert.Equal("Open ProtonDB page for New Game", items.Single(item => item.Title == "Community: Open in ProtonDB").SubTitle);
    }

    [Fact]
    public void MenuItem_HiddenForDlcAndUnreleased()
    {
        var handler = new StubHandler(HttpStatusCode.OK, Summary);
        var menu = Menu(handler);

        var dlc = menu.Build(new GameMenuTarget(1, "DLC", "", StoreType: "dlc"));
        var demo = menu.Build(new GameMenuTarget(1519390, "Loop Hero Demo", "", StoreType: "demo"));
        var unreleased = menu.Build(new GameMenuTarget(2, "Soon", "", StoreType: "game", ComingSoon: true));

        Assert.DoesNotContain(dlc.Concat(demo).Concat(unreleased), item => item.Title == "Community: Open in ProtonDB");
        Assert.Equal(0, handler.Requests);
    }

    private static GameContextMenu Menu(StubHandler handler)
    {
        var text = EnglishText.Translator();
        return new GameContextMenu(
            null!,
            text,
            new PluginSettings { ShowProtonDbContextMenu = true, ShowCsRinContextMenu = true },
            new SteamClient(null!, text),
            Wishlists.WithoutApi(text),
            Carts.WithoutAccount(text),
            FriendMenus.WithoutFriends(text),
            ProtonDbMenus.Responding(text, handler),
            Smokes.Disabled(text));
    }
}
