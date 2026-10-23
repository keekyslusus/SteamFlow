using System.Net;
using System.Windows.Controls;
using Flow.Launcher.Plugin;
using SteamFlow.Accounts;
using SteamFlow.Cart;
using SteamFlow.Diagnostics;
using SteamFlow.Downloads;
using SteamFlow.Friends;
using SteamFlow.Help;
using SteamFlow.Library;
using SteamFlow.Localization;
using SteamFlow.ProtonDb;
using SteamFlow.Session;
using SteamFlow.Settings;
using SteamFlow.Smoke;
using SteamFlow.Status;
using SteamFlow.Steam;
using SteamFlow.Store;
using SteamFlow.WebApi;
using SteamFlow.Wishlist;

namespace SteamFlow;

public sealed record PluginServices(
    QueryHandler Queries,
    LocalLibrary Library,
    StoreCatalog Store,
    StoreImages StoreImages,
    OwnedGamesService OwnedGames,
    ProfileService Profile,
    WishlistService Wishlist,
    HttpClient Http,
    Func<Control> CreateSettingsPanel) : IDisposable
{
    public void Dispose()
    {
        Library.Dispose();
        Http.Dispose();
    }
}

public static class CompositionRoot
{
    private static readonly TimeSpan LibraryReloadDelay = TimeSpan.FromSeconds(2);

