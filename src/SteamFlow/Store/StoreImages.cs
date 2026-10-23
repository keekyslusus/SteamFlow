using System.Collections.Concurrent;

namespace SteamFlow.Store;

public sealed class StoreImages(StoreApi api, StoreRequests requests, StoreImageCache cache)
{
    private readonly ConcurrentDictionary<int, Task<string?>> pending = new();

    public void WarmUp() => Task.Run(cache.Cleanup);

    // Each app gets its own task so cached capsules show even while other downloads are still running.
    public IReadOnlyDictionary<int, Task<string?>> Resolve(IReadOnlyCollection<StoreSearchItem> items)
    {
        var images = new Dictionary<int, Task<string?>>();
        foreach (var item in items)
        {
            if (cache.Find(item.AppId) is { } path)
            {
                images[item.AppId] = Task.FromResult<string?>(path);
            }
            else if (item.CapsuleUrl is { } url)
            {
                images[item.AppId] = pending.GetOrAdd(item.AppId, appId => DownloadAsync(appId, url));
            }
            else
            {
                images[item.AppId] = Task.FromResult<string?>(null);
            }
        }

        return images;
    }

    private async Task<string?> DownloadAsync(int appId, string url)
    {
        try
        {
            if (await requests.Quietly("Store capsule download", token => api.DownloadAsync(url, token), $"app {appId}") is not { Length: > 0 } image)
            {
                return null;
            }

            var path = cache.CapsulePath(appId);
            await cache.SaveAsync(path, image);
            return path;
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
            return null;
        }
        finally
        {
            pending.TryRemove(appId, out _);
        }
    }
}
