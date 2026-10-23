using SteamFlow.Cart;
using SteamFlow.Library;
using SteamFlow.Localization;

namespace SteamFlow.Tests;

public static class Carts
{
    // A library that has not loaded yet has no active account, so menus leave the cart item out.
    public static CartService WithoutAccount(Translator text) =>
        new(null!, null!, new LocalLibrary(null!, null!, null!), null!, null!, null!, text, TestLog.Discard(), "");
}

public class CartTests
{
    [Fact]
    public void Package_PrefersTheDefaultPurchaseGroup()
    {
        const string json = """
            {"311690":{"success":true,"data":{"packages":[700904,46873],"package_groups":[
              {"name":"subscriptions","subs":[{"packageid":999}]},
              {"name":"default","subs":[{"packageid":46873,"price_in_cents_with_discount":82000},{"packageid":700904}]}
            ]}}}
            """;

        Assert.Equal(46873, CartApi.ParsePackage(json, 311690));
    }

    [Fact]
    public void Package_FallsBackToPackageList() =>
        Assert.Equal(700904, CartApi.ParsePackage("""{"1":{"success":true,"data":{"packages":[700904]}}}""", 1));

    [Fact]
    public void Package_MissingForFreeOrUnknownApps()
    {
        Assert.Null(CartApi.ParsePackage("""{"1":{"success":true,"data":{}}}""", 1));
        Assert.Null(CartApi.ParsePackage("""{"1":{"success":false}}""", 1));
    }

    [Fact]
    public void CartPackages_AcceptNumbersAndStrings()
    {
        const string json = """
            {"response":{"cart":{"line_items":[{"line_item_id":"123","packageid":46873},{"packageid":"700904"},{"bundleid":5}],"is_valid":true}}}
            """;

        Assert.Equal(new HashSet<int> { 46873, 700904 }, CartApi.ParseCartPackages(json));
    }

    [Fact]
    public void EmptyCart_HasNoPackages() =>
        Assert.Empty(CartApi.ParseCartPackages("""{"response":{"cart":{"subtotal":{"amount_in_cents":"0"},"is_valid":true}}}"""));
}
