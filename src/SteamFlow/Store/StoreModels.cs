namespace SteamFlow.Store;

public sealed record StoreSearchItem(int AppId, string Type, string Name, string? CapsuleUrl = null);

public sealed record AppDetails(
    string Type,
    string Name,
    bool? IsFree,
    bool ComingSoon,
    string ReleaseDate,
    string? CapsuleUrl = null,
    IReadOnlyList<string>? Developers = null,
    IReadOnlyList<string>? Publishers = null);

public sealed record StorePrice(string Final, int DiscountPercent);

public sealed record ReviewSummary(int PercentPositive, int ReviewCount);

public sealed record PlayerCount(int Value);

public enum StoreCollection
{
    TopSellers,
    Specials,
}

public sealed record FeaturedCollections(IReadOnlyList<StoreSearchItem> TopSellers, IReadOnlyList<StoreSearchItem> Specials)
{
    public IReadOnlyList<StoreSearchItem> Get(StoreCollection collection) =>
        collection == StoreCollection.TopSellers ? TopSellers : Specials;
}
