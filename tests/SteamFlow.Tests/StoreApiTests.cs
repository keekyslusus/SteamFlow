using SteamFlow.Store;

namespace SteamFlow.Tests;

public class StoreApiTests
{
    [Fact]
    public void CountryCookie_IsSteamsGeolocatedRegion() =>
        Assert.Equal("kz", StoreApi.ParseCountryCookie(
        [
            "browserid=589567037491607648; path=/",
            "steamCountry=KZ%7C12d59c6a1348122b8cec454833db9d2e; path=/; secure; HttpOnly",
        ]));

    [Fact]
    public void CountryCookie_MissingOrMalformedGivesNull()
    {
        Assert.Null(StoreApi.ParseCountryCookie(["sessionid=1; path=/"]));
        Assert.Null(StoreApi.ParseCountryCookie(["steamCountry=%7Cabc; path=/"]));
    }

    [Fact]
    public void Search_ReadsItems()
    {
        const string json = """
            {"total":2,"items":[
              {"type":"app","name":"Enter the Gungeon","id":311690,"price":{"currency":"KZT","initial":410000,"final":82000},
               "tiny_image":"https://img/311690.jpg"},
              {"type":"sub","name":"Bundle","id":"oops"}
            ]}
            """;

        var item = Assert.Single(StoreApi.ParseSearch(json));
        Assert.Equal(new StoreSearchItem(311690, "app", "Enter the Gungeon", "https://img/311690.jpg"), item);
    }

    [Fact]
    public void AppDetails_ReadsTypeFreeAndRelease()
    {
        const string json = """
            {"2339840":{"success":true,"data":{"type":"game","name":"Enter the Gungeon 2","is_free":false,
              "capsule_image":"https://img/capsule.jpg",
              "release_date":{"coming_soon":true,"date":"To be announced"}}}}
            """;

        var details = StoreApi.ParseAppDetails(json, 2339840)!;

        Assert.Equal(
            new AppDetails("game", "Enter the Gungeon 2", false, true, "To be announced", "https://img/capsule.jpg"),
            details with { Developers = null, Publishers = null });
        Assert.Empty(details.Developers!);
        Assert.Empty(details.Publishers!);
    }

    [Fact]
    public void AppDetails_ReadsDevelopersAndPublishers()
    {
        const string json = """
            {"1282730":{"success":true,"data":{"type":"game","name":"Loop Hero",
              "developers":["Four Quarters", " ", "four quarters"],"publishers":["Devolver Digital", 5]}}}
            """;

        var details = StoreApi.ParseAppDetails(json, 1282730)!;

        Assert.Equal(["Four Quarters"], details.Developers!);
        Assert.Equal(["Devolver Digital"], details.Publishers!);
    }

    [Fact]
    public void AppDetails_UnsuccessfulGivesNull() =>
        Assert.Null(StoreApi.ParseAppDetails("""{"1":{"success":false}}""", 1));

    [Fact]
    public void Prices_SkipAppsWithoutPriceOverview()
    {
        const string json = """
            {"311690":{"success":true,"data":{"price_overview":{"currency":"KZT","initial":410000,"final":82000,
              "discount_percent":80,"final_formatted":"820₸"}}},
             "570":{"success":true,"data":[]}}
            """;

        var prices = StoreApi.ParsePrices(json);

        Assert.Equal(new StorePrice("820₸", 80), Assert.Single(prices).Value);
    }

    [Fact]
    public void Reviews_ReadFilteredSummary() =>
        Assert.Equal(
            new ReviewSummary(88, 115890),
            StoreApi.ParseReviews(
                """{"response":{"store_items":[{"appid":524220,"success":1,"reviews":{"summary_filtered":{"review_count":115890,"percent_positive":88,"review_score":8},"summary_language_specific":{"review_count":50749,"percent_positive":90,"review_score":8}}}]}}"""));

    [Theory]
    [InlineData("""{"response":{}}""")]
    [InlineData("""{"response":{"store_items":[{"appid":0,"success":15}]}}""")]
    public void Reviews_MissingSummaryIsNull(string json) => Assert.Null(StoreApi.ParseReviews(json));

    [Fact]
    public void Players_RequireSuccessfulResult()
    {
        Assert.Equal(new PlayerCount(683), StoreApi.ParsePlayers("""{"response":{"player_count":683,"result":1}}"""));
        Assert.Null(StoreApi.ParsePlayers("""{"response":{"result":42}}"""));
    }
}
