using SteamFlow.Steam;

namespace SteamFlow.Library;

public sealed class LocalLibrary(LibraryLoader loader, SteamUsers users, LibraryWatcher watcher) : IDisposable
{
    private readonly Lock gate = new();
    private Task<LibrarySnapshot> snapshot = Task.FromResult(LibrarySnapshot.Empty);

    public void Reload()
    {
        var next = Task.Run(loader.Load);
        lock (gate)
        {
            snapshot = next;
        }

        next.ContinueWith(
            loaded => watcher.Watch(WatchTargets(loaded.Result), Reload),
            TaskContinuationOptions.OnlyOnRanToCompletion);
    }

    public Task<LibrarySnapshot> GetAsync()
    {
        Task<LibrarySnapshot> current;
        lock (gate)
        {
            current = snapshot;
        }

        // Switching accounts changes playtime, hidden games and achievements without touching the watched files.
        if (current.IsFaulted || (current.IsCompletedSuccessfully && ActiveAccountChanged(current.Result)))
        {
            Reload();
            lock (gate)
            {
                current = snapshot;
            }
        }

        return current;
    }

    public void Dispose() => watcher.Dispose();

    private bool ActiveAccountChanged(LibrarySnapshot loaded) =>
        loaded.SteamFound && users.ReadActiveAccountId() is { } activeId && activeId != loaded.ActiveAccountId;

    private static IEnumerable<WatchTarget> WatchTargets(LibrarySnapshot loaded)
    {
        foreach (var steamApps in loaded.SteamAppsFolders)
        {
            yield return new WatchTarget(steamApps, "appmanifest_*.acf");
        }

        if (loaded.ConfigFolder is { } config)
        {
            yield return new WatchTarget(config, "localconfig.vdf");
            yield return new WatchTarget(
                Path.Combine(config, HiddenGamesReader.CloudStorageFolder),
                HiddenGamesReader.CloudStorageFile);
        }
    }
}
