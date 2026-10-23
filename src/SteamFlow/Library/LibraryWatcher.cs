namespace SteamFlow.Library;

public sealed record WatchTarget(string Folder, string Filter);

public sealed class LibraryWatcher(TimeSpan delay) : IDisposable
{
    private readonly Lock gate = new();
    private List<FileSystemWatcher> watchers = [];
    private Timer? pending;
    private Action? onChange;

    public void Watch(IEnumerable<WatchTarget> targets, Action changed)
    {
        var created = targets
            .Where(target => Directory.Exists(target.Folder))
            .Select(target =>
            {
                var watcher = new FileSystemWatcher(target.Folder, target.Filter)
                {
                    NotifyFilter = NotifyFilters.FileName | NotifyFilters.LastWrite | NotifyFilters.Size,
                };
                watcher.Changed += OnFileEvent;
                watcher.Created += OnFileEvent;
                watcher.Deleted += OnFileEvent;
                watcher.Renamed += OnFileEvent;
                watcher.EnableRaisingEvents = true;
                return watcher;
            })
            .ToList();

        List<FileSystemWatcher> previous;
        lock (gate)
        {
            previous = watchers;
            watchers = created;
            onChange = changed;
        }

        previous.ForEach(watcher => watcher.Dispose());
    }

    public void Dispose()
    {
        List<FileSystemWatcher> current;
        lock (gate)
        {
            current = watchers;
            watchers = [];
            onChange = null;
            pending?.Dispose();
            pending = null;
        }

        current.ForEach(watcher => watcher.Dispose());
    }

    // Steam rewrites manifests many times per second while downloading, so the first event schedules
    // one reload and the rest are absorbed until it runs; resetting a debounce would starve the reload.
    private void OnFileEvent(object sender, FileSystemEventArgs e)
    {
        lock (gate)
        {
            pending ??= new Timer(_ => Fire(), null, delay, Timeout.InfiniteTimeSpan);
        }
    }

    private void Fire()
    {
        Action? changed;
        lock (gate)
        {
            pending?.Dispose();
            pending = null;
            changed = onChange;
        }

        changed?.Invoke();
    }
}
