using System.ComponentModel;
using System.Diagnostics;
using Flow.Launcher.Plugin;
using SteamFlow.Localization;

namespace SteamFlow.Steam;

public sealed class SteamClient(IPublicAPI api, Translator text)
{
    private const string StoreUrl = "https://store.steampowered.com";
    private const string CommunityUrl = "https://steamcommunity.com";
    private const string WishlistUrl = CommunityUrl + "/my/wishlist/";
    private const string TopSellersUrl = StoreUrl + "/search/?filter=topsellers&os=win";
    private const string SpecialsUrl = StoreUrl + "/search/?os=win&specials=1&ndl=1";

    public void OpenLibrary() => Open("steam://nav/games");

    public void OpenSettings() => Open("steam://open/settings");

    public void OpenFriends() => Open("steam://open/friends");

    public void SetStatus(string protocol) => Open($"steam://friends/status/{protocol}");

    public void OpenChat(ulong steamId64) => Open($"steam://friends/message/{steamId64}");

    public void OpenProfile(ulong steamId64) => OpenInClient($"{CommunityUrl}/profiles/{steamId64}/");

    public void OpenTradeOffer(uint accountId) => OpenInClient($"{CommunityUrl}/tradeoffer/new/?partner={accountId}");

    // A known lobby joins directly; otherwise Steam asks the friend's game how to connect.
    public void JoinFriendGame(ulong steamId64, int appId, ulong? lobbyId) =>
        Open(lobbyId is { } lobby ? $"steam://joinlobby/{appId}/{lobby}/{steamId64}" : $"steam://friends/joingame/{steamId64}");

    public void OpenApiKeyPage() => OpenInClient(CommunityUrl + "/dev/apikey");

    public void OpenAccountPreferences() => OpenInClient(StoreUrl + "/account/preferences");

    public void OpenCart() => OpenInClient(StoreUrl + "/cart");

    public void OpenLibraryDetails(int appId) => Open($"steam://nav/games/details/{appId}");

    public void Install(int appId) => Open($"steam://install/{appId}");

    public void OpenWishlist() => OpenInClient(WishlistUrl);

    public void OpenTopSellers() => OpenInClient(TopSellersUrl);

    public void OpenSpecials() => OpenInClient(SpecialsUrl);

    // The dialog form lets Steam ask which launch option to use when a game has several.
    public void LaunchGame(int appId) => Open($"steam://launch/{appId}/dialog");

    public void OpenStorePage(int appId) => Open($"steam://store/{appId}", fallbackUrl: $"{StoreUrl}/app/{appId}/");

    public void OpenGuides(int appId) => OpenInClient($"{CommunityUrl}/app/{appId}/guides/");

    public void OpenDiscussions(int appId) => OpenInClient($"{CommunityUrl}/app/{appId}/discussions/");

    public void OpenScreenshots(int appId) => Open($"steam://open/screenshots/{appId}");

    public void OpenProperties(int appId) => Open($"steam://gameproperties/{appId}");

    public void Uninstall(int appId) => Open($"steam://uninstall/{appId}");

    public void OpenRefund(int appId) =>
        OpenInClient($"https://help.steampowered.com/en/wizard/HelpWithGameIssue/?appid={appId}&issueid=108");

    private void OpenInClient(string url) => Open($"steam://openurl/{url}", fallbackUrl: url);

    // Starting a steam:// URI only fails when the protocol is not registered, i.e. Steam is not installed.
    private void Open(string uri, string? fallbackUrl = null)
    {
        try
        {
            Process.Start(new ProcessStartInfo(uri) { UseShellExecute = true });
        }
        catch (Win32Exception) when (fallbackUrl is not null)
        {
            api.OpenUrl(fallbackUrl);
        }
        catch (Win32Exception ex)
        {
            api.ShowMsgError(text.Get("steamflow_steam_open_failed"), ex.Message);
        }
    }
}
