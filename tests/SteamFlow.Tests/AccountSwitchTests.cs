using System.Text;
using SteamFlow.Accounts;
using SteamFlow.Steam;

namespace SteamFlow.Tests;

public class AccountSwitchTests
{
    private const string LoginUsers = """
        "users"
        {
        	"76561198370456012"
        	{
        		"AccountName"		"main"
        		"PersonaName"		"Say \"hi\""
        		"RememberPassword"		"1"
        		"WantsOfflineMode"		"0"
        		"AutoLogin"		"1"
        		"timestamp"		"1792586984"
        	}
        	"76561198819383866"
        	{
        		"AccountName"		"alt"
        		"PersonaName"		"Alt"
        		"RememberPassword"		"0"
        		"AutoLogin"		"0"
        		"MostRecent"		"0"
        		"timestamp"		"1791843312"
        	}
        }
        """;

    [Fact]
    public void MakeAutoLogin_MovesAutoLoginToTheTarget()
    {
        var file = Parse(LoginUsers);

        Assert.True(file.MakeAutoLogin("76561198819383866"));
        var written = Parse(file.Serialize());

        Assert.Equal(
            ["AccountName=main", "PersonaName=Say \"hi\"", "RememberPassword=1", "WantsOfflineMode=0", "AutoLogin=0", "timestamp=1792586984"],
            Values(written.Serialize(), "76561198370456012"));
        Assert.Equal(
            ["AccountName=alt", "PersonaName=Alt", "RememberPassword=1", "AutoLogin=1", "MostRecent=1", "timestamp=1791843312"],
            Values(written.Serialize(), "76561198819383866"));
    }

    [Fact]
    public void MakeAutoLogin_DoesNotAddLegacyKeys()
    {
        var file = Parse(LoginUsers);

        file.MakeAutoLogin("76561198370456012");

        Assert.DoesNotContain("MostRecent", string.Join(",", Values(file.Serialize(), "76561198370456012")));
        Assert.DoesNotContain("AllowAutoLogin", file.Serialize());
    }

    [Fact]
    public void UnknownAccount_LeavesTheFileUnchanged()
    {
        var file = Parse(LoginUsers);
        var before = file.Serialize();

        Assert.False(file.MakeAutoLogin("1"));
        Assert.Equal(before, file.Serialize());
    }

    [Fact]
    public void AccountName_IsFoundForTheTarget() =>
        Assert.Equal("alt", Parse(LoginUsers).AccountName("76561198819383866"));

    private static LoginUsersFile Parse(string text) => LoginUsersFile.Parse(new MemoryStream(Encoding.UTF8.GetBytes(text)));

    // Reads one account's values back through the parser, so the check covers quoting as well as order.
    private static List<string> Values(string serialized, string steamId64)
    {
        var root = Vdf.ReadText(new MemoryStream(Encoding.UTF8.GetBytes(serialized)));
        var user = root.Items().Single(item => item.Name == steamId64);
        return user.Items().Select(value => $"{value.Name}={value.Value}").ToList();
    }
}
