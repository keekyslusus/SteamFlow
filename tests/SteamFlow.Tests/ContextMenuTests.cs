using SteamFlow.Library;
using SteamFlow.Settings;
using SteamFlow.Steam;

namespace SteamFlow.Tests;

public class ContextMenuTests
{
    [Fact]
    public void InstalledGame_ShowsMenuInPythonOrder()
    {
        Assert.Equal(
        [
            "Store: Open in Steam",
            "Store: Open in SteamDB",
            "Community: Search in CS.RIN",
            "Community: Open guides",
            "Community: Open discussions",
            "Library: Open recordings & screenshots",
            "Library: Open properties",
            "File: Browse local files",
            "File: Uninstall game",
        ],
        Titles(Menu(AllLinks()).Build(Game(@"C:\games\dota"))));
    }

    [Fact]
    public void InstalledGame_HidesNicheLinksByDefault()
    {
        Assert.Equal(
        [
            "Store: Open in Steam",
            "Store: Open in SteamDB",
            "Community: Open guides",
            "Community: Open discussions",
            "File: Browse local files",
            "File: Uninstall game",
        ],
        Titles(Menu(new PluginSettings()).Build(Game(@"C:\games\dota"))));
    }

    [Fact]
    public void OptionalLinks_FollowSettings()
    {
        var settings = new PluginSettings { ShowSteamDbContextMenu = false, ShowCsRinContextMenu = false };

        var titles = Titles(Menu(settings).Build(Game(@"C:\games\dota")));

        Assert.DoesNotContain("Store: Open in SteamDB", titles);
        Assert.DoesNotContain("Community: Search in CS.RIN", titles);
    }

    [Fact]
    public void CommunityAndLibraryLinks_FollowSettings()
    {
        var settings = AllLinks();
        settings.ShowGuidesContextMenu = false;
        settings.ShowDiscussionsContextMenu = false;
        settings.ShowScreenshotsContextMenu = false;
        settings.ShowPropertiesContextMenu = false;

        Assert.Equal(
        [
            "Store: Open in Steam",
            "Store: Open in SteamDB",
            "Community: Search in CS.RIN",
            "File: Browse local files",
            "File: Uninstall game",
        ],
        Titles(Menu(settings).Build(Game(@"C:\games\dota"))));
    }

    [Fact]
    public void GameWithoutInstallFolder_HasNoLocalActions()
    {
        Assert.Equal(
        [
            "Store: Open in Steam",
            "Store: Open in SteamDB",
            "Community: Open guides",
            "Community: Open discussions",
        ],
        Titles(Menu(new PluginSettings()).Build(Game(""))));
    }

    [Fact]
    public void Refund_SitsBetweenScreenshotsAndProperties()
    {
        var titles = Titles(Menu(AllLinks()).Build(Game(@"C:\games\dota", refund: RefundState.Likely)));

        Assert.Equal(titles.IndexOf("Library: Open recordings & screenshots") + 1, titles.IndexOf("Support: Open refund page"));
        Assert.Equal(titles.IndexOf("Support: Open refund page") + 1, titles.IndexOf("Library: Open properties"));
    }

    [Fact]
    public void Refund_UnclearUsesSupportCopy() =>
        Assert.Contains("Support: Check refund options", Titles(Menu(new PluginSettings()).Build(Game(@"C:\games\dota", refund: RefundState.Unclear))));

    [Fact]
    public void CommunityLinks_HiddenForDlcAndGuidesForUnreleased()
    {
        var dlc = Titles(Menu(new PluginSettings()).Build(Game("", storeType: "dlc")));
        var demo = Titles(Menu(new PluginSettings()).Build(Game("", storeType: "demo")));
        Assert.DoesNotContain("Community: Open guides", demo);
        Assert.DoesNotContain("Community: Open discussions", demo);
        var unreleased = Titles(Menu(new PluginSettings()).Build(Game("", storeType: "game", comingSoon: true)));

        Assert.DoesNotContain("Community: Open guides", dlc);
        Assert.DoesNotContain("Community: Open discussions", dlc);
        Assert.DoesNotContain("Community: Open guides", unreleased);
        Assert.Contains("Community: Open discussions", unreleased);
    }

