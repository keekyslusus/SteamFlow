using SteamFlow.Steam;

namespace SteamFlow.Library;

public sealed record LibraryGame(
    int AppId,
    string Name,
    string InstallPath,
    string? IconPath,
    PlayActivity? Activity,
    AchievementProgress? Achievements,
    bool HasCurrentAccountData,
    long StateFlags = 0,
    long SizeOnDisk = 0);

public sealed record LibrarySnapshot(
    bool SteamFound,
    IReadOnlyList<LibraryGame> Games,
    IReadOnlySet<int> HiddenAppIds,
    uint? ActiveAccountId,
    SteamAccount? ActiveAccount,
    int? PersonaState,
    string? ActiveAvatarPath,
    bool HasMultipleAccounts,
    IReadOnlyList<string> SteamAppsFolders,
    string? ConfigFolder)
{
    public static readonly LibrarySnapshot Empty =
        new(false, [], new HashSet<int>(), null, null, null, null, false, [], null);
}
