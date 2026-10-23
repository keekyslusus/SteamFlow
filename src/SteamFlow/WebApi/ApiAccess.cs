using SteamFlow.Library;
using SteamFlow.Steam;

namespace SteamFlow.WebApi;

public sealed record BoundKey(string Key, ulong SteamId64);

public enum ApiUnavailable
{
    None,
    NoKey,
    NoActiveAccount,
}

public sealed record ApiState(BoundKey? Bound, ApiUnavailable Reason);

public sealed class ApiAccess(ApiKeyStore keys, LocalLibrary library)
{
    // Account data is only requested with the key saved for the account signed in right now.
    public async Task<BoundKey?> CurrentAsync() => (await StateAsync()).Bound;

    public async Task<ApiState> StateAsync()
    {
        var snapshot = await library.GetAsync();
        if (snapshot.ActiveAccountId is not { } activeId)
        {
            return new ApiState(null, ApiUnavailable.NoActiveAccount);
        }

        var steamId64 = SteamAccount.ToSteamId64(activeId);
        return keys.For(steamId64) is { } key
            ? new ApiState(new BoundKey(key.Key, steamId64), ApiUnavailable.None)
            : new ApiState(null, ApiUnavailable.NoKey);
    }
}
