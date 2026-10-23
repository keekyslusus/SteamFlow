using System.ComponentModel;
using System.Diagnostics;
using System.Globalization;
using Flow.Launcher.Plugin;
using Microsoft.Win32;
using SteamFlow.Diagnostics;
using SteamFlow.Library;
using SteamFlow.Localization;
using SteamFlow.Steam;

namespace SteamFlow.Accounts;

public sealed class AccountSwitcher(
    SteamInstallation installation,
    LocalLibrary library,
    SteamClient steam,
    IPublicAPI flow,
    Translator text,
    PluginLog log)
{
    private static readonly string[] SteamProcesses = ["steam", "steamwebhelper", "GameOverlayUI", "steamservice"];
    private static readonly TimeSpan ShutdownWait = TimeSpan.FromSeconds(10);
    private static readonly TimeSpan KillWait = TimeSpan.FromSeconds(10);

    // Steam rewrites its own files on exit; starting it again right away can race with that.
    private static readonly TimeSpan RelaunchDelay = TimeSpan.FromSeconds(4);

    // steamservice can keep running as a Windows service and does not stop Steam from starting again.
    private const string IgnoredProcess = "steamservice";

    private int switching;

    public void Switch(SteamAccount target)
    {
        if (Interlocked.Exchange(ref switching, 1) == 1)
        {
            return;
        }

        _ = Task.Run(async () =>
        {
            try
            {
                await SwitchAsync(target);
            }
            catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or Win32Exception or InvalidOperationException or ValveKeyValue.KeyValueException)
            {
                log.Warn("Account switch failed", ex);
                Fail(ex.Message);
            }
            finally
            {
                Interlocked.Exchange(ref switching, 0);
            }
        });
    }

    private async Task SwitchAsync(SteamAccount target)
    {
        if (installation.FindSteamPath() is not { } steamPath)
        {
            Fail(text.Get("steamflow_switch_steam_not_found"));
            return;
        }

        var loginUsersPath = Path.Combine(steamPath, "config", "loginusers.vdf");
        var steamId64 = target.SteamId64.ToString(CultureInfo.InvariantCulture);
        if (!File.Exists(loginUsersPath) || LoginUsersFile.Read(loginUsersPath).AccountName(steamId64) is not { Length: > 0 })
        {
            Fail(text.Get("steamflow_switch_account_not_found"));
            return;
        }

        // Games are child processes of Steam, so the forced shutdown below would kill one without letting it save.
        if (RunningAppId() is { } runningAppId)
        {
            var game = (await library.GetAsync()).Games.FirstOrDefault(game => game.AppId == runningAppId);
            Fail(game is { Name.Length: > 0 }
                ? text.Format("steamflow_switch_game_running", game.Name)
                : text.Get("steamflow_switch_game_running_unknown"));
            return;
        }

        await StopSteamAsync(steamPath);

        // Read again after Steam exited: it saves loginusers.vdf on shutdown and would overwrite an earlier edit.
        var loginUsers = LoginUsersFile.Read(loginUsersPath);
        if (!loginUsers.MakeAutoLogin(steamId64))
        {
            Fail(text.Get("steamflow_switch_account_not_found"));
            return;
        }

        loginUsers.Write(loginUsersPath);
        using (var key = Registry.CurrentUser.CreateSubKey(@"Software\Valve\Steam"))
        {
            key.SetValue("AutoLoginUser", loginUsers.AccountName(steamId64)!, RegistryValueKind.String);
            key.SetValue("RememberPassword", 1, RegistryValueKind.DWord);
        }

        await Task.Delay(RelaunchDelay);
        steam.OpenLibrary();
        library.Reload();
    }

    // A clean shutdown lets Steam save its state; forcing it is only the fallback the Python plugin always used.
    private static async Task StopSteamAsync(string steamPath)
    {
        if (!AnyRunning())
        {
            return;
        }

        var steamExe = Path.Combine(steamPath, "steam.exe");
        if (File.Exists(steamExe))
        {
            Process.Start(new ProcessStartInfo(steamExe, "-shutdown") { UseShellExecute = false, CreateNoWindow = true })?.Dispose();
            if (await WaitUntilStoppedAsync(ShutdownWait))
            {
                return;
            }
        }

        foreach (var name in SteamProcesses)
        {
            foreach (var process in Process.GetProcessesByName(name))
            {
                using (process)
                {
                    try
                    {
                        process.Kill(entireProcessTree: true);
                    }
                    catch (Exception ex) when (ex is Win32Exception or InvalidOperationException)
                    {
                        // Elevated helpers can refuse; the wait below decides whether that matters.
                    }
                }
            }
        }

        if (!await WaitUntilStoppedAsync(KillWait))
        {
            throw new InvalidOperationException("Steam did not exit");
        }
    }

    // Steam leaves the value behind when it crashes, so it only counts while Steam is running.
    private static int? RunningAppId()
    {
        using var key = Registry.CurrentUser.OpenSubKey(@"Software\Valve\Steam");
        return key?.GetValue("RunningAppID") is int appId && appId != 0 && AnyRunning() ? appId : null;
    }

    private static async Task<bool> WaitUntilStoppedAsync(TimeSpan timeout)
    {
        var deadline = DateTime.UtcNow + timeout;
        while (DateTime.UtcNow < deadline)
        {
            if (!AnyRunning())
            {
                return true;
            }

            await Task.Delay(500);
        }

        return !AnyRunning();
    }

    private static bool AnyRunning() =>
        SteamProcesses.Where(name => name != IgnoredProcess).Any(name =>
        {
            var processes = Process.GetProcessesByName(name);
            foreach (var process in processes)
            {
                process.Dispose();
            }

            return processes.Length > 0;
        });

    private void Fail(string message) =>
        flow.ShowMsgError(text.Get("steamflow_switch_failed_title"), message);
}
