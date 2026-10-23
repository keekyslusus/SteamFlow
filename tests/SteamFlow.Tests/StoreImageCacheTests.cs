using SteamFlow.Store;

namespace SteamFlow.Tests;

public sealed class StoreImageCacheTests : IDisposable
{
    private readonly string folder = Path.Combine(Path.GetTempPath(), "steamflow-tests-" + Guid.NewGuid().ToString("N"));

    [Fact]
    public async Task Find_ReturnsSavedCapsule()
    {
        var cache = new StoreImageCache(folder, TimeProvider.System);
        Assert.Null(cache.Find(570));

        await cache.SaveAsync(cache.CapsulePath(570), [1]);

        Assert.Equal(cache.CapsulePath(570), cache.Find(570));
    }

    [Fact]
    public async Task Cleanup_DropsOldCapsulesAndForeignFiles()
    {
        var cache = new StoreImageCache(folder, TimeProvider.System);
        await cache.SaveAsync(cache.CapsulePath(1), [1]);
        await cache.SaveAsync(cache.CapsulePath(2), [1]);
        await File.WriteAllBytesAsync(Path.Combine(folder, "3_icon.jpg"), [1]);
        File.SetLastWriteTimeUtc(cache.CapsulePath(2), DateTime.UtcNow.AddDays(-8));

        cache.Cleanup();

        Assert.Equal(cache.CapsulePath(1), cache.Find(1));
        Assert.Null(cache.Find(2));
        Assert.False(File.Exists(Path.Combine(folder, "3_icon.jpg")));
    }

    public void Dispose()
    {
        if (Directory.Exists(folder))
        {
            Directory.Delete(folder, recursive: true);
        }
    }
}