    [Theory]
    [InlineData(77_803_000_000, "Open uninstall prompt for Dota 2 | 72.5~ Gb")]
    [InlineData(1L << 30, "Open uninstall prompt for Dota 2 | 1~ Gb")]
    [InlineData(330_000_000, "Open uninstall prompt for Dota 2 | 315~ Mb")]
    [InlineData(1_000, "Open uninstall prompt for Dota 2 | 1~ Mb")]
    [InlineData(0, "Open uninstall prompt for Dota 2")]
    public void Uninstall_ShowsApproximateSize(long sizeOnDisk, string expected)
    {
        var items = Menu(new PluginSettings()).Build(new GameMenuTarget(570, "Dota 2", @"C:\games\dota", SizeOnDisk: sizeOnDisk));

        Assert.Equal(expected, items.Single(item => item.Title == "File: Uninstall game").SubTitle);
    }

    [Theory]
    [InlineData(new[] { "Four Quarters" }, new[] { "Devolver Digital" }, "Open store page for Dota 2 by Four Quarters/Devolver Digital")]
    [InlineData(new[] { "Future Cat LLC" }, new[] { "future cat llc" }, "Open store page for Dota 2 by Future Cat LLC")]
    [InlineData(new[] { "Valve", "Hidden Path" }, new[] { "Valve" }, "Open store page for Dota 2 by Valve, Hidden Path")]
    [InlineData(new string[0], new[] { "Devolver Digital" }, "Open store page for Dota 2 by Devolver Digital")]
    [InlineData(new string[0], new string[0], "Open store page for Dota 2")]
    public void StoreItem_NamesDevelopersAndPublishersOnce(string[] developers, string[] publishers, string expected) =>
        Assert.Equal(expected, Menu(new PluginSettings()).Build(Game(@"C:\games\dota") with { Developers = developers, Publishers = publishers })[0].SubTitle);

    [Fact]
    public void SubtitlesNameTheGame() =>
        Assert.Equal("Open store page for Dota 2", Menu(new PluginSettings()).Build(Game(@"C:\games\dota"))[0].SubTitle);

    [Fact]
    public void SteamClientMenu_HasAllClientShortcuts()
    {
        var text = EnglishText.Translator();
        var menu = new SteamClientMenu(text, new SteamClient(null!, text));

        Assert.Equal(
        [
            "Steam: Open Library",
            "Steam: Open settings",
            "Steam: Open friends",
            "Store: Open wishlist",
            "Store: Open top sellers",
            "Store: Open specials",
        ],
        Titles(menu.Build()));
    }

    [Fact]
    public void CsRinSearch_EncodesNameLikePythonQuotePlus() =>
        Assert.Equal(
            "https://cs.rin.ru/forum/search.php?keywords=Baldur%27s+Gate+3&fid[]=10&sr=topics&sf=titleonly",
            GameContextMenu.CsRinSearchUrl(" Baldur's Gate 3 "));

    private static GameContextMenu Menu(PluginSettings settings)
    {
        var text = EnglishText.Translator();
        return new GameContextMenu(null!, text, settings, new SteamClient(null!, text), Wishlists.WithoutApi(text), Carts.WithoutAccount(text), FriendMenus.WithoutFriends(text), ProtonDbMenus.Unused(text), Smokes.Disabled(text));
    }

    private static PluginSettings AllLinks() =>
        new() { ShowCsRinContextMenu = true, ShowScreenshotsContextMenu = true, ShowPropertiesContextMenu = true };

    private static GameMenuTarget Game(string installPath, string? storeType = null, bool comingSoon = false, RefundState refund = RefundState.None) =>
        new(570, "Dota 2", installPath, storeType, comingSoon, refund);

    private static List<string> Titles(IEnumerable<Flow.Launcher.Plugin.Result> results) =>
        results.Select(result => result.Title).ToList();
}
