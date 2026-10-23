using System.Globalization;

namespace SteamFlow.Library;

public sealed class GameIconLocator
{
    private static readonly string[] NonIconPrefixes = ["header", "library", "logo"];

    // Steam stores the small library icon as a hash-named jpg next to the header and capsule art.
    public string? Find(string steamPath, int appId)
    {
        var folder = Path.Combine(steamPath, "appcache", "librarycache", appId.ToString(CultureInfo.InvariantCulture));
        if (!Directory.Exists(folder))
        {
            return null;
        }

        try
        {
            return Directory.EnumerateFiles(folder, "*.jpg")
                .FirstOrDefault(file => !NonIconPrefixes.Any(prefix =>
                    Path.GetFileName(file).StartsWith(prefix, StringComparison.OrdinalIgnoreCase)));
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
            return null;
        }
    }
}