    public static PluginServices Create(PluginInitContext context)
    {
        var api = context.API;
        var metadata = context.CurrentPluginMetadata;
        var time = TimeProvider.System;
        var log = new PluginLog(Path.Combine(metadata.PluginCacheDirectoryPath, "steamflow.log"), time);

        // The Python plugin kept its settings, key and session token in a "SteamFlow" folder next to this plugin's own.
        var legacySettings = Path.Combine(
            Path.GetDirectoryName(Path.TrimEndingDirectorySeparator(metadata.PluginSettingsDirectoryPath))!, "SteamFlow");
        var settings = LoadSettings(api, metadata, legacySettings, log);
        var text = new Translator(api.GetTranslation);
        var requests = new StoreRequests(log);
        var steam = new SteamClient(api, text);
        var users = new SteamUsers(log);
        var http = CreateHttpClient(log, time);
        var storeApi = new StoreApi(http);
        var catalog = new StoreCatalog(storeApi, requests, text, log, time);
        var storeImages = new StoreImages(
            storeApi,
            requests,
            new StoreImageCache(Path.Combine(metadata.PluginCacheDirectoryPath, "store-images"), time));

        var loader = new LibraryLoader(
            new SteamInstallation(),
            users,
            new InstalledGamesReader(log),
            new LocalConfigReader(log),
            new HiddenGamesReader(log),
            new AchievementsReader(log),
            new GameIconLocator(),
            log);
        var library = new LocalLibrary(loader, users, new LibraryWatcher(LibraryReloadDelay));

        var apiKeys = new ApiKeyStore(metadata.PluginSettingsDirectoryPath, legacySettings, log);
        apiKeys.ImportLegacy();
        var sessionTokens = new SteamSessionTokens(metadata.PluginSettingsDirectoryPath, legacySettings, steam, log, time);
        sessionTokens.ImportLegacy();
        var webApi = new SteamWebApi(http);
        var apiAccess = new ApiAccess(apiKeys, library);
        var ownedGames = new OwnedGamesService(
            apiAccess,
            webApi,
            Path.Combine(metadata.PluginCacheDirectoryPath, "owned_games"),
            log,
            time);
        var profile = new ProfileService(
            apiAccess,
            webApi,
            requests,
            new AvatarComposer(),
            Path.Combine(metadata.PluginCacheDirectoryPath, "avatar"),
            log,
            time);
        var wishlist = new WishlistService(apiAccess, webApi, sessionTokens, requests, log, api, text, metadata.PluginDirectory, time);
        var cart = new CartService(new CartApi(http), sessionTokens, library, catalog, steam, api, text, log, metadata.PluginDirectory);
        var friendsApi = new FriendsApi(http);
        var friends = new FriendsService(apiAccess, friendsApi, sessionTokens, requests, log, time);
        var friendMenu = new FriendMenu(api, text, friends, steam);
        var downloadStatuses = new DownloadStatuses(new ContentLog(), new SteamInstallation());
        var clientComm = new ClientCommApi(http);
        var smokeApi = new SmokeApiService(
            new SmokeApiFiles(),
            new AntiCheatScanner(),
            new SmokePayload(Path.Combine(metadata.PluginCacheDirectoryPath, "smokeapi")),
            settings,
            api,
            text,
            time,
            log,
            metadata.PluginDirectory);
        var protonDb = new ProtonDbMenu(api, text, new ProtonDbApi(http), requests, time);
        var gameMenu = new GameContextMenu(api, text, settings, steam, wishlist, cart, friendMenu, protonDb, smokeApi);
        var libraryResults = new LibraryResults(
            api,
            text,
            settings,
            library,
            new LibrarySubtitles(text, settings, time),
            gameMenu,
            new SteamClientMenu(text, steam),
            catalog,
            ownedGames,
            profile,
            friends,
            smokeApi,
            downloadStatuses,
            new DownloadProgress(clientComm, sessionTokens, requests, library, time),
            new DownloadControl(clientComm, sessionTokens, library, downloadStatuses, api, text, log, metadata.PluginDirectory),
            steam);
        var storeResults = new StoreResults(
            text,
            settings,
            catalog,
            storeImages,
            new StoreSubtitles(text, settings),
            gameMenu,
            ownedGames,
            new ApiAchievements(apiAccess, webApi, requests, time),
            steam,
            log);

        return new PluginServices(
            new QueryHandler(
                api,
                text,
                libraryResults,
                storeResults,
                new StatusResults(api, text, library, steam),
                new ApiResults(api, text, apiKeys, ownedGames, library, steam, log, metadata.PluginDirectory, time),
                new WishlistResults(api, text, wishlist, catalog, storeResults, time),
                new SwitchResults(text, library, new SteamInstallation(), users, new AccountSwitcher(new SteamInstallation(), library, steam, api, text, log)),
                new FriendsResults(api, text, friends, new FriendPresence(friendsApi, requests, text, time), friendMenu, steam, time),
                new HelpResults(api, text),
                log),
            library,
            catalog,
            storeImages,
            ownedGames,
            profile,
            wishlist,
            http,
            () => new SettingsPanel(settings, api.SaveSettingJsonStorage<PluginSettings>));
    }

    // Flow names the file after the settings type; without one this is the first start, e.g. right after the
    // update from the Python plugin.
    private static PluginSettings LoadSettings(IPublicAPI api, PluginMetadata metadata, string legacySettings, PluginLog log)
    {
        var firstStart = !File.Exists(Path.Combine(metadata.PluginSettingsDirectoryPath, nameof(PluginSettings) + ".json"));
        var settings = api.LoadSettingJsonStorage<PluginSettings>();
        if (firstStart && LegacySettings.Import(settings, Path.Combine(legacySettings, "Settings.json"), log))
        {
            api.SaveSettingJsonStorage<PluginSettings>();
        }

        return settings;
    }

    // Cookies are read by hand (Steam's region cookie), so the handler must not swallow Set-Cookie headers.
    private static HttpClient CreateHttpClient(PluginLog log, TimeProvider time) =>
        new(new StorePause(log, time)
        {
            InnerHandler = new SocketsHttpHandler
            {
                UseCookies = false,
                AutomaticDecompression = DecompressionMethods.All,
                PooledConnectionLifetime = TimeSpan.FromMinutes(10),
            },
        })
        {
            DefaultRequestHeaders = { { "User-Agent", "Mozilla/5.0" } },
        };
}
