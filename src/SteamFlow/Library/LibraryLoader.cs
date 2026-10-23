using SteamFlow.Diagnostics;
using SteamFlow.Steam;

namespace SteamFlow.Library;

public sealed class LibraryLoader(
    SteamInstallation installation,
    SteamUsers users,
    InstalledGamesReader installedGames,
    LocalConfigReader localConfigs,
    HiddenGamesReader hiddenGames,
    AchievementsReader achievements,
    GameIconLocator icons,
    PluginLog log)
{
    private static readonly TimeSpan SlowLoad = TimeSpan.FromSeconds(1);

    public LibrarySnapshot Load()
    {
        var steamPath = installation.FindSteamPath();
        if (steamPath is null)
        {
            return LibrarySnapshot.Empty;
        }

        var started = log.StartTiming();
        var accounts = users.ReadAccounts(steamPath);
        var activeAccountId = users.ReadActiveAccountId() ?? SteamUsers.SelectLastKnown(accounts)?.AccountId;
        var activeAccount = accounts.FirstOrDefault(account => account.AccountId == activeAccountId);
        var configFolder = SteamUsers.FindConfigFolder(steamPath, activeAccountId);
        var localConfig = configFolder is null ? LocalConfig.Empty : localConfigs.Read(configFolder, activeAccountId);
        var steamAppsFolders = installedGames.FindSteamAppsFolders(steamPath);

        var games = installedGames.Read(steamAppsFolders)
            .Select(game =>
            {
                var gameActivity = localConfig.Activity.GetValueOrDefault(game.AppId);
                var gameAchievements = activeAccountId is { } accountId
                    ? achievements.Read(steamPath, accountId, game.AppId)
                    : new AchievementsState(null, false);
                return new LibraryGame(
                    game.AppId,
                    game.Name,
                    game.InstallPath,
                    icons.Find(steamPath, game.AppId),
                    gameActivity,
                    gameAchievements.Progress,
                    HasCurrentAccountData: gameActivity is not null || gameAchievements.HasStatsFile,
                    game.StateFlags,
                    game.SizeOnDisk);
            })
            .ToList();

        log.Slow("Library load", started, SlowLoad, $"{games.Count} games");
        return new LibrarySnapshot(
            SteamFound: true,
            games,
            configFolder is null ? new HashSet<int>() : hiddenGames.Read(configFolder),
            activeAccountId,
            activeAccount,
            localConfig.PersonaState,
            SteamUsers.FindAvatar(steamPath, activeAccount),
            HasMultipleAccounts: accounts.Count > 1,
            steamAppsFolders,
            configFolder);
    }
}
