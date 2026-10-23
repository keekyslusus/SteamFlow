using System.Collections.Concurrent;
using System.Windows;
using Flow.Launcher.Plugin;
using SteamFlow.Diagnostics;
using SteamFlow.Localization;
using SteamFlow.Settings;

namespace SteamFlow.Smoke;

public enum SmokeSafety
{
    Checking,
    Clean,
    Risk,
}

public sealed record SmokeMenuState(SmokeAction Action, SmokeSafety Safety, string? Signal);

public sealed class SmokeApiService(
    SmokeApiFiles files,
    AntiCheatScanner scanner,
    SmokePayload payload,
    PluginSettings settings,
    IPublicAPI flow,
    Translator text,
    TimeProvider time,
    PluginLog log,
    string pluginDirectory)
{
    private static readonly TimeSpan StateLifetime = TimeSpan.FromMinutes(10);
    private static readonly TimeSpan SafetyLifetime = TimeSpan.FromDays(7);

    // Installing re-checks a scan older than this, since a game update can add an anti-cheat.
    private static readonly TimeSpan InstallRescanAge = TimeSpan.FromHours(1);

    private readonly ConcurrentDictionary<(int AppId, string Path), Timed<SmokeState>> states = new();
    private readonly ConcurrentDictionary<(int AppId, string Path), Timed<string?>> scans = new();
    private readonly ConcurrentDictionary<(int AppId, string Path), Task> pending = new();

    // Walking a game folder can take seconds, so it starts when the game is shown and the menu reads the result.
    public void Prefetch(int appId, string installPath)
    {
        if (!settings.EnableSmokeApiContextMenu || installPath.Length == 0)
        {
            return;
        }

        var key = (appId, installPath);
        if (Fresh(states, key, StateLifetime) is not null && Fresh(scans, key, SafetyLifetime) is not null)
        {
            return;
        }

        pending.GetOrAdd(key, _ => Task.Run(() =>
        {
            try
            {
                Refresh(key);
            }
            catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
            {
            }
            finally
            {
                pending.TryRemove(key, out Task? _);
            }
        }));
    }

    public SmokeMenuState? MenuState(int appId, string installPath)
    {
        if (!settings.EnableSmokeApiContextMenu || installPath.Length == 0)
        {
            return null;
        }

        var key = (appId, installPath);
        if (Fresh(states, key, StateLifetime) is not { } state || state.Value.Action == SmokeAction.None)
        {
            Prefetch(appId, installPath);
            return null;
        }

        if (state.Value.Action == SmokeAction.Remove)
        {
            return new SmokeMenuState(SmokeAction.Remove, SmokeSafety.Clean, null);
        }

        var scan = Fresh(scans, key, SafetyLifetime);
        return scan is null
            ? new SmokeMenuState(SmokeAction.Install, SmokeSafety.Checking, null)
            : new SmokeMenuState(SmokeAction.Install, scan.Value.Value is null ? SmokeSafety.Clean : SmokeSafety.Risk, scan.Value.Value);
    }

    // Runs on Flow's UI thread so the dialogs can show; folder work is pushed to the thread pool.
    public async Task InstallAsync(int appId, string installPath, string name)
    {
        var key = (appId, installPath);
        if (!Directory.Exists(installPath))
        {
            Error("steamflow_smoke_install_path_missing");
            return;
        }

        if (!payload.Ready())
        {
            if (!Confirm("steamflow_smoke_download_title", text.Get("steamflow_smoke_download_body")) || !await DownloadAsync())
            {
                return;
            }
        }

        string? signal;
        try
        {
            signal = Fresh(scans, key, InstallRescanAge) is { } recent
                ? recent.Value
                : await Task.Run(() => Scan(key));
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
            log.Warn("SmokeAPI anti-cheat scan failed", ex, $"app {appId}");
            Error("steamflow_smoke_scan_failed");
            return;
        }

        var body = signal is null
            ? text.Format("steamflow_smoke_install_body", name)
            : text.Format("steamflow_smoke_install_body_anticheat", name, signal);
        if (!Confirm("steamflow_smoke_install_title", body))
        {
            return;
        }

        var result = await Task.Run(() => files.Install(installPath, payload.Folder, SmokePayload.Hashes));
        Forget(key);
        if (result.Succeeded)
        {
            Notify(text.Get("steamflow_smoke_title"), text.Format("steamflow_smoke_install_success", result.ChangedDlls));
        }
        else if (result.Partial)
        {
            Error("steamflow_smoke_install_partial", result.Successful, result.Total);
        }
        else
        {
            Error("steamflow_smoke_install_failed");
        }
    }

    public async Task RemoveAsync(int appId, string installPath, string name)
    {
        if (!Directory.Exists(installPath))
        {
            Error("steamflow_smoke_install_path_missing");
            return;
        }

        if (!Confirm("steamflow_smoke_remove_title", text.Format("steamflow_smoke_remove_body", name)))
        {
            return;
        }

        var result = await Task.Run(() => files.Remove(installPath, SmokePayload.Hashes));
        Forget((appId, installPath));
        if (result.Succeeded)
        {
            Notify(text.Get("steamflow_smoke_title"), text.Format("steamflow_smoke_remove_success", result.ChangedDlls));
        }
        else if (result.BackupMissing.Count > 0)
        {
            Error("steamflow_smoke_backup_missing");
        }
        else if (result.Partial)
        {
            Error("steamflow_smoke_remove_partial", result.Successful, result.Total);
        }
        else
        {
            Error("steamflow_smoke_remove_failed");
        }
    }

    private async Task<bool> DownloadAsync()
    {
        using var cancel = new CancellationTokenSource();
        Exception? failure = null;
        await flow.ShowProgressBoxAsync(
            text.Get("steamflow_smoke_downloading"),
            async progress =>
            {
                try
                {
                    await payload.DownloadAsync(flow, progress, cancel.Token);
                }
                catch (Exception ex) when (ex is HttpRequestException or OperationCanceledException or IOException or InvalidDataException)
                {
                    failure = ex;
                }
            },
            cancel.Cancel);

        if (failure is not null || !payload.Ready())
        {
            if (failure is not OperationCanceledException)
            {
                if (failure is not null)
                {
                    log.Warn("SmokeAPI download failed", failure);
                }

                Error("steamflow_smoke_download_failed");
            }

            return false;
        }

        return true;
    }

    private void Refresh((int AppId, string Path) key)
    {
        var state = files.Detect(key.Path, SmokePayload.Hashes);
        states[key] = new Timed<SmokeState>(state, time.GetUtcNow());
        if (state.Action == SmokeAction.Install && Fresh(scans, key, SafetyLifetime) is null)
        {
            Scan(key);
        }
    }

    private string? Scan((int AppId, string Path) key)
    {
        var signal = scanner.Scan(key.Path);
        scans[key] = new Timed<string?>(signal, time.GetUtcNow());
        return signal;
    }

    private void Forget((int AppId, string Path) key)
    {
        states.TryRemove(key, out _);
        scans.TryRemove(key, out _);
    }

    private Timed<T>? Fresh<T>(ConcurrentDictionary<(int, string), Timed<T>> cache, (int, string) key, TimeSpan lifetime) =>
        cache.TryGetValue(key, out var entry) && time.GetUtcNow() - entry.At < lifetime ? entry : null;

    // No is the default answer: replacing game files is never what an accidental Enter should do.
    private bool Confirm(string titleKey, string body) =>
        flow.ShowMsgBox(body, text.Get(titleKey), MessageBoxButton.YesNo, MessageBoxImage.Warning, MessageBoxResult.No) == MessageBoxResult.Yes;

    private void Notify(string title, string message) => flow.ShowMsg(title, message, Path.Combine(pluginDirectory, Icons.SmokeApi));

    private void Error(string key, params object[] args) =>
        flow.ShowMsgError(text.Get("steamflow_smoke_error_title"), args.Length == 0 ? text.Get(key) : text.Format(key, args));

    private readonly record struct Timed<T>(T Value, DateTimeOffset At);
}
