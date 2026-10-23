using Flow.Launcher.Plugin;
using SteamFlow.Accounts;
using SteamFlow.Friends;
using SteamFlow.Localization;
using SteamFlow.Status;
using SteamFlow.WebApi;
using SteamFlow.Wishlist;

namespace SteamFlow.Help;

public sealed class HelpResults(IPublicAPI api, Translator text)
{
    public const string Command = "?";

    private const int TopScore = 22000;

    // Only commands that exist in the C# plugin are listed; each ported command adds its entry here.
    private static readonly (string Command, string SubtitleKey, string Icon)[] Entries =
    [
        (ApiResults.Command, "steamflow_help_api_subtitle", Icons.Owned),
        (SwitchResults.Command, "steamflow_help_switch_subtitle", Icons.Community),
        (StatusResults.Command, "steamflow_help_status_subtitle", Icons.Online),
        (WishlistResults.Command, "steamflow_help_wishlist_subtitle", Icons.Wishlist),
        (FriendsResults.Command, "steamflow_help_friends_subtitle", Icons.Friends),
        ("top", "steamflow_help_top_sellers_subtitle", Icons.TopSellers),
        ("deals", "steamflow_help_specials_subtitle", Icons.Deals),
    ];

    public List<Result> Build(string actionKeyword) =>
        Entries
            .Select((entry, index) =>
            {
                var query = PluginQuery.Build(actionKeyword, entry.Command);
                return new Result
                {
                    Title = query,
                    SubTitle = text.Get(entry.SubtitleKey),
                    IcoPath = entry.Icon,
                    Score = TopScore - index,
                    Action = _ =>
                    {
                        api.ChangeQuery(query, requery: true);
                        return false;
                    },
                };
            })
            .ToList();
}
