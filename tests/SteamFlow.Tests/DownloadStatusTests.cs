using SteamFlow.Downloads;
using SteamFlow.Library;
using SteamFlow.Settings;

namespace SteamFlow.Tests;

public sealed class DownloadStatusTests : IDisposable
{
    private readonly string steam = Path.Combine(Path.GetTempPath(), "steamflow-log-" + Guid.NewGuid().ToString("N"));

    // Lines copied from a real content_log.txt.
    [Theory]
    [InlineData("[2026-10-22 00:13:57] AppID 304930 state changed : Fully Installed,Update Queued,Update Running,", DownloadStatus.Updating)]
    [InlineData("[2026-06-08 12:21:05] AppID 570 state changed : Update Required,Fully Installed,Update Queued,Update Started, (Paused)", DownloadStatus.Paused)]
    [InlineData("[2026-06-08 12:21:05] AppID 570 state changed : Update Required,Fully Installed,Update Paused,Update Started,", DownloadStatus.Paused)]
    [InlineData("[2026-07-29 00:06:11] AppID 2807960 state changed : Update Required,Update Queued,Update Optional,Update Started, (Suspended)", DownloadStatus.Queued)]
    [InlineData("[2026-10-01 10:00:00] AppID 1 state changed : Update Required,Update Queued,Update Started,", DownloadStatus.Queued)]
    [InlineData("[2026-10-01 10:00:00] AppID 1 state changed : Update Required,", DownloadStatus.Required)]
    [InlineData("[2026-10-22 00:13:57] AppID 304930 state changed : Fully Installed,", DownloadStatus.None)]
    [InlineData("[2026-08-08 17:27:02] AppID 570 state changed : Update Required,Fully Installed,Update Paused, (Update delayed for 44944 secs)", DownloadStatus.Paused)]
    public void StateLines_MapToStatus(string line, DownloadStatus expected)
    {
        var states = new Dictionary<int, AppUpdateState>();

        ContentLog.Apply(states, line);

        Assert.Equal(expected, Assert.Single(states).Value.Status);
    }

    [Fact]
    public void NewSteamSession_ForgetsEarlierStates()
    {
        var states = new Dictionary<int, AppUpdateState>();

        ContentLog.Apply(states, "[2026-10-01 10:00:00] AppID 570 state changed : Fully Installed,Update Queued,Update Running,");
        ContentLog.Apply(states, "[2026-10-02 09:00:00] Client version: 1785799196");

        Assert.Empty(states);
    }

    [Fact]
    public void OtherLines_AreIgnored()
    {
        var states = new Dictionary<int, AppUpdateState>();

        ContentLog.Apply(states, "[2026-10-22 00:13:57] AppID 304930 App update changed : Running Update,Downloading,Staging,");
        ContentLog.Apply(states, "[2026-10-22 00:14:02] Current download rate: 0.000 Mbps");

        Assert.Empty(states);
    }

    [Theory]
    [InlineData(true, DownloadStatus.Updating, 4, DownloadStatus.Updating)]
    [InlineData(false, DownloadStatus.Updating, 4, DownloadStatus.None)]
    [InlineData(true, null, 4 | 256 | 1024, DownloadStatus.None)]
    [InlineData(true, null, 2 | 4 | 1024, DownloadStatus.Queued)]
    [InlineData(false, null, 2 | 1024, DownloadStatus.Required)]
    [InlineData(false, null, 4 | 512 | 1024, DownloadStatus.Paused)]
    public void Resolve_TrustsTheLogAndNeverAManifestRunningFlag(bool steamRunning, DownloadStatus? logged, long stateFlags, DownloadStatus expected)
    {
        var state = logged switch
        {
            DownloadStatus.Updating => new AppUpdateState(new HashSet<string> { "Update Running" }, "", DateTime.Now),
            _ => null,
        };

        Assert.Equal(expected, DownloadStatuses.Resolve(state, stateFlags, steamRunning));
    }

    [Fact]
    public void Read_FollowsAppendsAndRestartsAfterRotation()
    {
        var log = new ContentLog();
        Append("[2026-10-22 00:00:00] Client version: 1\n[2026-10-22 00:00:01] AppID 570 state changed : Fully Installed,Update Running,\n");
        Assert.Equal(DownloadStatus.Updating, log.Read(steam)[570].Status);

        Append("[2026-10-22 00:00:05] AppID 570 state changed : Fully Installed,Update Paused,Update Started,\n[2026-10-22 00:00:06] AppID 730 state chang");
        Assert.Equal(DownloadStatus.Paused, log.Read(steam)[570].Status);
        Assert.False(log.Read(steam).ContainsKey(730));

        Append("ed : Fully Installed,Update Running,\n");
        Assert.Equal(DownloadStatus.Updating, log.Read(steam)[730].Status);

        File.WriteAllText(LogPath, "[2026-10-22 01:00:00] AppID 10 state changed : Update Required,\n");
        var restarted = log.Read(steam);
        Assert.Equal([10], restarted.Keys);
    }

    [Fact]
    public void ClientInstance_PrefersThisMachine()
    {
        const string json = """
            {"response":{"sessions":[
              {"client_instanceid":"111","machine_name":"LAPTOP"},
              {"client_instanceid":"222","machine_name":"DESKTOP"}
            ]}}
            """;

        Assert.Equal("222", ClientCommApi.ClientInstance(json, "desktop"));
        Assert.Equal("111", ClientCommApi.ClientInstance(json, "OTHER"));
        Assert.Null(ClientCommApi.ClientInstance("""{"response":{}}""", "DESKTOP"));
    }

