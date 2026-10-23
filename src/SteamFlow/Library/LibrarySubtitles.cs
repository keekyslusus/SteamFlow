using System.Text;
using SteamFlow.Downloads;
using SteamFlow.Localization;
using SteamFlow.Settings;
using SteamFlow.Store;
using SteamFlow.WebApi;

namespace SteamFlow.Library;

public sealed class LibrarySubtitles(Translator text, PluginSettings settings, TimeProvider time)
{
    private const string Separator = " | ";

    public string Build(
        LibraryGame game,
        bool hasMultipleAccounts,
        PlayerCount? players = null,
        Ownership ownership = Ownership.Unknown,
        bool isFree = false,
        IReadOnlyList<string>? friendsPlaying = null,
        DownloadStatus download = DownloadStatus.None,
        bool canControl = false,
        AppProgress? progress = null)
    {
        var subtitle = new StringBuilder(text.Get(download switch
        {
            DownloadStatus.Updating => canControl ? "steamflow_download_pause" : "steamflow_download_updating",
            DownloadStatus.Paused => canControl ? "steamflow_download_resume" : "steamflow_download_update_paused",
            DownloadStatus.Queued => "steamflow_download_update_queued",
            DownloadStatus.Required => "steamflow_download_update_required",
            _ => "steamflow_launch_game",
        }));

        if (progress is not null)
        {
            subtitle.Append(Separator).Append(progress.SecondsLeft is { } seconds
                ? text.Format("steamflow_download_progress_with_eta", progress.Percent, FormatTimeLeft(seconds))
                : text.Format("steamflow_download_progress", progress.Percent));
        }

        if (friendsPlaying is { Count: > 0 })
        {
            subtitle.Append(Separator).Append(friendsPlaying.Count == 1
                ? text.Format("steamflow_friend_playing", friendsPlaying[0])
                : text.Format("steamflow_friends_playing", friendsPlaying.Count));
        }

        if (settings.ShowPlaytime && game.Activity?.PlaytimeMinutes is { } minutes)
        {
            subtitle.Append(Separator).Append(FormatPlaytime(minutes));
        }

        if (settings.ShowAchievements
            && game.Achievements is { Total: > 0 } achievements
            && (achievements.Unlocked > 0 || game.HasCurrentAccountData))
        {
            subtitle.Append(Separator).Append(text.Format("steamflow_achievements", achievements.Unlocked, achievements.Total));
        }

        if (settings.ShowLastPlayed && game.Activity?.LastPlayed is { } lastPlayed)
        {
            var date = FormatLastPlayed(lastPlayed.ToLocalTime().DateTime, time.GetLocalNow().DateTime);
            subtitle.Append(Separator).Append(text.Format("steamflow_last_played", date));
        }

        // Free games are playable from any account, so only paid installs are attributed to another one.
        if (ownership == Ownership.NotOwned && !game.HasCurrentAccountData && !isFree)
        {
            subtitle.Append(Separator).Append(text.Get("steamflow_account_installed_other"));
        }
        else if (ownership == Ownership.Unknown && hasMultipleAccounts && !game.HasCurrentAccountData)
        {
            subtitle.Append(Separator).Append(text.Get("steamflow_account_no_current_data"));
        }

        if (settings.ShowPlayerCount && players is { Value: > 0 })
        {
            subtitle.Append(Separator).Append(text.Format("steamflow_player_count", players.Value));
        }

        return subtitle.ToString();
    }

    public string FormatPlaytime(int minutes) => PlaytimeText.Format(text, minutes);

    // Rounded up, so the last seconds of a download read as "1 min" rather than "0 min".
    public string FormatTimeLeft(int seconds)
    {
        var minutes = (seconds + 59) / 60;
        return minutes < 60
            ? text.Format("steamflow_download_eta_minutes", minutes)
            : text.Format("steamflow_download_eta_hours", minutes / 60, minutes % 60);
    }

    public string FormatLastPlayed(DateTime playedAt, DateTime now)
    {
        var daysAgo = (now.Date - playedAt.Date).Days;
        return daysAgo switch
        {
            0 => text.Get("steamflow_today"),
            1 => text.Get("steamflow_yesterday"),
            >= 2 and <= 7 => text.Format("steamflow_days_ago", daysAgo),
            _ when playedAt.Year == now.Year => text.Format("steamflow_date_short", playedAt),
            _ => text.Format("steamflow_date_short_with_year", playedAt),
        };
    }
}
