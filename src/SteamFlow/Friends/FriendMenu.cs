using Flow.Launcher.Plugin;
using SteamFlow.Localization;
using SteamFlow.Steam;

namespace SteamFlow.Friends;

public sealed class FriendMenu(IPublicAPI flow, Translator text, FriendsService friends, SteamClient steam)
{
    public List<Result> Build(Friend friend)
    {
        var name = friend.Name.Length > 0 ? friend.Name : text.Get("steamflow_friends_unknown");
        var items = friend.GameId is { } gameId ? JoinItems(gameId, friend.SteamId64) : [];
        items.Add(Item("steamflow_menu_friend_chat", text.Format("steamflow_menu_friend_chat_subtitle", name), Icons.Chat,
            () => steam.OpenChat(friend.SteamId64)));
        items.Add(Item("steamflow_menu_friend_profile", text.Format("steamflow_menu_friend_profile_subtitle", name), Icons.Community,
            () => steam.OpenProfile(friend.SteamId64)));
        items.Add(Item("steamflow_menu_friend_trade", text.Format("steamflow_menu_friend_trade_subtitle", name), Icons.Trade,
            () => steam.OpenTradeOffer(friend.AccountId)));
        if (friend.GameId is { } appId)
        {
            var game = friend.GameName.Length > 0 ? friend.GameName : text.Get("steamflow_friends_unknown_game");
            items.Add(Item("steamflow_menu_friend_game", text.Format("steamflow_menu_friend_game_subtitle", game), Icons.Steam,
                () => steam.OpenStorePage(appId)));
        }

        return items;
    }

    // Shared with installed games: joining only makes sense for a game the user can launch.
    public List<Result> JoinItems(int appId, ulong? onlyFriend = null) =>
        friends.CachedJoinCandidates(appId, onlyFriend)
            .Select(candidate => new Result
            {
                Title = text.Format("steamflow_menu_friend_join", candidate.Name),
                SubTitle = text.Format("steamflow_menu_friend_join_subtitle", candidate.Name),
                IcoPath = Icons.JoinParty,
                AsyncAction = async _ =>
                {
                    if (await friends.ConfirmJoinAsync(candidate) is { } current)
                    {
                        steam.JoinFriendGame(current.SteamId64, current.AppId, current.LobbyId);
                    }
                    else
                    {
                        flow.ShowMsg(text.Get("steamflow_friends_title"), text.Get("steamflow_friend_join_expired"));
                    }

                    return true;
                },
            })
            .ToList();

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
