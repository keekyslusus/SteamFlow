using SteamFlow.Caching;
using SteamFlow.Library;
using SteamFlow.Store;

namespace SteamFlow.WebApi;

// Achievement progress for owned games that are not installed, where the local stats files have nothing.
public sealed class ApiAchievements(ApiAccess access, SteamWebApi api, StoreRequests requests, TimeProvider time)
{
    private readonly TimedCache<(ulong SteamId64, int AppId), AchievementProgress> progress =
        new(time, TimeSpan.FromHours(12), TimeSpan.FromHours(1));

    public async Task<AchievementProgress?> ProgressAsync(int appId)
    {
        if (await access.CurrentAsync() is not { } bound)
        {
            return null;
        }

        return await progress.GetAsync(
            (bound.SteamId64, appId),
            () => requests.Quietly("Achievements request", token => api.PlayerAchievementsAsync(bound.Key, bound.SteamId64, appId, token), $"app {appId}"));
    }
}
