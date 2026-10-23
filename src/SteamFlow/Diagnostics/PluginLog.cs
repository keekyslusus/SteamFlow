namespace SteamFlow.Diagnostics;

// The plugin's own log, kept apart from Flow's so its size stays capped: one file of up to MaxFileBytes plus one
// previous file. Writing never throws, because a broken log must not break the feature that reports to it.
public sealed class PluginLog(string path, TimeProvider time)
{
    private const long MaxFileBytes = 64 * 1024;

    // Without a network every keystroke fails the same way; such repeats are written once per window and counted.
    private static readonly TimeSpan RepeatWindow = TimeSpan.FromMinutes(10);

    private readonly Lock gate = new();
    private readonly Dictionary<string, Repeat> repeats = [];

    // Expected failures (network, locked or malformed files): the exception's type and message are enough.
    // `what` names the failure and must not vary, since repeats are matched on it; specifics go in `detail`.
    public void Warn(string what, Exception ex, string? detail = null) =>
        Write("WARN", what + "|" + ex.GetType().Name, $"{Describe(what, detail)}: {ex.GetType().Name}: {ex.Message}");

    // Unexpected failures keep the stack trace.
    public void Error(string what, Exception ex) =>
        Write("ERROR", what + "|" + ex.GetType().Name, $"{what}{Environment.NewLine}{ex}");

    public long StartTiming() => time.GetTimestamp();

    public void Slow(string what, long started, TimeSpan threshold, string? detail = null)
    {
        var elapsed = time.GetElapsedTime(started);
        if (elapsed >= threshold)
        {
            Write("SLOW", what, $"{Describe(what, detail)} took {elapsed.TotalMilliseconds:0} ms");
        }
    }

    private static string Describe(string what, string? detail) => detail is null ? what : $"{what} ({detail})";

    private void Write(string level, string key, string message)
    {
        lock (gate)
        {
            var now = time.GetUtcNow();
            if (repeats.TryGetValue(level + key, out var repeat) && now - repeat.WrittenAt < RepeatWindow)
            {
                repeats[level + key] = repeat with { Skipped = repeat.Skipped + 1 };
                return;
            }

            repeats[level + key] = new Repeat(now, 0);
            if (repeat is { Skipped: > 0 })
            {
                message += $" (also {repeat.Skipped} more times since {repeat.WrittenAt.ToLocalTime():HH:mm})";
            }

            Append($"{now.ToLocalTime():yyyy-MM-dd HH:mm:ss.fff} {level} {message}{Environment.NewLine}");
        }
    }

    private void Append(string entry)
    {
        try
        {
            Directory.CreateDirectory(Path.GetDirectoryName(path)!);
            if (new FileInfo(path) is { Exists: true, Length: >= MaxFileBytes })
            {
                File.Move(path, Path.ChangeExtension(path, ".old.log"), overwrite: true);
            }

            File.AppendAllText(path, entry);
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
        }
    }

    private sealed record Repeat(DateTimeOffset WrittenAt, int Skipped);
}
