using System.Security.Cryptography;
using System.Text;
using SteamFlow.Library;
using SteamFlow.Settings;
using SteamFlow.Steam;
using SteamFlow.Store;
using SteamFlow.WebApi;

namespace SteamFlow.Tests;

public sealed class WebApiTests : IDisposable
{
    private const string Key = "0123456789abcdef0123456789ABCDEF";

    private readonly string root = Path.Combine(Path.GetTempPath(), "steamflow-tests-" + Guid.NewGuid().ToString("N"));

    private string Folder => Path.Combine(root, "Flow.Launcher.Plugin.SteamFlow");

    private string LegacyFolder => Path.Combine(root, "SteamFlow");

    [Theory]
    [InlineData(" 0123456789abcdef0123456789ABCDEF \n", "0123456789ABCDEF0123456789ABCDEF")]
    [InlineData("0123456789abcdef0123456789ABCDE", null)]
    [InlineData("0123456789abcdef0123456789ABCDEG", null)]
    [InlineData(null, null)]
    public void Normalize_AcceptsOnly32HexCharacters(string? input, string? expected) =>
        Assert.Equal(expected, ApiKeyStore.Normalize(input));

    [Fact]
    public void SavedKey_RoundTripsThroughDpapi()
    {
        var account = new SteamAccount(76561198370456012, "login", "Persona", true, 0);
        new ApiKeyStore(Folder, LegacyFolder, TestLog.Discard()).Save(Key.ToUpperInvariant(), account);

        var loaded = new ApiKeyStore(Folder, LegacyFolder, TestLog.Discard()).For(76561198370456012);

        Assert.Equal(new StoredApiKey(Key.ToUpperInvariant(), 76561198370456012, "Persona", "login"), loaded);
        Assert.DoesNotContain(Key.ToUpperInvariant(), File.ReadAllText(Path.Combine(Folder, "owned_api_keys.bin")));
    }

    [Fact]
    public void Keys_AreKeptPerAccount()
    {
        const string otherKey = "FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF";
        var store = new ApiKeyStore(Folder, LegacyFolder, TestLog.Discard());
        store.Save(Key.ToUpperInvariant(), new SteamAccount(76561198370456012, "first", "", false, 0));
        store.Save(otherKey, new SteamAccount(76561198000000001, "second", "", false, 0));

        var reloaded = new ApiKeyStore(Folder, LegacyFolder, TestLog.Discard());

        Assert.Equal(Key.ToUpperInvariant(), reloaded.For(76561198370456012)?.Key);
        Assert.Equal(otherKey, reloaded.For(76561198000000001)?.Key);
        Assert.Null(reloaded.For(76561198000000002));
        Assert.Equal(2, reloaded.All().Count);
    }

    [Fact]
    public void ImportLegacy_CopiesPythonKeyAndKeepsTheOriginal()
    {
        WriteSingleKey(LegacyFolder, 76561198370456012);
        var store = new ApiKeyStore(Folder, LegacyFolder, TestLog.Discard());

        store.ImportLegacy();

        Assert.Equal(Key.ToUpperInvariant(), store.For(76561198370456012)?.Key);
        Assert.Equal("Persona", store.For(76561198370456012)?.PersonaName);
        Assert.True(File.Exists(Path.Combine(LegacyFolder, "owned_api_key.bin")));
    }

    [Fact]
    public void ImportLegacy_MovesTheSingleKeyOfAnEarlierBuild()
    {
        WriteSingleKey(Folder, 76561198370456012);
        var store = new ApiKeyStore(Folder, LegacyFolder, TestLog.Discard());

        store.ImportLegacy();

        Assert.Equal(Key.ToUpperInvariant(), new ApiKeyStore(Folder, LegacyFolder, TestLog.Discard()).For(76561198370456012)?.Key);
        Assert.False(File.Exists(Path.Combine(Folder, "owned_api_key.bin")));
    }

    [Fact]
    public void Remove_ForgetsOnlyThatAccountsKey()
    {
        var store = new ApiKeyStore(Folder, LegacyFolder, TestLog.Discard());
        store.Save(Key.ToUpperInvariant(), new SteamAccount(76561198370456012, "", "", false, 0));
        store.Save(Key.ToUpperInvariant(), new SteamAccount(76561198000000001, "", "", false, 0));

        store.Remove(76561198370456012);

        Assert.Null(store.For(76561198370456012));
        Assert.Null(new ApiKeyStore(Folder, LegacyFolder, TestLog.Discard()).For(76561198370456012));
        Assert.NotNull(new ApiKeyStore(Folder, LegacyFolder, TestLog.Discard()).For(76561198000000001));
    }

    [Fact]
    public void Remove_OfTheLastKeyDoesNotBringBackThePythonKey()
    {
        WriteSingleKey(LegacyFolder, 76561198370456012);
        var store = new ApiKeyStore(Folder, LegacyFolder, TestLog.Discard());
        store.ImportLegacy();

        store.Remove(76561198370456012);
        var restarted = new ApiKeyStore(Folder, LegacyFolder, TestLog.Discard());
        restarted.ImportLegacy();

        Assert.Empty(restarted.All());
    }

    // The Python plugin's layout: a DPAPI-protected key plus plain JSON metadata naming the bound account.
    private static void WriteSingleKey(string folder, ulong steamId64)
    {
        Directory.CreateDirectory(folder);
        File.WriteAllBytes(
            Path.Combine(folder, "owned_api_key.bin"),
            ProtectedData.Protect(
                Encoding.UTF8.GetBytes(Key),
                "SteamFlow-OwnedGames-Key-v1"u8.ToArray(),
                DataProtectionScope.CurrentUser));
        File.WriteAllText(
            Path.Combine(folder, "owned_api_key.meta.json"),
            $$"""{"bound_steamid64":"{{steamId64}}","persona_name":"Persona","account_name":"login"}""");
    }

