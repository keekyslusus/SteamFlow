using System.Security.Cryptography;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace SteamFlow.Smoke;

public enum SmokeAction
{
    None,
    Install,
    Remove,
}

public sealed record SmokeState(IReadOnlyList<string> Installed, IReadOnlyList<string> Installable, IReadOnlyList<string> Ambiguous)
{
    // A folder that has both a live DLL and a backup but no SmokeAPI marks is left alone: guessing could
    // overwrite the only original copy.
    public SmokeAction Action =>
        Installed.Count > 0 ? SmokeAction.Remove
        : Installable.Count > 0 && Ambiguous.Count == 0 ? SmokeAction.Install
        : SmokeAction.None;
}

public sealed record SmokeOperation(int Total, int Successful, int ChangedDlls, IReadOnlyList<string> Errors, IReadOnlyList<string> BackupMissing)
{
    public bool Succeeded => Total > 0 && Errors.Count == 0 && BackupMissing.Count == 0;

    public bool Partial => ChangedDlls > 0 && !Succeeded;
}

public sealed class SmokeApiFiles
{
    private static readonly (string Live, string Backup)[] ApiFiles =
        [("steam_api.dll", "steam_api_o.dll"), ("steam_api64.dll", "steam_api64_o.dll")];

    private static readonly string[] ConfigFiles = ["SmokeAPI.config.json", "SmokeAPI.json"];
    private static readonly string[] LeftoverFiles = ["SmokeAPI.cache.json", "SmokeAPI.log", "SmokeAPI.log.log"];

    private static readonly EnumerationOptions Walk = new()
    {
        RecurseSubdirectories = true,
        IgnoreInaccessible = true,
        AttributesToSkip = FileAttributes.ReparsePoint,
    };

    private static readonly JsonObject Config = new()
    {
        ["$version"] = 4,
        ["logging"] = false,
        ["log_steam_http"] = false,
        ["default_app_status"] = "unlocked",
        ["override_app_status"] = new JsonObject(),
        ["override_dlc_status"] = new JsonObject(),
        ["auto_inject_inventory"] = true,
        ["extra_inventory_items"] = new JsonArray(),
        ["extra_dlcs"] = new JsonObject(),
    };

    // SHA-256 of the SmokeAPI DLLs by file name, used to recognize an install that lost its config file.
    public SmokeState Detect(string installPath, IReadOnlyDictionary<string, string> smokeHashes)
    {
        List<string> installed = [], installable = [], ambiguous = [];
        foreach (var directory in CandidateDirectories(installPath))
        {
            var names = Files(directory);
            if (IsSmokeApi(names, smokeHashes))
            {
                installed.Add(directory);
                continue;
            }

            var hasLive = ApiFiles.Any(pair => names.ContainsKey(pair.Live));
            var hasBackup = ApiFiles.Any(pair => names.ContainsKey(pair.Backup));
            if (hasLive && hasBackup)
            {
                ambiguous.Add(directory);
            }
            else if (hasLive)
            {
                installable.Add(directory);
            }
        }

        return new SmokeState(installed, installable, ambiguous);
    }

    public SmokeOperation Install(string installPath, string payloadFolder, IReadOnlyDictionary<string, string> smokeHashes)
    {
        var state = Detect(installPath, smokeHashes);
        if (state.Action != SmokeAction.Install)
        {
            return new SmokeOperation(0, 0, 0, ["not_installable"], []);
        }

        int successful = 0, changed = 0;
        var errors = new List<string>();
        foreach (var directory in state.Installable)
        {
            var names = Files(directory);
            var directoryChanged = 0;
            var directoryFailed = false;
            foreach (var (live, backup) in ApiFiles)
            {
                if (!names.TryGetValue(live, out var livePath))
                {
                    continue;
                }

                var backupPath = Path.Combine(directory, backup);
                try
                {
                    File.Move(livePath, backupPath);
                    try
                    {
                        File.Copy(Path.Combine(payloadFolder, live), Path.Combine(directory, live));
                    }
                    catch
                    {
                        // Put the original back so a failed copy never leaves the game without its DLL.
                        File.Delete(Path.Combine(directory, live));
                        File.Move(backupPath, Path.Combine(directory, live));
                        throw;
                    }

                    directoryChanged++;
                    changed++;
                }
                catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
                {
                    directoryFailed = true;
                    errors.Add($"{directory}:{live}:{ex.Message}");
                }
            }

            if (directoryChanged > 0)
            {
                try
                {
                    var configPath = Path.Combine(directory, "SmokeAPI.config.json");
                    File.WriteAllText(configPath + ".tmp", Config.ToJsonString(new JsonSerializerOptions { WriteIndented = true }) + "\n");
                    File.Move(configPath + ".tmp", configPath, overwrite: true);
                }
                catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
                {
                    directoryFailed = true;
                    errors.Add($"{directory}:SmokeAPI.config.json:{ex.Message}");
                }
            }

            if (directoryChanged > 0 && !directoryFailed)
            {
                successful++;
            }
        }

        return new SmokeOperation(state.Installable.Count, successful, changed, errors, []);
    }

