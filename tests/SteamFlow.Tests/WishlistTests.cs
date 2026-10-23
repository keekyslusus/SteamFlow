using System.Text;
using SteamFlow.Localization;
using SteamFlow.Session;
using SteamFlow.WebApi;
using SteamFlow.Wishlist;

namespace SteamFlow.Tests;

public static class Wishlists
{
    // Before any query has run the service knows no bound account, so menus leave the wishlist items out.
    public static WishlistService WithoutApi(Translator text) =>
        new(null!, null!, null!, null!, TestLog.Discard(), null!, text, "", TimeProvider.System);
}

public class WishlistTests
{
    private static readonly DateTimeOffset Now = DateTimeOffset.UtcNow;

    [Theory]
    [InlineData("wishlist", "")]
    [InlineData("wishlist  hollow knight ", "hollow knight")]
    [InlineData("wishl", "")]
    [InlineData("Wishlsit elden", "elden")]
    [InlineData("wish list", "")]
    [InlineData("wish list portal", "portal")]
    [InlineData("wish", null)]
    [InlineData("dota", null)]
    public void SearchFrom_RecognizesWishlistQueries(string term, string? expected) =>
        Assert.Equal(expected, WishlistResults.SearchFrom(term));

    [Theory]
    [InlineData(200, 1, true, false)]
    [InlineData(200, 15, false, false)]
    [InlineData(200, null, false, false)]
    [InlineData(401, null, false, true)]
    [InlineData(403, 15, false, true)]
    public void Mutation_NeedsEResultOkNotJustHttp200(int status, int? eresult, bool succeeded, bool unauthorized)
    {
        var mutation = new ServiceResponse(status, eresult);

        Assert.Equal(succeeded, mutation.Succeeded);
        Assert.Equal(unauthorized, mutation.Unauthorized);
    }

    [Fact]
    public void Wishlist_ReadsAppIdsAndDates()
    {
        var items = SteamWebApi.ParseWishlist("""
            {"response":{"items":[{"appid":4115450,"priority":0,"date_added":1786617277},{"appid":"bad"}]}}
            """);

        Assert.Equal([new WishlistItem(4115450, DateTimeOffset.FromUnixTimeSeconds(1786617277))], items);
    }

    [Fact]
    public void Decode_ReadsSubjectAndExpiry()
    {
        var token = Jwt(76561198370456012, Now.AddHours(20), Now.AddHours(-4));

        var decoded = SteamSessionTokens.Decode(token);

        Assert.Equal(76561198370456012ul, decoded?.SteamId64);
        Assert.Equal(Now.AddHours(20).ToUnixTimeSeconds(), decoded?.ExpiresAt.ToUnixTimeSeconds());
        Assert.Null(SteamSessionTokens.Decode("not-a-token"));
    }

    [Fact]
    public void ExtractTokens_FindsEveryEmbeddingSteamUses()
    {
        var page = """
            {"webapi_token":"a.b.c"} &quot;webapi_token&quot;:&quot;d.e.f&quot;
            "loyalty_webapi_token" : "g.h.i" ?access_token=j-1.k_2.l3&x=1
            """;

        Assert.Equal(["a.b.c", "d.e.f", "g.h.i", "j-1.k_2.l3"], SteamSessionTokens.ExtractTokens(page));
    }

    [Fact]
    public void SelectBest_PrefersLongestLivedTokenOfTheAccount()
    {
        var tokens = new SteamSessionTokens("", "", null!, TestLog.Discard(), TimeProvider.System);
        var older = Jwt(1, Now.AddHours(2), Now.AddHours(-22));
        var newer = Jwt(1, Now.AddHours(23), Now.AddHours(-1));
        var otherAccount = Jwt(2, Now.AddHours(24), Now);
        var expired = Jwt(1, Now.AddMinutes(-1), Now.AddHours(-25));
        var almostExpired = Jwt(1, Now.AddMinutes(2), Now.AddHours(-24));

        Assert.Equal(newer, tokens.SelectBest([older, otherAccount, newer, expired], 1)?.Value);
        Assert.Null(tokens.SelectBest([otherAccount, expired, almostExpired], 1));
    }

    [Fact]
    public void SelectBest_SkipsTokenSteamRejected()
    {
        var tokens = new SteamSessionTokens("", "", null!, TestLog.Discard(), TimeProvider.System);
        var older = Jwt(1, Now.AddHours(2), Now.AddHours(-22));
        var newer = Jwt(1, Now.AddHours(23), Now.AddHours(-1));

        tokens.Reject(SteamSessionTokens.Decode(newer)!);

        Assert.Equal(older, tokens.SelectBest([older, newer], 1)?.Value);
        Assert.Null(tokens.SelectBest([newer], 1));
    }

    private static string Jwt(ulong steamId64, DateTimeOffset expires, DateTimeOffset issued)
    {
        static string Encode(string json) =>
            Convert.ToBase64String(Encoding.UTF8.GetBytes(json)).TrimEnd('=').Replace('+', '-').Replace('/', '_');

        return $"{Encode("""{"typ":"JWT","alg":"EdDSA"}""")}.{Encode($$"""{"sub":"{{steamId64}}","exp":{{expires.ToUnixTimeSeconds()}},"iat":{{issued.ToUnixTimeSeconds()}}}""")}.signature";
    }
}
