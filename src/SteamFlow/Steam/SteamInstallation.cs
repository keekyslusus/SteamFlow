using Microsoft.Win32;

namespace SteamFlow.Steam;

public sealed class SteamInstallation
{
    public string? FindSteamPath()
    {
        using var key = Registry.CurrentUser.OpenSubKey(@"Software\Valve\Steam");
        var path = key?.GetValue("SteamPath") as string;
        if (string.IsNullOrWhiteSpace(path))
        {
            return null;
        }

        // The registry stores the path with forward slashes and lowercase drive letters.
        var fullPath = Path.GetFullPath(path);
        return Directory.Exists(fullPath) ? fullPath : null;
    }
}
