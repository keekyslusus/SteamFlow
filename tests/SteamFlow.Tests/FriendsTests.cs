using SteamFlow.Friends;
using SteamFlow.Library;
using SteamFlow.Localization;
using SteamFlow.Settings;
using SteamFlow.Steam;
using SteamFlow.Store;

namespace SteamFlow.Tests;

public static class FriendMenus
{
    // Before any friends query the service knows no account, so menus offer no join items.
    public static FriendMenu WithoutFriends(Translator text) =>
        new(null!, text, new FriendsService(null!, null!, null!, null!, TestLog.Discard(), TimeProvider.System), new SteamClient(null!, text));
}

public class FriendsTests
{
    [Fact]
    public void Summaries_ReadPresenceGameAndJoinHints()
    {
        const string json = """
            {"response":{"players":[
              {"steamid":"76561198000000001","personaname":"Alex","personastate":1,"avatarmedium":"https://a/1.jpg",
               "gameid":"570","gameextrainfo":"Dota 2","lobbysteamid":"109775241","lastlogoff":1700000000},
              {"steamid":"76561198000000002","personaname":"Mod","personastate":1,"gameid":"13238412589130006528","gameextrainfo":"Some Mod",
               "gameserverip":"1.2.3.4:27015"},
              {"steamid":"76561198000000003","personaname":"Off","personastate":0}
            ]}}
            """;

        var friends = FriendsApi.ParseSummaries(json);

        Assert.Equal(new Friend(76561198000000001, "Alex", "https://a/1.jpg", 1, DateTimeOffset.FromUnixTimeSeconds(1700000000), 570, "Dota 2", 109775241, false), friends[0]);
        Assert.Null(friends[1].GameId);
        Assert.True(friends[1].HasServer);
        Assert.Equal(Presence.Playing, friends[1].Presence);
        Assert.Equal(Presence.Offline, friends[2].Presence);
    }

    [Fact]
    public void FriendIds_RequireAFriendList()
    {
        Assert.Equal([76561198000000001ul], FriendsApi.ParseFriendIds("""{"friendslist":{"friends":[{"steamid":"76561198000000001","relationship":"friend"}]}}"""));
        Assert.Throws<FriendsListUnavailableException>(() => FriendsApi.ParseFriendIds("{}"));
    }

    [Fact]
    public void Favorites_AreAccountIds() =>
        Assert.Equal(new HashSet<uint> { 39794284 }, FriendsApi.ParseFavorites("""{"response":{"favorites":[{"accountid":39794284}]}}"""));

    [Fact]
    public void JoinDetails_NeedAConnectStringLobbyOrServer()
    {
        const string json = """
            {"response":{"accounts":[
              {"public_data":{"steamid":"1"},"private_data":{"game_id":"570","rich_presence_kv":"\"rp\"{\"connect\"\t\"+gid:1\"}"}},
              {"public_data":{"steamid":"2"},"private_data":{"game_id":"570","lobby_steam_id":"55"}},
              {"public_data":{"steamid":"3"},"private_data":{"game_id":"570","lobby_steam_id":"55","game_is_private":true}},
              {"public_data":{"steamid":"4"},"private_data":{"game_id":"570"}},
              {"public_data":{"steamid":"5"},"private_data":{"persona_state":1}}
            ]}}
            """;

        var details = FriendsApi.ParseJoinDetails(json);

        Assert.True(details[1].Joinable);
        Assert.Equal(new JoinDetails(570, true, 55), details[2]);
        Assert.False(details[3].Joinable);
        Assert.False(details[4].Joinable);
        Assert.False(details.ContainsKey(5));
    }

    [Fact]
    public void Candidates_UsePublicHintsThenPrivateDetails()
    {
        var friends = new[]
        {
            Friend(1, "Zed", gameId: 570, lobby: 9),
            Friend(2, "Amy", gameId: 570),
            Friend(3, "Bob", gameId: 570),
            Friend(4, "Cat", gameId: 730, lobby: 7),
        };
        var details = new Dictionary<ulong, JoinDetails> { [2] = new(570, true, null), [3] = new(570, false, null) };

        var candidates = FriendsService.Candidates(friends, details, 570, null);

        Assert.Equal([new JoinCandidate(2, "Amy", 570, null), new JoinCandidate(1, "Zed", 570, 9)], candidates);
        Assert.Empty(FriendsService.Candidates(friends, details, 570, onlyFriend: 3));
    }

