using SteamFlow.Store;

namespace SteamFlow.Library;

public enum RefundState
{
    None,
    Likely,
    Unclear,
}

public static class RefundEligibility
{
    private const int RefundPlaytimeLimitMinutes = 120;

    // Steam refunds paid games played under two hours; the purchase date is checked by Steam itself.
    public static RefundState Evaluate(LibraryGame game, AppDetails? details)
    {
        if (!MayBeEligible(game) || details is not { Type: "game", IsFree: false })
        {
            return RefundState.None;
        }

        return game.Activity?.PlaytimeMinutes is null ? RefundState.Unclear : RefundState.Likely;
    }

    public static bool MayBeEligible(LibraryGame game) =>
        game.HasCurrentAccountData && game.Activity?.PlaytimeMinutes is not >= RefundPlaytimeLimitMinutes;
}