    [Fact]
    public void OwnedGames_ReadAppIdsAndPlaytime()
    {
        var games = SteamWebApi.ParseOwnedGames("""
            {"response":{"game_count":2,"games":[{"appid":570,"playtime_forever":85691},{"appid":311690}]}}
            """);

        Assert.Equal(new HashSet<int> { 570, 311690 }, games.AppIds);
        Assert.Equal(85691, games.PlaytimeMinutes[570]);
        Assert.Equal(0, games.PlaytimeMinutes[311690]);
    }

    [Fact]
    public void PlayerSummary_ReadsStateAndCurrentGame()
    {
        Assert.Equal(
            new ProfileSummary(1, "Dota 2"),
            SteamWebApi.ParsePlayerSummary("""{"response":{"players":[{"personaname":"x","personastate":1,"gameextrainfo":" Dota 2 "}]}}"""));
        Assert.Null(SteamWebApi.ParsePlayerSummary("""{"response":{"players":[]}}"""));
    }

    [Fact]
    public void AvatarFrame_ResolvesCommunityAssetUrl()
    {
        Assert.Equal(
            new AvatarFrame("17153269771", "https://shared.fastly.steamstatic.com/community_assets/images/items/527230/18ec.png"),
            SteamWebApi.ParseAvatarFrame("""{"response":{"avatar_frame":{"communityitemid":"17153269771","image_small":"items/527230/18ec.png","image_large":"items/527230/00c0.png"}}}"""));
        Assert.Null(SteamWebApi.ParseAvatarFrame("""{"response":{}}"""));
    }

    [Fact]
    public void PlayerAchievements_CountUnlockedOutOfAll() =>
        Assert.Equal(
            new AchievementProgress(2, 3),
            SteamWebApi.ParsePlayerAchievements("""{"playerstats":{"achievements":[{"achieved":1},{"achieved":0},{"achieved":1}]}}"""));

    [Fact]
    public void OwnedStoreResult_ShowsApiAchievements()
    {
        var item = new StoreSearchItem(311690, "app", "Enter the Gungeon");
        var data = new StoreItemData(item, null, null, null, null, null, IsOwned: true, OwnedPlaytimeMinutes: 7167, OwnedAchievements: new AchievementProgress(43, 54));

        Assert.Equal(
            "Open in Library | 119.5h | 43/54",
            new StoreSubtitles(EnglishText.Translator(), new PluginSettings()).Build(data));
    }

    [Fact]
    public void OwnedView_OnlyClaimsNotOwnedWhenTheListIsFresh()
    {
        var games = new OwnedGames(new HashSet<int> { 570 }, new Dictionary<int, int>());

        Assert.Equal(Ownership.Owned, new OwnedView(true, false, games, null).StateOf(570));
        Assert.Equal(Ownership.Unknown, new OwnedView(true, false, games, null).StateOf(10));
        Assert.Equal(Ownership.NotOwned, new OwnedView(true, true, games, null).StateOf(10));
        Assert.Equal(Ownership.Unknown, OwnedView.None.StateOf(570));
    }

    [Fact]
    public void LocalNotice_NamesAnotherAccountOnlyForPaidGamesWithoutLocalData()
    {
        var subtitles = new LibrarySubtitles(EnglishText.Translator(), new PluginSettings(), TimeProvider.System);
        var foreign = new LibraryGame(1, "Game", @"C:\g", null, null, null, HasCurrentAccountData: false);

        Assert.Equal("Launch game | Installed via another account", subtitles.Build(foreign, false, ownership: Ownership.NotOwned));
        Assert.Equal("Launch game", subtitles.Build(foreign, false, ownership: Ownership.NotOwned, isFree: true));
        Assert.Equal("Launch game", subtitles.Build(foreign, true, ownership: Ownership.Owned));
        Assert.Equal("Launch game | No current-account data", subtitles.Build(foreign, true, ownership: Ownership.Unknown));
    }

    [Fact]
    public void OwnedStoreResult_ShowsPlaytimeInsteadOfPrice()
    {
        var item = new StoreSearchItem(570, "app", "Dota 2");
        var data = new StoreItemData(item, null, new StorePrice("1 000₸", 0), null, null, null, IsOwned: true, OwnedPlaytimeMinutes: 90);

        Assert.Equal(
            "Open in Library | 1.5h",
            new StoreSubtitles(EnglishText.Translator(), new PluginSettings()).Build(data));
    }

    [Fact]
    public void OwnedButNotInstalled_OffersScreenshotsAndInstall()
    {
        var text = EnglishText.Translator();
        var settings = new PluginSettings { ShowScreenshotsContextMenu = true };
        var menu = new GameContextMenu(null!, text, settings, new SteamClient(null!, text), Wishlists.WithoutApi(text), Carts.WithoutAccount(text), FriendMenus.WithoutFriends(text), ProtonDbMenus.Unused(text), Smokes.Disabled(text));

        var titles = menu.Build(new GameMenuTarget(570, "Dota 2", "", IsOwned: true)).Select(result => result.Title).ToList();

        Assert.Equal(["Library: Open recordings & screenshots", "Library: Install game"], titles[^2..]);
    }

    public void Dispose()
    {
        if (Directory.Exists(root))
        {
            Directory.Delete(root, recursive: true);
        }
    }
}