    public SmokeOperation Remove(string installPath, IReadOnlyDictionary<string, string> smokeHashes)
    {
        var state = Detect(installPath, smokeHashes);
        if (state.Installed.Count == 0)
        {
            return new SmokeOperation(0, 0, 0, ["not_installed"], []);
        }

        int successful = 0, changed = 0;
        List<string> errors = [], backupMissing = [];
        foreach (var directory in state.Installed)
        {
            var names = Files(directory);
            var restored = 0;
            var directoryFailed = false;
            var directoryBackupMissing = false;
            foreach (var (live, backup) in ApiFiles)
            {
                if (!names.TryGetValue(backup, out var backupPath))
                {
                    if (names.ContainsKey(live))
                    {
                        backupMissing.Add($"{directory}:{backup}");
                        directoryBackupMissing = true;
                    }

                    continue;
                }

                try
                {
                    File.Move(backupPath, Path.Combine(directory, live), overwrite: true);
                    restored++;
                    changed++;
                }
                catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
                {
                    directoryFailed = true;
                    errors.Add($"{directory}:{live}:{ex.Message}");
                }
            }

            // Without a backup the SmokeAPI DLL stays, so its config stays with it to keep the game working.
            var cleanup = directoryBackupMissing ? LeftoverFiles : [.. ConfigFiles, .. LeftoverFiles];
            foreach (var name in cleanup)
            {
                if (Files(directory).TryGetValue(name, out var path))
                {
                    try
                    {
                        File.Delete(path);
                    }
                    catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
                    {
                        directoryFailed = true;
                        errors.Add($"{directory}:{name}:{ex.Message}");
                    }
                }
            }

            if (restored > 0 && !directoryFailed)
            {
                successful++;
            }
        }

        return new SmokeOperation(state.Installed.Count, successful, changed, errors, backupMissing);
    }

    public static string Sha256(string path)
    {
        using var stream = File.OpenRead(path);
        return Convert.ToHexString(SHA256.HashData(stream));
    }

    private static bool IsSmokeApi(Dictionary<string, string> names, IReadOnlyDictionary<string, string> smokeHashes)
    {
        if (ConfigFiles.Any(names.ContainsKey))
        {
            return true;
        }

        if (ApiFiles.Any(pair => names.ContainsKey(pair.Backup)) && LeftoverFiles.Any(names.ContainsKey))
        {
            return true;
        }

        foreach (var (live, _) in ApiFiles)
        {
            try
            {
                if (names.TryGetValue(live, out var path)
                    && smokeHashes.TryGetValue(live, out var hash)
                    && Sha256(path).Equals(hash, StringComparison.OrdinalIgnoreCase))
                {
                    return true;
                }
            }
            catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
            {
            }
        }

        return false;
    }

    private static IEnumerable<string> CandidateDirectories(string installPath)
    {
        if (!Directory.Exists(installPath))
        {
            return [];
        }

        var interesting = ApiFiles.SelectMany(pair => new[] { pair.Live, pair.Backup })
            .Concat(ConfigFiles)
            .Concat(LeftoverFiles)
            .ToHashSet(StringComparer.OrdinalIgnoreCase);
        return new[] { installPath }
            .Concat(Directory.EnumerateDirectories(installPath, "*", Walk))
            .Where(directory => Files(directory).Keys.Any(interesting.Contains))
            .ToList();
    }

    private static Dictionary<string, string> Files(string directory)
    {
        try
        {
            return Directory.EnumerateFiles(directory)
                .ToDictionary(path => Path.GetFileName(path), path => path, StringComparer.OrdinalIgnoreCase);
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
            return new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        }
    }
}
