using System.Net;
using Flow.Launcher.Plugin;
using SteamFlow.Cart;
using SteamFlow.Friends;
using SteamFlow.Localization;
using SteamFlow.ProtonDb;
using SteamFlow.Settings;
using SteamFlow.Smoke;
using SteamFlow.Steam;
using SteamFlow.Wishlist;

namespace SteamFlow.Library;

public sealed record GameMenuTarget(
    int AppId,
    string Name,
    string InstallPath,
    string? StoreType = null,
    bool ComingSoon = false,
    RefundState Refund = RefundState.None,
    bool IsOwned = false,
    bool Wishlistable = false,
    bool Purchasable = false,
    long SizeOnDisk = 0,
    IReadOnlyList<string>? Developers = null,
    IReadOnlyList<string>? Publishers = null);

public sealed class GameContextMenu(
    IPublicAPI api,
    Translator text,
    PluginSettings settings,
    SteamClient steam,
    WishlistService wishlist,
    CartService cart,
    FriendMenu friendMenu,
    ProtonDbMenu protonDb,
    SmokeApiService smokeApi)
{
    private static readonly string[] TypesWithoutCommunityLinks = ["dlc", "demo", "music", "soundtrack"];

    public List<Result> Build(GameMenuTarget game)
    {
        var installed = !string.IsNullOrEmpty(game.InstallPath);
        var communityLinks = !TypesWithoutCommunityLinks.Contains(game.StoreType ?? "");
        // Joining a friend comes first, as in the Python menu, and only for games the user can launch.
        var items = installed ? friendMenu.JoinItems(game.AppId) : [];
        items.Add(Item("steamflow_menu_store_open", StoreSubtitle(game), Icons.Steam, () => steam.OpenStorePage(game.AppId)));

        if (settings.ShowSteamDbContextMenu)
        {
            items.Add(Item("steamflow_menu_steamdb", text.Format("steamflow_menu_steamdb_subtitle", game.Name),
                Icons.SteamDb, () => api.OpenUrl($"https://steamdb.info/app/{game.AppId}/")));
        }

        if (game.Purchasable && !installed && !game.IsOwned)
        {
            AddCartItem(items, game);
        }

        if (game.Wishlistable && !installed && !game.IsOwned)
        {
            AddWishlistItem(items, game);
        }

        if (installed && settings.ShowCsRinContextMenu)
        {
            items.Add(Item("steamflow_menu_csrin", text.Format("steamflow_menu_csrin_subtitle", game.Name),
                Icons.CsRin, () => api.OpenUrl(CsRinSearchUrl(game.Name))));
        }

        if (settings.ShowProtonDbContextMenu && communityLinks && !game.ComingSoon)
        {
            // Menus of installed games are opened for everyday actions, so they do not wait for the rating.
            items.Add(protonDb.Item(game.AppId, game.Name, withRating: !installed));
        }

        if (settings.ShowGuidesContextMenu && communityLinks && !game.ComingSoon)
        {
            items.Add(Item("steamflow_menu_guides", text.Format("steamflow_menu_guides_subtitle", game.Name),
                Icons.Guides, () => steam.OpenGuides(game.AppId)));
        }

        if (settings.ShowDiscussionsContextMenu && communityLinks)
        {
            items.Add(Item("steamflow_menu_discussions", text.Format("steamflow_menu_discussions_subtitle", game.Name),
                Icons.Discussions, () => steam.OpenDiscussions(game.AppId)));
        }

        if (settings.ShowScreenshotsContextMenu && (installed || game.IsOwned))
        {
            items.Add(Item("steamflow_menu_screenshots", text.Format("steamflow_menu_screenshots_subtitle", game.Name),
                Icons.Screenshot, () => steam.OpenScreenshots(game.AppId)));
        }

        if (!installed)
        {
            if (game.IsOwned)
            {
                items.Add(Item("steamflow_menu_install", text.Format("steamflow_menu_install_subtitle", game.Name),
                    Icons.Download, () => steam.Install(game.AppId)));
            }

            return items;
        }

        if (game.Refund is RefundState.Likely)
        {
            items.Add(Item("steamflow_menu_refund_likely", text.Format("steamflow_menu_refund_likely_subtitle", game.Name),
                Icons.Refund, () => steam.OpenRefund(game.AppId)));
        }
        else if (game.Refund is RefundState.Unclear)
        {
            items.Add(Item("steamflow_menu_refund_unclear", text.Format("steamflow_menu_refund_unclear_subtitle", game.Name),
                Icons.Refund, () => steam.OpenRefund(game.AppId)));
        }

        if (settings.ShowPropertiesContextMenu)
        {
            items.Add(Item("steamflow_menu_properties", text.Format("steamflow_menu_properties_subtitle", game.Name),
                Icons.Properties, () => steam.OpenProperties(game.AppId)));
        }

        AddSmokeApiItem(items, game);
        items.Add(Item("steamflow_menu_browse_files", text.Format("steamflow_menu_browse_files_subtitle", game.Name),
            Icons.Location, () => OpenLocalFiles(game.InstallPath)));
        items.Add(Item("steamflow_menu_uninstall", UninstallSubtitle(game), Icons.Trash, () => steam.Uninstall(game.AppId)));
        return items;
    }

    private void AddSmokeApiItem(List<Result> items, GameMenuTarget game)
    {
        if (smokeApi.MenuState(game.AppId, game.InstallPath) is not { } state)
        {
            return;
        }

        if (state.Action == SmokeAction.Remove)
        {
            items.Add(new Result
            {
                Title = text.Get("steamflow_menu_smoke_remove"),
                SubTitle = text.Format("steamflow_menu_smoke_remove_subtitle", game.Name),
                IcoPath = Icons.SmokeApi,
                AsyncAction = async _ =>
                {
                    await smokeApi.RemoveAsync(game.AppId, game.InstallPath, game.Name);
                    return true;
                },
            });
            return;
        }

        items.Add(new Result
        {
            Title = text.Get("steamflow_menu_smoke_install"),
            SubTitle = state.Safety switch
            {
                SmokeSafety.Checking => text.Get("steamflow_menu_smoke_install_checking"),
                SmokeSafety.Risk => text.Format("steamflow_menu_smoke_install_anticheat", state.Signal),
                _ => text.Format("steamflow_menu_smoke_install_subtitle", game.Name),
            },
            IcoPath = Icons.SmokeApi,
            AsyncAction = async _ =>
            {
                await smokeApi.InstallAsync(game.AppId, game.InstallPath, game.Name);
                return true;
            },
        });
    }

    private void AddCartItem(List<Result> items, GameMenuTarget game)
    {
        var (available, needsSteamStart) = cart.MenuState();
        if (!available)
        {
            return;
        }

        var subtitle = text.Format("steamflow_menu_cart_add_subtitle", game.Name);
        items.Add(new Result
        {
            Title = text.Get("steamflow_menu_cart_add"),
            SubTitle = needsSteamStart ? text.Format("steamflow_menu_needs_steam_start", subtitle) : subtitle,
            IcoPath = Icons.Buy,
            AsyncAction = async _ =>
            {
                await cart.AddAsync(game.AppId, game.Name);
                return true;
            },
        });
    }

    private void AddWishlistItem(List<Result> items, GameMenuTarget game)
    {
        var (state, needsSteamStart) = wishlist.MenuState(game.AppId);
        if (state == WishlistMenuState.Unavailable)
        {
            return;
        }

        var add = state == WishlistMenuState.CanAdd;
        var subtitle = text.Format(add ? "steamflow_menu_wishlist_add_subtitle" : "steamflow_menu_wishlist_remove_subtitle", game.Name);
        if (needsSteamStart)
        {
            subtitle = text.Format("steamflow_menu_needs_steam_start", subtitle);
        }

        items.Add(new Result
        {
            Title = text.Get(add ? "steamflow_menu_wishlist_add" : "steamflow_menu_wishlist_remove"),
            SubTitle = subtitle,
            IcoPath = add ? Icons.WishlistAdd : Icons.WishlistRemove,
            AsyncAction = async _ =>
            {
                await wishlist.MutateAsync(game.AppId, game.Name, add);
                return true;
            },
        });
    }

    // A studio that publishes its own game is named once.
    private string StoreSubtitle(GameMenuTarget game)
    {
        var developers = game.Developers ?? [];
        var publishers = (game.Publishers ?? []).Where(name => !developers.Contains(name, StringComparer.OrdinalIgnoreCase)).ToList();
        if (developers.Count == 0 && publishers.Count == 0)
        {
            return text.Format("steamflow_menu_store_open_subtitle", game.Name);
        }

        var separator = text.Get("steamflow_list_separator");
        var makers = developers.Count > 0 && publishers.Count > 0
            ? text.Format("steamflow_menu_store_makers", string.Join(separator, developers), string.Join(separator, publishers))
            : string.Join(separator, developers.Count > 0 ? developers : publishers);
        return text.Format("steamflow_menu_store_open_by_subtitle", game.Name, makers);
    }

    // SizeOnDisk counts only the files Steam installed, not what the game itself wrote into its folder, so the
    // size is marked as approximate.
    private string UninstallSubtitle(GameMenuTarget game)
    {
        const long megabyte = 1L << 20;
        const long gigabyte = 1L << 30;
        var subtitle = text.Format("steamflow_menu_uninstall_subtitle", game.Name);
        return game.SizeOnDisk switch
        {
            <= 0 => subtitle,
            >= gigabyte => text.Format("steamflow_menu_uninstall_subtitle_size", subtitle,
                text.Format("steamflow_size_gb", (double)game.SizeOnDisk / gigabyte)),
            _ => text.Format("steamflow_menu_uninstall_subtitle_size", subtitle,
                text.Format("steamflow_size_mb", Math.Max(1, (double)game.SizeOnDisk / megabyte))),
        };
    }

    public static string CsRinSearchUrl(string name) =>
        $"https://cs.rin.ru/forum/search.php?keywords={WebUtility.UrlEncode(name.Trim())}&fid[]=10&sr=topics&sf=titleonly";

    private void OpenLocalFiles(string installPath)
    {
        if (Directory.Exists(installPath))
        {
            api.OpenDirectory(installPath);
        }
        else
        {
            api.ShowMsgError(text.Get("steamflow_local_files_missing"), installPath);
        }
    }

    private Result Item(string titleKey, string subtitle, string icon, Action action) => new()
    {
        Title = text.Get(titleKey),
        SubTitle = subtitle,
        IcoPath = icon,
        Action = _ =>
        {
            action();
            return true;
        },
    };
}
