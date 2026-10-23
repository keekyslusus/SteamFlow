using Flow.Launcher.Plugin;
using SteamFlow.Library;
using SteamFlow.Localization;
using SteamFlow.Steam;

namespace SteamFlow.Accounts;

public sealed class SwitchResults(Translator text, LocalLibrary library, SteamInstallation installation, SteamUsers users, AccountSwitcher switcher)
{
    public const string Command = "switch";

    public static readonly IReadOnlySet<string> Aliases =
        new HashSet<string> { Command, "switch account", "switch accounts", "account switch", "accounts" };

    private const int TopScore = 21000;

    public async Task<List<Result>> QueryAsync()
    {
        var snapshot = await library.GetAsync();
        var steamPath = installation.FindSteamPath();
        var accounts = steamPath is null ? [] : users.ReadAccounts(steamPath)
            .Where(account => account.AccountId != snapshot.ActiveAccountId)
            .OrderByDescending(account => account.MostRecent)
            .ThenByDescending(account => account.Timestamp)
            .ThenBy(account => account.DisplayName, StringComparer.CurrentCultureIgnoreCase)
            .ToList();

        if (accounts.Count == 0)
        {
            return
            [
                new Result
                {
                    Title = text.Get("steamflow_switch_none"),
                    SubTitle = text.Get("steamflow_switch_none_subtitle"),
                    IcoPath = Icons.Steam,
                    Score = TopScore,
                },
            ];
        }

        return accounts
            .Select((account, index) =>
            {
                var label = account.DisplayName ?? account.SteamId64.ToString();
                var subtitle = text.Format("steamflow_switch_to", label);
                if (account.AccountName.Length > 0 && account.AccountName != label)
                {
                    subtitle = text.Format("steamflow_switch_login_name", subtitle, account.AccountName);
                }

                if (!account.RememberPassword)
                {
                    subtitle = text.Format("steamflow_switch_password_required", subtitle);
                }

                return new Result
                {
                    Title = label,
                    SubTitle = subtitle,
                    IcoPath = SteamUsers.FindAvatar(steamPath!, account) ?? Icons.Steam,
                    Score = TopScore - index,
                    Action = _ =>
                    {
                        switcher.Switch(account);
                        return true;
                    },
                };
            })
            .ToList();
    }
}
