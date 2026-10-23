namespace SteamFlow.Smoke;

// SmokeAPI replaces the Steam API DLL, which kernel anti-cheats can flag as tampering and ban for.
public sealed class AntiCheatScanner
{
    private static readonly (string Kind, string Name, string Label)[] Markers =
    [
        ("file", "start_protected_game.exe", "Easy Anti-Cheat"),
        ("directory", "EasyAntiCheat", "Easy Anti-Cheat"),
        ("directory", "EasyAntiCheat_EOS", "Easy Anti-Cheat"),
        ("directory", "BattlEye", "BattlEye"),
        ("prefix", "BEService", "BattlEye"),
        ("prefix", "BEClient", "BattlEye"),
        ("file", "EAAntiCheat.GameServiceLauncher.dll", "EA AntiCheat"),
        ("file", "EAAntiCheat.GameServiceLauncher.exe", "EA AntiCheat"),
        ("file", "EAAntiCheat.Installer.exe", "EA AntiCheat"),
        ("file", "NeacClient.exe", "NetEase AntiCheat Experts"),
        ("file", "FragNeacClient.exe", "NetEase AntiCheat Experts"),
        ("file", "NSHNeacClient.exe", "NetEase AntiCheat Experts"),
        ("directory", "AntiCheatExpert", "AntiCheatExpert"),
        ("file", "ACE-Service64.exe", "AntiCheatExpert"),
        ("file", "ACE-Setup64.exe", "AntiCheatExpert"),
        ("file", "AntiCheatInstaller.exe", "AnyBrain AntiCheat"),
    ];

    private static readonly EnumerationOptions Walk = new()
    {
        RecurseSubdirectories = true,
        IgnoreInaccessible = true,
        AttributesToSkip = FileAttributes.ReparsePoint,
    };

    // Returns the first anti-cheat found, or null; one is enough to warn, so the walk stops there.
    public string? Scan(string installPath)
    {
        if (!Directory.Exists(installPath))
        {
            throw new DirectoryNotFoundException(installPath);
        }

        foreach (var entry in Directory.EnumerateFileSystemEntries(installPath, "*", Walk))
        {
            var name = Path.GetFileName(entry);
            var isDirectory = Directory.Exists(entry);
            foreach (var (kind, marker, label) in Markers)
            {
                var found = kind switch
                {
                    "directory" => isDirectory && name.Equals(marker, StringComparison.OrdinalIgnoreCase),
                    "file" => !isDirectory && name.Equals(marker, StringComparison.OrdinalIgnoreCase),
                    _ => !isDirectory
                        && name.StartsWith(marker, StringComparison.OrdinalIgnoreCase)
                        && Path.GetExtension(name) is var extension
                        && (extension.Equals(".exe", StringComparison.OrdinalIgnoreCase) || extension.Equals(".dll", StringComparison.OrdinalIgnoreCase)),
                };
                if (found)
                {
                    return label;
                }
            }
        }

        return null;
    }
}