    [Fact]
    public void DownloadSize_IsCarriedIntoLaterStates()
    {
        var states = new Dictionary<int, AppUpdateState>();

        ContentLog.Apply(states, "[2026-10-22 15:02:10] AppID 1446780 update started : download 0/24213372928, store 0/0, reuse 0/0, delta 0/0, stage 0/0");
        ContentLog.Apply(states, "[2026-10-22 15:02:10] AppID 1446780 state changed : Fully Installed,Update Running,");
        ContentLog.Apply(states, "[2026-10-22 15:05:00] AppID 1446780 state changed : Fully Installed,Update Paused,Update Started,");

        var state = Assert.Single(states).Value;
        Assert.Equal(24213372928, state.DownloadBytes);
        Assert.Equal(DownloadStatus.Paused, state.Status);
    }

    [Fact]
    public void CancelledFirstDownload_IsUninstalledWhileSteamRuns()
    {
        var states = new Dictionary<int, AppUpdateState>();
        ContentLog.Apply(states, "[2026-10-22 01:41:09] AppID 1627720 state changed : Update Required,Uninstalling,");
        ContentLog.Apply(states, "[2026-10-22 01:41:09] AppID 1627720 state changed : Uninstalled,");

        Assert.True(new DownloadView(states, SteamRunning: true).IsUninstalled(1627720));
        Assert.False(new DownloadView(states, SteamRunning: false).IsUninstalled(1627720));

        ContentLog.Apply(states, "[2026-10-22 02:00:00] AppID 1627720 state changed : Update Required,Update Queued,");
        Assert.False(new DownloadView(states, SteamRunning: true).IsUninstalled(1627720));
    }

    [Fact]
    public void Progress_IsOnlyWantedForLargeRunningDownloads()
    {
        var running = new HashSet<string> { "Update Running" };
        var view = new DownloadView(
            new Dictionary<int, AppUpdateState>
            {
                [1] = new(running, "", DateTime.Now, DownloadProgress.MinimumBytes),
                [2] = new(running, "", DateTime.Now, DownloadProgress.MinimumBytes - 1),
            },
            SteamRunning: true);

        Assert.True(DownloadProgress.Wanted(view, 1, DownloadStatus.Updating));
        Assert.False(DownloadProgress.Wanted(view, 1, DownloadStatus.Paused));
        Assert.False(DownloadProgress.Wanted(view, 2, DownloadStatus.Updating));
        Assert.False(DownloadProgress.Wanted(view, 3, DownloadStatus.Updating));
    }

    [Fact]
    public void ParseProgress_ReadsPercentAndTimeLeft()
    {
        // Shape of a real GetClientAppList answer, trimmed.
        const string json = """
            {"response":{"bytes_available":"1","apps":[
              {"appid":1446780,"app":"Monster Hunter Rise","bytes_downloaded":"3350000000","bytes_to_download":"24213372928","update_percentage":9,"estimated_seconds_remaining":1320,"download_paused":false},
              {"appid":570,"app":"Dota 2","update_percentage":0},
              {"appid":"730","update_percentage":"140","estimated_seconds_remaining":0},
              {"app":"no id","update_percentage":5}
            ],"refetch_interval_sec_updating":10}}
            """;

        var progress = ClientCommApi.ParseProgress(json);

        Assert.Equal(new AppProgress(9, 1320), progress[1446780]);
        Assert.Equal(new AppProgress(0, null), progress[570]);
        Assert.Equal(new AppProgress(100, null), progress[730]);
        Assert.Equal(3, progress.Count);
        Assert.Empty(ClientCommApi.ParseProgress("""{"response":{}}"""));
    }

    [Theory]
    [InlineData(1320, "Pause updating game | 9%, ~22 min left")]
    [InlineData(5, "Pause updating game | 9%, ~1 min left")]
    [InlineData(3900, "Pause updating game | 9%, ~1 h 5 min left")]
    [InlineData(null, "Pause updating game | 9%")]
    public void Subtitle_ShowsProgressAfterTheAction(int? secondsLeft, string expected)
    {
        var subtitles = new LibrarySubtitles(EnglishText.Translator(), new PluginSettings(), TimeProvider.System);
        var game = new LibraryGame(1446780, "Monster Hunter Rise", @"C:\mhr", null, null, null, HasCurrentAccountData: true);

        Assert.Equal(expected, subtitles.Build(game, false, download: DownloadStatus.Updating, canControl: true, progress: new AppProgress(9, secondsLeft)));
    }

    [Theory]
    [InlineData(DownloadStatus.Updating, true, "Pause updating game")]
    [InlineData(DownloadStatus.Updating, false, "Installed game, updating")]
    [InlineData(DownloadStatus.Paused, true, "Resume updating game")]
    [InlineData(DownloadStatus.Queued, false, "Installed game, update queued")]
    [InlineData(DownloadStatus.None, false, "Launch game")]
    public void Subtitle_StartsWithTheDownloadAction(DownloadStatus status, bool canControl, string expected)
    {
        var subtitles = new LibrarySubtitles(EnglishText.Translator(), new PluginSettings(), TimeProvider.System);
        var game = new LibraryGame(570, "Dota 2", @"C:\dota", null, null, null, HasCurrentAccountData: true);

        Assert.Equal(expected, subtitles.Build(game, false, download: status, canControl: canControl));
    }

    public void Dispose()
    {
        if (Directory.Exists(steam))
        {
            Directory.Delete(steam, recursive: true);
        }
    }

    private string LogPath => Path.Combine(steam, "logs", "content_log.txt");

    private void Append(string text)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(LogPath)!);
        File.AppendAllText(LogPath, text);
    }
}
