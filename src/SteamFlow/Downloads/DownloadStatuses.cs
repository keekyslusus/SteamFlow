using SteamFlow.Session;
using SteamFlow.Steam;

namespace SteamFlow.Downloads;

public sealed record DownloadView(IReadOnlyDictionary<int, AppUpdateState> Logged, bool SteamRunning)
{
    public DownloadStatus StatusOf(int appId, long stateFlags) =>
        DownloadStatuses.Resolve(Logged.GetValueOrDefault(appId), stateFlags, SteamRunning);

    public bool IsUninstalled(int appId) => SteamRunning && Logged.GetValueOrDefault(appId)?.Uninstalled == true;

    // Pausing and resuming go through the running client, so they are only offered while it runs.
    public bool CanControl(DownloadStatus status) => SteamRunning && status is DownloadStatus.Updating or DownloadStatus.Paused;
}

public sealed class DownloadStatuses(ContentLog log, SteamInstallation installation)
{
    private const long UpdateRequired = 2;
    private const long FullyInstalled = 4;
    private const long UpdatePaused = 512;

    // One read of the log and one process check per query, shared by every game in it.
    public DownloadView Snapshot()
    {
        var steamRunning = SteamSessionTokens.SteamIsRunning();
        return new DownloadView(
            steamRunning && installation.FindSteamPath() is { } steamPath ? log.Read(steamPath) : new Dictionary<int, AppUpdateState>(),
            steamRunning);
    }

    // The log of the current Steam session wins; without an entry there, the manifest is only trusted for
    // the slow-changing states, never for "running", which it keeps reporting long after a download ends.
    public static DownloadStatus Resolve(AppUpdateState? logged, long stateFlags, bool steamRunning)
    {
        if (steamRunning && logged is not null)
        {
            return logged.Status;
        }

        if ((stateFlags & UpdatePaused) != 0)
        {
            return DownloadStatus.Paused;
        }

        if ((stateFlags & UpdateRequired) != 0)
        {
            return (stateFlags & FullyInstalled) != 0 ? DownloadStatus.Queued : DownloadStatus.Required;
        }

        return DownloadStatus.None;
    }
}
