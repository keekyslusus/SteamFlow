using System.Globalization;

namespace SteamFlow.Store;

// Flow squeezes images loaded from a URL into a square, so store capsules are shown from local files,
// which Flow draws with their own aspect ratio.
public sealed class StoreImageCache(string folder, TimeProvider time)
{
    private const string CapsuleSuffix = "_capsule.jpg";

    // Steam rarely changes capsule art, and a week keeps the folder small for games searched once.
    private static readonly TimeSpan Lifetime = TimeSpan.FromDays(7);

    public string CapsulePath(int appId) =>
        Path.Combine(folder, string.Create(CultureInfo.InvariantCulture, $"{appId}{CapsuleSuffix}"));

    public string? Find(int appId) => File.Exists(CapsulePath(appId)) ? CapsulePath(appId) : null;

    public async Task SaveAsync(string path, byte[] image)
    {
        Directory.CreateDirectory(folder);
        var temporary = path + ".tmp";
        await File.WriteAllBytesAsync(temporary, image);
        File.Move(temporary, path, overwrite: true);
    }

    public void Cleanup()
    {
        if (!Directory.Exists(folder))
        {
            return;
        }

        var now = time.GetUtcNow().UtcDateTime;
        foreach (var file in new DirectoryInfo(folder).EnumerateFiles())
        {
            if (!file.Name.EndsWith(CapsuleSuffix, StringComparison.Ordinal) || now - file.LastWriteTimeUtc > Lifetime)
            {
                try
                {
                    file.Delete();
                }
                catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
                {
                }
            }
        }
    }
}
