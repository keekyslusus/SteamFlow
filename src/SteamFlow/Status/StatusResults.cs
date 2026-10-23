using System.Globalization;
using Flow.Launcher.Plugin;
using SteamFlow.Library;
using SteamFlow.Localization;
using SteamFlow.Steam;

namespace SteamFlow.Status;

public sealed class StatusResults(IPublicAPI api, Translator text, LocalLibrary library, SteamClient steam)
{
    public const string Command = "status";

    private const int CurrentScore = 1_000_000;
    private const int OptionScore = 999_000;

    // Steam's EPersonaState values; only these three can be set through steam://friends/status.
    private static readonly (string Protocol, int State)[] Options = [("online", 1), ("offline", 0), ("invisible", 7)];

    public async Task<List<Result>> QueryAsync(string actionKeyword)
    {
        var snapshot = await library.GetAsync();
        var statusQuery = PluginQuery.Build(actionKeyword, Command);
        if (snapshot.ActiveAccountId is null)
        {
            return
            [
                Requery(text.Get("steamflow_status_no_account_title"), text.Get("steamflow_status_no_account_subtitle"), Icons.Community, statusQuery),
            ];
        }

        var account = snapshot.ActiveAccount?.DisplayName ?? text.Get("steamflow_steam_user");
        var current = snapshot.PersonaState;
        var currentProtocol = Options.FirstOrDefault(option => option.State == current).Protocol;
        var results = new List<Result>
        {
            current is { } state
                ? Requery(
                    text.Format("steamflow_status_current", StateLabel(state)),
                    text.Format("steamflow_status_choose_different", account),
                    StatusIcon(currentProtocol),
                    statusQuery)
                : Requery(text.Get("steamflow_status_current_unknown"), text.Format("steamflow_status_choose", account), Icons.Warning, statusQuery),
        };

        results.AddRange(Options
            .Where(option => option.Protocol != currentProtocol)
            .Select((option, index) =>
            {
                var label = StateLabel(option.State);
                return new Result
                {
                    Title = label,
                    SubTitle = text.Format("steamflow_status_set_to", label.ToLower(text.Culture)),
                    IcoPath = StatusIcon(option.Protocol),
                    Score = OptionScore - index,
                    Action = _ =>
                    {
                        steam.SetStatus(option.Protocol);
                        api.ChangeQuery(actionKeyword.Length > 0 ? actionKeyword + " " : "");
                        return true;
                    },
                };
            }));
        return results;
    }

    private string StateLabel(int state) =>
        state is >= 0 and <= 7
            ? text.Get(string.Create(CultureInfo.InvariantCulture, $"steamflow_persona_state_{state}"))
            : text.Format("steamflow_persona_state_unknown", state);

    private static string StatusIcon(string? protocol) => protocol switch
    {
        "online" => Icons.Online,
        "offline" => Icons.Offline,
        "invisible" => Icons.Invisible,
        _ => Icons.Community,
    };

    private Result Requery(string title, string subtitle, string icon, string query) => new()
    {
        Title = title,
        SubTitle = subtitle,
        IcoPath = icon,
        Score = CurrentScore,
        Action = _ =>
        {
            api.ChangeQuery(query, requery: true);
            return false;
        },
    };
}
