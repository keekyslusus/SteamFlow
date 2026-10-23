using SteamFlow.Diagnostics;
using SteamFlow.Steam;

namespace SteamFlow.Library;

public sealed class InstalledGamesReader(PluginLog log)
{
    private const int UpdateRequired = 2;
    private const int FullyInstalled = 4;
    private const int UpdateRunning = 256;
    private const int UpdatePaused = 512;
    private const int UpdateStarted = 1024;

    public IReadOnlyList<string> FindSteamAppsFolders(string steamPath)
    {
        var defaultSteamApps = Path.Combine(steamPath, "steamapps");
        var folders = new List<string> { defaultSteamApps };

        var libraryFoldersPath = Path.Combine(defaultSteamApps, "libraryfolders.vdf");
        if (File.Exists(libraryFoldersPath))
        {
            try
            {
                foreach (var library in Vdf.ReadText(libraryFoldersPath).Items())
                {
                    if (library.Text("path") is { Length: > 0 } libraryPath)
                    {
                        folders.Add(Path.Combine(Path.GetFullPath(libraryPath), "steamapps"));
                    }
                }
            }
            catch (Exception ex) when (Vdf.IsReadError(ex))
            {
                log.Warn("libraryfolders.vdf unreadable", ex);
            }
        }

        return [.. folders.Distinct(StringComparer.OrdinalIgnoreCase).Where(Directory.Exists)];
    }

    public IReadOnlyList<InstalledGame> Read(IEnumerable<string> steamAppsFolders)
    {
        var games = new Dictionary<int, InstalledGame>();
        foreach (var steamApps in steamAppsFolders)
        {
            foreach (var manifestPath in Directory.EnumerateFiles(steamApps, "appmanifest_*.acf"))
            {
                if (TryReadManifest(steamApps, manifestPath) is { } game)
                {
                    games.TryAdd(game.AppId, game);
                }
            }
        }

        return [.. games.Values];
    }

    // Games that are still being installed for the first time have none of these flags.
    public static bool IsVisible(long stateFlags) =>
        (stateFlags & (FullyInstalled | UpdateRequired | UpdateRunning | UpdatePaused | UpdateStarted)) != 0;

    private static InstalledGame? TryReadManifest(string steamApps, string manifestPath)
    {
        try
        {
            var state = Vdf.ReadText(manifestPath);
            var stateFlags = state.Number("StateFlags") ?? 0;
            if (state.Number("appid") is not { } appId
                || state.Text("name") is not { Length: > 0 } name
                || !IsVisible(stateFlags))
            {
                return null;
            }

            var installDir = state.Text("installdir");
            var installPath = string.IsNullOrEmpty(installDir) ? "" : Path.Combine(steamApps, "common", installDir);
            return new InstalledGame((int)appId, name, installPath, stateFlags, state.Number("SizeOnDisk") ?? 0);
        }
        // Steam rewrites manifests while downloading; a half-written one should not break the whole list.
        catch (Exception ex) when (Vdf.IsReadError(ex))
        {
            return null;
        }
    }
}
