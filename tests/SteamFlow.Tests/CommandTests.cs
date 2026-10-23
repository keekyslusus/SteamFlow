using System.Text;
using SteamFlow.Help;
using SteamFlow.Library;
using SteamFlow.Store;

namespace SteamFlow.Tests;

public class CommandTests
{
    [Fact]
    public void PersonaState_IsReadFromFriendsPrefsOfActiveAccount()
    {
        const string localConfig = """
            "UserLocalConfigStore"
            {
                "WebStorage"
                {
                    "FriendStoreLocalPrefs_42"		"{\"ePersonaState\":7,\"strNonFriendsAllowedToMsg\":\"\"}"
                    "FriendStoreLocalPrefs_43"		"{\"ePersonaState\":1}"
                }
            }
            """;

        Assert.Equal(7, Parse(localConfig, 42).PersonaState);
        Assert.Null(Parse(localConfig, 44).PersonaState);
        Assert.Null(Parse(localConfig, null).PersonaState);
    }

    [Fact]
    public void PersonaState_IgnoresBrokenJson() =>
        Assert.Null(Parse("""
            "UserLocalConfigStore" { "WebStorage" { "FriendStoreLocalPrefs_42" "{oops" } }
            """, 42).PersonaState);

    [Fact]
    public void Featured_ReadsBothCollections()
    {
        const string json = """
            {"top_sellers":{"items":[{"id":4435490,"name":"Call of DutyВ®","small_capsule_image":"https://img/cod.jpg",
               "windows_available":true,"mac_available":false,"linux_available":false}]},
             "specials":{"items":[{"id":1091500,"name":"Cyberpunk 2077","windows_available":true,"mac_available":true}]}}
            """;

        var featured = StoreApi.ParseFeatured(json);

        Assert.Equal(new StoreSearchItem(4435490, "app", "Call of DutyВ®", "https://img/cod.jpg"), Assert.Single(featured.TopSellers));
        Assert.Equal(1091500, Assert.Single(featured.Get(StoreCollection.Specials)).AppId);
    }

    [Theory]
    [InlineData("stc", "stc api")]
    [InlineData("", "api")]
    public void Help_BuildsQueriesForTheActionKeyword(string keyword, string expected)
    {
        var results = new HelpResults(null!, EnglishText.Translator()).Build(keyword);

        Assert.Equal(expected, results[0].Title);
        Assert.Equal(
            [
                "Set up Steam API features & owned-game sync",
                "Switch between Steam accounts signed in on this PC",
                "Change your Steam status",
                "Browse your Steam wishlist & recent additions",
                "Search your Steam friends & open chats",
                "Browse Steam top sellers",
                "Browse Steam specials & deals",
            ],
            results.Select(result => result.SubTitle));
    }

    private static LocalConfig Parse(string text, uint? accountId) =>
        LocalConfigReader.Parse(new MemoryStream(Encoding.UTF8.GetBytes(text)), accountId);
}
