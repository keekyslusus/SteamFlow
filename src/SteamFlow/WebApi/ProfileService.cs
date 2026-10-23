using System.Globalization;
using System.Text.Json;
using SteamFlow.Caching;
using SteamFlow.Diagnostics;
using SteamFlow.Store;

namespace SteamFlow.WebApi;

public sealed class ProfileService
{
    private static readonly TimeSpan FrameLifetime = TimeSpan.FromHours(24);

    private readonly ApiAccess access;
    private readonly SteamWebApi api;
    private readonly StoreRequests requests;
    private readonly AvatarComposer composer;
    private readonly PluginLog log;
    private readonly string cacheFolder;
    private readonly TimeProvider time;
    private readonly TimedCache<ulong, ProfileSummary> summaries;
    private readonly Lock gate = new();
    private readonly Dictionary<ulong, DateTimeOffset> frameChecks = [];

    public ProfileService(
        ApiAccess access,
        SteamWebApi api,
        StoreRequests requests,
        AvatarComposer composer,
        string cacheFolder,
        PluginLog log,
        TimeProvider time)
    {
        this.access = access;
        this.api = api;
        this.requests = requests;
        this.composer = composer;
        this.log = log;
        this.cacheFolder = cacheFolder;
        this.time = time;
        // The status follows what the user does in Steam, so it goes stale quickly.
        summaries = new(time, TimeSpan.FromSeconds(30), TimeSpan.FromMinutes(1));
    }

    public void WarmUp() => _ = Task.Run(async () =>
    {
        if (await access.CurrentAsync() is { } bound)
        {
            _ = summaries.GetAsync(bound.SteamId64, () => FetchSummaryAsync(bound));
        }
    });

    // Never waits: the empty query shows what is cached and the refresh lands on the next open.
    public async Task<ProfileSummary?> CachedSummaryAsync()
    {
        if (await access.CurrentAsync() is not { } bound)
        {
            return null;
        }

        var summary = summaries.GetAsync(bound.SteamId64, () => FetchSummaryAsync(bound));
        return summary.IsCompletedSuccessfully ? summary.Result : null;
    }

    // Returns the framed avatar once it has been built; until then the plain avatar is shown and the frame is built in the background.
    public async Task<string?> FramedAvatarAsync(string? avatarPath)
    {
        if (avatarPath is null || await access.CurrentAsync() is not { } bound)
        {
            return null;
        }

        var framedPath = Path.Combine(cacheFolder, string.Create(CultureInfo.InvariantCulture, $"avatar_{bound.SteamId64}_framed.png"));
        var now = time.GetUtcNow();
        var framed = new FileInfo(framedPath);
        if (framed.Exists
            && now - framed.LastWriteTimeUtc < FrameLifetime
            && framed.LastWriteTimeUtc >= File.GetLastWriteTimeUtc(avatarPath))
        {
            return framedPath;
        }

        lock (gate)
        {
            if (frameChecks.TryGetValue(bound.SteamId64, out var checkedAt) && now - checkedAt < FrameLifetime)
            {
                return null;
            }

            frameChecks[bound.SteamId64] = now;
        }

        _ = Task.Run(() => BuildFramedAvatarAsync(bound, avatarPath, framedPath));
        return null;
    }

    private async Task BuildFramedAvatarAsync(BoundKey bound, string avatarPath, string framedPath)
    {
        try
        {
            if (await requests.Quietly("Avatar frame request", token => api.AvatarFrameAsync(bound.Key, bound.SteamId64, token)) is not { } frame)
            {
                return;
            }

            var framePath = Path.Combine(cacheFolder, $"avatar_frame_{frame.Id}.png");
            if (!File.Exists(framePath))
            {
                if (await requests.Quietly("Avatar frame download", token => api.DownloadAsync(frame.ImageUrl, token)) is not { Length: > 0 } image)
                {
                    return;
                }

                Directory.CreateDirectory(cacheFolder);
                await File.WriteAllBytesAsync(framePath, image);
            }

            await composer.ComposeAsync(avatarPath, framePath, framedPath);
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or InvalidOperationException or NotSupportedException)
        {
            log.Warn("Framed avatar failed", ex);
        }
    }

    private Task<ProfileSummary?> FetchSummaryAsync(BoundKey bound) =>
        requests.Quietly("Profile summary request", token => api.PlayerSummaryAsync(bound.Key, bound.SteamId64, token));
}
