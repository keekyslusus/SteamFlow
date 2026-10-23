using SteamFlow.Diagnostics;

namespace SteamFlow.Tests;

public sealed class PluginLogTests : IDisposable
{
    private readonly string folder = Path.Combine(Path.GetTempPath(), "steamflow-tests-" + Guid.NewGuid().ToString("N"));
    private readonly ManualTime time = new();

    private string LogPath => Path.Combine(folder, "steamflow.log");

    private string OldLogPath => Path.Combine(folder, "steamflow.old.log");

    [Fact]
    public void Warn_WritesWhatFailedAndWhy()
    {
        new PluginLog(LogPath, time).Warn("App details request failed", new HttpRequestException("503"), "app 570");

        Assert.Contains("WARN App details request failed (app 570): HttpRequestException: 503", File.ReadAllText(LogPath));
    }

    [Fact]
    public void Repeats_AreWrittenOncePerWindowAndCounted()
    {
        var log = new PluginLog(LogPath, time);

        log.Warn("Store search failed", new HttpRequestException("offline"), "'a'");
        log.Warn("Store search failed", new HttpRequestException("offline"), "'ab'");
        log.Warn("Store search failed", new HttpRequestException("offline"), "'abc'");
        time.Advance(TimeSpan.FromMinutes(11));
        log.Warn("Store search failed", new HttpRequestException("offline"), "'abcd'");

        var lines = File.ReadAllLines(LogPath);
        Assert.Equal(2, lines.Length);
        Assert.Contains("(also 2 more times since", lines[1]);
    }

    [Fact]
    public void Slow_OnlyWritesPastTheThreshold()
    {
        var log = new PluginLog(LogPath, time);

        var fast = log.StartTiming();
        time.Advance(TimeSpan.FromMilliseconds(200));
        log.Slow("Store search request", fast, TimeSpan.FromSeconds(1));
        var slow = log.StartTiming();
        time.Advance(TimeSpan.FromMilliseconds(1500));
        log.Slow("Search", slow, TimeSpan.FromSeconds(1), "'elden'");

        Assert.Equal(["SLOW Search ('elden') took 1500 ms"], File.ReadAllLines(LogPath).Select(line => line[24..]));
    }

    [Fact]
    public void FullLog_MovesToTheOldFileSoTheSizeStaysCapped()
    {
        var log = new PluginLog(LogPath, time);
        for (var index = 0; index < 4000; index++)
        {
            log.Warn($"Failure {index}", new IOException(new string('x', 100)));
        }

        Assert.True(new FileInfo(LogPath).Length <= 65 * 1024);
        Assert.True(new FileInfo(OldLogPath).Length <= 65 * 1024);
        Assert.Contains("Failure 3999", File.ReadAllText(LogPath));
    }

    public void Dispose()
    {
        if (Directory.Exists(folder))
        {
            Directory.Delete(folder, recursive: true);
        }
    }

    private sealed class ManualTime : TimeProvider
    {
        private DateTimeOffset now = new(2026, 10, 23, 12, 0, 0, TimeSpan.Zero);

        public override DateTimeOffset GetUtcNow() => now;

        public override long TimestampFrequency => TimeSpan.TicksPerSecond;

        public override long GetTimestamp() => now.UtcTicks;

        public void Advance(TimeSpan by) => now += by;
    }
}
