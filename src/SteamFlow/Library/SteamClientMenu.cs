using Flow.Launcher.Plugin;
using SteamFlow.Localization;
using SteamFlow.Steam;

namespace SteamFlow.Library;

public sealed class SteamClientMenu(Translator text, SteamClient steam)
{
    public List<Result> Build() =>
    [
        Item("steamflow_menu_steam_library", Icons.Steam, steam.OpenLibrary),
        Item("steamflow_menu_steam_settings", Icons.Settings, steam.OpenSettings),
        Item("steamflow_menu_steam_friends", Icons.Community, steam.OpenFriends),
        Item("steamflow_menu_steam_wishlist", Icons.Wishlist, steam.OpenWishlist),
        Item("steamflow_menu_steam_top_sellers", Icons.TopSellers, steam.OpenTopSellers),
        Item("steamflow_menu_steam_specials", Icons.Deals, steam.OpenSpecials),
    ];

    private Result Item(string key, string icon, Action action) => new()
    {
        Title = text.Get(key),
        SubTitle = text.Get(key + "_subtitle"),
        IcoPath = icon,
        Action = _ =>
        {
            action();
            return true;
        },
    };
}
