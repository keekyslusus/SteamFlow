using System.Globalization;
using System.Text;
using System.Text.RegularExpressions;

namespace SteamFlow.Downloads;

public enum DownloadStatus
{
    None,
    Updating,
    Paused,
    Queued,
    Required,
}

public sealed record AppUpdateState(IReadOnlySet<string> Flags, string Note, DateTime At, long DownloadBytes = 0)
{
    // "Update Started" stays set while a download is paused, suspended or queued, which is why the Python
    // plugin kept showing finished downloads as running; only "Update Running" means bytes are moving.
    public DownloadStatus Status =>
        Flags.Contains("Update Paused") || Note.Contains("Paused", StringComparison.Ordinal) ? DownloadStatus.Paused
        : Flags.Contains("Update Running") ? DownloadStatus.Updating
        : Flags.Contains("Update Queued") || Note.Contains("Suspended", StringComparison.Ordinal) ? DownloadStatus.Queued
        : Flags.Contains("Update Required") ? DownloadStatus.Required
        : DownloadStatus.None;

    // Steam can leave the manifest of a cancelled first download behind with "update paused" flags.
    public bool Uninstalled => Flags.Contains("Uninstalled") || Flags.Contains("Uninstalling");
}

// Steam writes every app state change to logs/content_log.txt the moment it happens, unlike appmanifest
// StateFlags, which lag. The file is read incrementally: each call only parses what Steam appended.
public sealed partial class ContentLog
{
    private readonly Lock gate = new();
    private readonly Dictionary<int, AppUpdateState> states = [];
    private string? path;
    private long offset;

    public IReadOnlyDictionary<int, AppUpdateState> Read(string steamPath)
    {
        var logPath = Path.Combine(steamPath, "logs", "content_log.txt");
        lock (gate)
        {
            if (logPath != path)
            {
                path = logPath;
                Reset();
            }

            try
            {
                using var stream = new FileStream(logPath, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete);
                if (stream.Length < offset)
                {
                    // Steam started a new file (it rotates the log), so the old position means nothing.
                    Reset();
                }

                stream.Seek(offset, SeekOrigin.Begin);
                var appended = new byte[stream.Length - offset];
                stream.ReadExactly(appended);

                // A line Steam is still writing has no newline yet; it is read again next time.
                var complete = Array.LastIndexOf(appended, (byte)'\n') + 1;
                foreach (var line in Encoding.UTF8.GetString(appended, 0, complete).Split('\n'))
                {
                    Apply(states, line);
                }

                offset += complete;
            }
            catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
            {
            }

            return new Dictionary<int, AppUpdateState>(states);
        }
    }

    public static void Apply(Dictionary<int, AppUpdateState> states, string line)
    {
        // Every Steam start logs its client version first; states from earlier runs no longer apply.
        if (line.Contains("] Client version:", StringComparison.Ordinal))
        {
            states.Clear();
            return;
        }

        // The download size is only logged when an update starts, so later state lines carry it forward.
        var started = UpdateStarted().Match(line);
        if (started.Success)
        {
            var startedApp = int.Parse(started.Groups["app"].Value, CultureInfo.InvariantCulture);
            var previous = states.GetValueOrDefault(startedApp) ?? new AppUpdateState(new HashSet<string>(), "", DateTime.MinValue);
            states[startedApp] = previous with { DownloadBytes = long.Parse(started.Groups["total"].Value, CultureInfo.InvariantCulture) };
            return;
        }

        var match = StateChanged().Match(line);
        if (!match.Success)
        {
            return;
        }

        var app = int.Parse(match.Groups["app"].Value, CultureInfo.InvariantCulture);
        var flags = match.Groups["flags"].Value
            .Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries)
            .ToHashSet(StringComparer.Ordinal);
        DateTime.TryParseExact(match.Groups["time"].Value, "yyyy-MM-dd HH:mm:ss", CultureInfo.InvariantCulture, DateTimeStyles.AssumeLocal, out var at);
        states[app] = new AppUpdateState(flags, match.Groups["note"].Value.Trim(), at, states.GetValueOrDefault(app)?.DownloadBytes ?? 0);
    }

    private void Reset()
    {
        offset = 0;
        states.Clear();
    }

    [GeneratedRegex(@"^\[(?<time>[^\]]+)\] AppID (?<app>\d+) state changed : (?<flags>[^(\r]*)(?<note>\([^)]*\))?")]
    private static partial Regex StateChanged();

    [GeneratedRegex(@"^\[[^\]]+\] AppID (?<app>\d+) update started : download \d+/(?<total>\d+)")]
    private static partial Regex UpdateStarted();
}