    [Fact]
    public void Sort_RanksNameMatchesThenFavoritesThenPresence()
    {
        var friends = new[]
        {
            Friend(1, "Offline Ann", state: 0),
            Friend(2, "Ann", state: 1),
            Friend(3, "Bob", state: 3),
            Friend(4, "Carl", gameId: 570, game: "Annoying Game"),
            Friend(5, "Dan", state: 1),
        };

        Assert.Equal([2, 1, 4], FriendsResults.Sort(friends, "ann", new HashSet<uint>()).Select(friend => (int)friend.SteamId64));
        Assert.Equal([3, 4, 2, 5, 1], FriendsResults.Sort(friends, "", new HashSet<uint> { 3 }).Select(friend => (int)friend.SteamId64));
    }

    [Theory]
    [InlineData("friends", "")]
    [InlineData("friend alex", "alex")]
    [InlineData("Friends  dota ", "dota")]
    [InlineData("friendly", null)]
    public void SearchFrom_RecognizesFriendsQueries(string term, string? expected) =>
        Assert.Equal(expected, FriendsResults.SearchFrom(term));

    [Fact]
    public void EmptyQuery_NamesOneFriendAndCountsSeveral()
    {
        var subtitles = new LibrarySubtitles(EnglishText.Translator(), new PluginSettings(), TimeProvider.System);
        var game = new LibraryGame(570, "Dota 2", @"C:\dota", null, null, null, HasCurrentAccountData: true);

        Assert.Equal("Launch game | Alex is playing", subtitles.Build(game, false, friendsPlaying: ["Alex"]));
        Assert.Equal("Launch game | 3 friends are playing", subtitles.Build(game, false, friendsPlaying: ["A", "B", "C"]));
    }

    [Fact]
    public void RichPresence_IsTheMiniProfileGameStatus()
    {
        Assert.Equal("-$7 147 Loss", FriendsApi.ParseRichPresence("""
            {"persona_name":"Bashai","in_game":{"name":"WARDOGS","is_non_steam":false,"rich_presence":" -$7 147\n Loss "}}
            """));
        Assert.Equal("", FriendsApi.ParseRichPresence("""{"persona_name":"Bashai","in_game":{"name":"WARDOGS"}}"""));
        Assert.Equal("", FriendsApi.ParseRichPresence("""{"persona_name":"Bashai"}"""));
    }

    [Fact]
    public async Task Presence_IsAskedOnlyForFriendsInGameAndCachedPerGame()
    {
        var steam = new StubHandler(System.Net.HttpStatusCode.OK, """{"in_game":{"name":"Dota 2","rich_presence":"Turbo: Lvl 25 Wraith King"}}""");
        var text = EnglishText.Translator();
        var presence = new FriendPresence(new FriendsApi(new HttpClient(steam)), new StoreRequests(TestLog.Discard()), text, TimeProvider.System);
        Friend[] friends = [Friend(1, "Bashai", gameId: 570), Friend(2, "Offline", state: 0), Friend(3, "Online")];

        var first = presence.Load(friends);
        Assert.Equal("Turbo: Lvl 25 Wraith King", await Assert.Single(first).Value);
        var again = presence.Load(friends);
        var otherGame = presence.Load([Friend(1, "Bashai", gameId: 730)]);
        await Task.WhenAll(again.Values.Concat(otherGame.Values));

        Assert.True(again[1].IsCompletedSuccessfully);
        Assert.Equal(2, steam.Requests);
    }

    private static Friend Friend(ulong id, string name, int state = 1, int? gameId = null, string game = "", ulong? lobby = null) =>
        new(id, name, null, state, null, gameId, game.Length > 0 ? game : gameId is null ? "" : "Game", lobby, false);
}
