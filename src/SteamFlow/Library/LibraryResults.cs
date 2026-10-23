using System.Globalization;
using Flow.Launcher.Plugin;
using SteamFlow.Downloads;
using SteamFlow.Friends;
using SteamFlow.Localization;
using SteamFlow.Settings;
using SteamFlow.Smoke;
using SteamFlow.Steam;
using SteamFlow.Store;
using SteamFlow.WebApi;

namespace SteamFlow.Library;

// Completion is set when player counts or download progress were still loading; it rebuilds the results once they arrived.
// Live means a shown game has download progress that keeps changing while the results stay open.
public sealed record LocalSearch(
    List<Result> Results,
    IReadOnlySet<int> AppIds,
    IReadOnlySet<int> HiddenAppIds,
    Task<List<Result>>? Completion = null,
    bool Live = false);

public sealed class LibraryResults(
    IPublicAPI api,
    Translator text,
    PluginSettings settings,
    LocalLibrary library,
    LibrarySubtitles subtitles,
    GameContextMenu gameMenu,
    SteamClientMenu steamClientMenu,
    StoreCatalog catalog,
    OwnedGamesService ownedGames,
    ProfileService profile,
    FriendsService friends,
    SmokeApiService smokeApi,
    DownloadStatuses downloads,
    DownloadProgress downloadProgress,
    DownloadControl downloadControl,
    SteamClient steam)
{
    private const int MaxSearchResults = 5;
    private const int MaxEmptyQueryResults = 67;
    private const int LaunchSteamScore = 10000;

    // Installed games always rank above store results, whose scores stay below this.
    private const int LocalSearchScoreBase = 1000;

    // Results show after this even if player counts are still loading; they are pushed when ready.
    private static readonly TimeSpan PlayerCountDeadline = TimeSpan.FromMilliseconds(500);

    public async Task<LocalSearch> EmptyQueryAsync()
    {
        var snapshot = await library.GetAsync();
        if (!snapshot.SteamFound)
        {
            return new LocalSearch([SteamNotFound()], new HashSet<int>(), new HashSet<int>());
        }

        var downloadView = downloads.Snapshot();
        var games = VisibleGames(snapshot, downloadView);
        var owned = await ownedGames.CurrentAsync();
        var playing = await friends.PlayingByAppAsync();
        var results = new List<Result>
        {
            LaunchSteam(snapshot, await profile.CachedSummaryAsync(), await profile.FramedAvatarAsync(snapshot.ActiveAvatarPath)),
        };
        if (games.Count == 0)
        {
            results.Add(Message(text.Get("steamflow_plugin_title"), text.Get("steamflow_no_installed_games")));
            return new LocalSearch(results, new HashSet<int>(), new HashSet<int>());
        }

        var ordered = settings.SortLocalByRecent
            ? games.OrderByDescending(game => game.Activity?.LastPlayed ?? DateTimeOffset.MinValue)
                .ThenBy(game => game.Name, StringComparer.CurrentCultureIgnoreCase)
            : games.OrderBy(game => game.Name, StringComparer.CurrentCultureIgnoreCase);

        var shown = ordered.Take(MaxEmptyQueryResults).ToList();
        var live = AnyProgressWanted(downloadView, shown);
        var progress = await downloadProgress.ForAsync(live, CancellationToken.None);

        // Flow sorts by score, so the score has to carry the order chosen here.
        List<Result> Build(IReadOnlyDictionary<int, AppProgress> known) => results
            .Concat(shown.Select((game, index) => GameResult(
                snapshot, owned, downloadView, known, game, MaxEmptyQueryResults - index, highlight: null, players: null, playing.GetValueOrDefault(game.AppId))))
            .ToList();

        return new LocalSearch(
            Build(progress.Known),
            new HashSet<int>(),
            new HashSet<int>(),
            progress.Late?.ContinueWith(late => Build(late.Result), TaskScheduler.Default),
            live);
    }

    public async Task<LocalSearch> SearchAsync(string search, CancellationToken token)
    {
        var snapshot = await library.GetAsync();
        if (!snapshot.SteamFound)
        {
            return new LocalSearch([SteamNotFound()], new HashSet<int>(), new HashSet<int>());
        }

        var downloadView = downloads.Snapshot();
        var matches = VisibleGames(snapshot, downloadView)
            .Select(game => (Game: game, Match: api.FuzzySearch(search, game.Name)))
            .Where(candidate => candidate.Match.IsSearchPrecisionScoreMet())
            .OrderByDescending(candidate => candidate.Match.Score)
            .Take(MaxSearchResults)
            .ToList();
        var owned = await ownedGames.CurrentAsync();
        var live = AnyProgressWanted(downloadView, matches.Select(candidate => candidate.Game));
        var pendingProgress = downloadProgress.ForAsync(live, token);

        var players = settings.ShowPlayerCount
            ? matches.ToDictionary(candidate => candidate.Game.AppId, candidate => catalog.PlayersAsync(candidate.Game.AppId))
            : [];
        var allPlayers = Task.WhenAll(players.Values);
        await Task.WhenAny(allPlayers, Task.Delay(PlayerCountDeadline, token));
        var progress = await pendingProgress;
        token.ThrowIfCancellationRequested();

        List<Result> Build(IReadOnlyDictionary<int, AppProgress> known) => matches
            .Select(candidate => GameResult(
                snapshot,
                owned,
                downloadView,
                known,
                candidate.Game,
                LocalSearchScoreBase + candidate.Match.Score,
                candidate.Match.MatchData,
                players.TryGetValue(candidate.Game.AppId, out var count) && count.IsCompletedSuccessfully ? count.Result : null))
            .ToList();

        async Task<List<Result>> CompleteAsync()
        {
            await allPlayers.ContinueWith(_ => { }, TaskScheduler.Default);
            return Build(progress.Late is { } late ? await late : progress.Known);
        }

        return new LocalSearch(
            Build(progress.Known),
            matches.Select(candidate => candidate.Game.AppId).ToHashSet(),
            settings.HideHiddenGames ? snapshot.HiddenAppIds : new HashSet<int>(),
            allPlayers.IsCompleted && progress.Late is null ? null : CompleteAsync(),
            live);
    }

    // Store lists should not offer games the user already has or hid in Steam.
    public async Task<IReadOnlySet<int>> OwnedInstalledOrHiddenAsync()
    {
        var snapshot = await library.GetAsync();
        var downloadView = downloads.Snapshot();
        var excluded = snapshot.Games.Where(game => !downloadView.IsUninstalled(game.AppId)).Select(game => game.AppId).ToHashSet();
        excluded.UnionWith((await ownedGames.CurrentAsync()).Games.AppIds);
        if (settings.HideHiddenGames)
        {
            excluded.UnionWith(snapshot.HiddenAppIds);
        }

        return excluded;
    }

    private List<LibraryGame> VisibleGames(LibrarySnapshot snapshot, DownloadView downloadView)
    {
        var blacklist = settings.BlacklistedAppIdSet();
        return snapshot.Games
            .Where(game => !downloadView.IsUninstalled(game.AppId))
            .Where(game => !blacklist.Contains(game.AppId))
            .Where(game => !settings.HideHiddenGames || !snapshot.HiddenAppIds.Contains(game.AppId))
            .ToList();
    }

    private static bool AnyProgressWanted(DownloadView view, IEnumerable<LibraryGame> games) =>
        games.Any(game => DownloadProgress.Wanted(view, game.AppId, view.StatusOf(game.AppId, game.StateFlags)));

    private Result GameResult(
        LibrarySnapshot snapshot,
        OwnedView owned,
        DownloadView downloadView,
        IReadOnlyDictionary<int, AppProgress> progress,
        LibraryGame game,
        int score,
        List<int>? highlight,
        PlayerCount? players,
        IReadOnlyList<string>? friendsPlaying = null)
    {
        var ownership = owned.StateOf(game.AppId);
        var download = downloadView.StatusOf(game.AppId, game.StateFlags);
        var canControl = downloadView.CanControl(download);
        var gameProgress = DownloadProgress.Wanted(downloadView, game.AppId, download) ? progress.GetValueOrDefault(game.AppId) : null;

        // The refund item and the other-account notice need store details; fetch them now so they are cached in time.
        // Other games are left out: appdetails for a whole library page gets the IP blocked from the store.
        smokeApi.Prefetch(game.AppId, game.InstallPath);
        if (RefundEligibility.MayBeEligible(game) || (ownership == Ownership.NotOwned && !game.HasCurrentAccountData))
        {
            _ = catalog.DetailsAsync(game.AppId);
        }

        return new Result
        {
            Title = download == DownloadStatus.None ? game.Name : text.Format("steamflow_game_with_status", game.Name, StatusLabel(download)),
            SubTitle = subtitles.Build(
                game,
                snapshot.HasMultipleAccounts,
                players,
                ownership,
                catalog.PeekDetails(game.AppId)?.IsFree == true,
                friendsPlaying,
                download,
                canControl,
                gameProgress),
            IcoPath = game.IconPath ?? Icons.Steam,
            Score = score,
            TitleHighlightData = highlight,
            ContextData = new ResultMenu(() => gameMenu.Build(new GameMenuTarget(
                game.AppId,
                game.Name,
                game.InstallPath,
                Refund: RefundEligibility.Evaluate(game, catalog.PeekDetails(game.AppId)),
                IsOwned: ownership == Ownership.Owned,
                SizeOnDisk: game.SizeOnDisk,
                Developers: catalog.PeekDetails(game.AppId)?.Developers,
                Publishers: catalog.PeekDetails(game.AppId)?.Publishers))),
            // While Steam is updating the game, Enter pauses or resumes instead of launching it, as in the Python plugin.
            AsyncAction = async _ =>
            {
                if (canControl)
                {
                    await downloadControl.ChangeAsync(game.AppId, game.Name, pause: download == DownloadStatus.Updating);
                }
                else
                {
                    steam.LaunchGame(game.AppId);
                }

                return true;
            },
        };
    }

    private string StatusLabel(DownloadStatus status) => text.Get(status switch
    {
        DownloadStatus.Updating => "steamflow_download_status_updating",
        DownloadStatus.Paused => "steamflow_download_status_paused",
        DownloadStatus.Queued => "steamflow_download_status_queued",
        _ => "steamflow_download_status_required",
    });

    private Result LaunchSteam(LibrarySnapshot snapshot, ProfileSummary? summary, string? framedAvatar) => new()
    {
        Title = text.Get("steamflow_launch_steam"),
        SubTitle = LaunchSteamSubtitle(snapshot, summary),
        IcoPath = framedAvatar ?? snapshot.ActiveAvatarPath ?? Icons.Steam,
        Score = LaunchSteamScore,
        ContextData = new ResultMenu(steamClientMenu.Build),
        Action = _ =>
        {
            steam.OpenLibrary();
            return true;
        },
    };

    private string LaunchSteamSubtitle(LibrarySnapshot snapshot, ProfileSummary? summary)
    {
        var subtitle = text.Format(
            "steamflow_launch_steam_subtitle",
            snapshot.ActiveAccount?.DisplayName ?? text.Get("steamflow_steam_user"));
        if (summary is null)
        {
            return subtitle;
        }

        var status = summary.GameName.Length > 0
            ? text.Format("steamflow_profile_playing", summary.GameName)
            : summary.PersonaState is >= 0 and <= 7
                ? text.Get(string.Create(CultureInfo.InvariantCulture, $"steamflow_persona_state_{summary.PersonaState}"))
                : null;
        return status is null ? subtitle : text.Format("steamflow_launch_steam_subtitle_with_status", subtitle, status);
    }

    private Result SteamNotFound() =>
        Message(text.Get("steamflow_steam_not_found_title"), text.Get("steamflow_steam_not_found_subtitle"));

    private static Result Message(string title, string subtitle) => new()
    {
        Title = title,
        SubTitle = subtitle,
        IcoPath = Icons.Steam,
    };
}
