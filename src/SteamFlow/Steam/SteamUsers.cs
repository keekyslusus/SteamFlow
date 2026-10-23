using System.Globalization;
using Microsoft.Win32;
using SteamFlow.Diagnostics;

namespace SteamFlow.Steam;

public sealed record SteamAccount(
    ulong SteamId64,
    string AccountName,
    string PersonaName,
    bool MostRecent,
    long Timestamp,
    bool RememberPassword = true)
{
    private const ulong SteamId64Offset = 76561197960265728;

    public uint AccountId => (uint)(SteamId64 - SteamId64Offset);

    public static ulong ToSteamId64(uint accountId) => SteamId64Offset + accountId;

    public string? DisplayName =>
        !string.IsNullOrEmpty(PersonaName) ? PersonaName : !string.IsNullOrEmpty(AccountName) ? AccountName : null;
}

public sealed class SteamUsers(PluginLog log)
{
    public uint? ReadActiveAccountId()
    {
        using var key = Registry.CurrentUser.OpenSubKey(@"Software\Valve\Steam\ActiveProcess");
        return key?.GetValue("ActiveUser") is int value && value != 0 ? unchecked((uint)value) : null;
    }

    public IReadOnlyList<SteamAccount> ReadAccounts(string steamPath)
    {
        var path = Path.Combine(steamPath, "config", "loginusers.vdf");
        if (!File.Exists(path))
        {
            return [];
        }

        try
        {
            var accounts = new List<SteamAccount>();
            foreach (var user in Vdf.ReadText(path).Items())
            {
                if (ulong.TryParse(user.Name, NumberStyles.None, CultureInfo.InvariantCulture, out var steamId64))
                {
                    accounts.Add(new SteamAccount(
                        steamId64,
                        user.Text("AccountName") ?? "",
                        user.Text("PersonaName") ?? "",
                        user.Text("MostRecent") == "1",
                        user.Number("Timestamp") ?? 0,
                        user.Text("RememberPassword") != "0"));
                }
            }

            return accounts;
        }
        catch (Exception ex) when (Vdf.IsReadError(ex))
        {
            log.Warn("loginusers.vdf unreadable", ex);
            return [];
        }
    }

    // Used when Steam is not running: the registry has no active user, so fall back to the last login.
    public static SteamAccount? SelectLastKnown(IReadOnlyList<SteamAccount> accounts) =>
        accounts.Where(account => account.MostRecent).MaxBy(account => account.Timestamp)
        ?? accounts.MaxBy(account => account.Timestamp);

    public static string? FindConfigFolder(string steamPath, uint? accountId)
    {
        var userData = Path.Combine(steamPath, "userdata");
        if (!Directory.Exists(userData))
        {
            return null;
        }

        if (accountId is { } id)
        {
            var activeConfig = Path.Combine(userData, id.ToString(CultureInfo.InvariantCulture), "config");
            if (File.Exists(Path.Combine(activeConfig, "localconfig.vdf")))
            {
                return activeConfig;
            }
        }

        return Directory.EnumerateDirectories(userData)
            .Select(folder => Path.Combine(folder, "config"))
            .Where(config => File.Exists(Path.Combine(config, "localconfig.vdf")))
            .OrderByDescending(config => File.GetLastWriteTimeUtc(Path.Combine(config, "localconfig.vdf")))
            .FirstOrDefault();
    }

    public static string? FindAvatar(string steamPath, SteamAccount? account)
    {
        if (account is null)
        {
            return null;
        }

        var path = Path.Combine(steamPath, "config", "avatarcache", $"{account.SteamId64}.png");
        return File.Exists(path) ? path : null;
    }
}
