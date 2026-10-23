using System.Globalization;
using System.Text.Json;
using Flow.Launcher.Plugin;
using SteamFlow.Diagnostics;
using SteamFlow.Library;
using SteamFlow.Localization;
using SteamFlow.Steam;

namespace SteamFlow.WebApi;

public sealed class ApiResults(
    IPublicAPI api,
    Translator text,
    ApiKeyStore keys,
    OwnedGamesService ownedGames,
    LocalLibrary library,
    SteamClient steam,
    PluginLog log,
    string pluginDirectory,
    TimeProvider time)
{
    public const string Command = "api";

    public static readonly IReadOnlySet<string> Aliases = new HashSet<string> { Command, "api key", "apikey", "owned", "owned games" };

    public async Task<List<Result>> QueryAsync()
    {
        var snapshot = await library.GetAsync();
        var activeId = snapshot.ActiveAccountId is { } id ? SteamAccount.ToSteamId64(id) : (ulong?)null;
        var others = keys.All().Where(key => key.SteamId64 != activeId).Select(RemoveOtherKey);
        if (activeId is { } steamId64 && keys.For(steamId64) is { } key)
        {
            var status = await StatusAsync(key);
            status.Score = 20000;
            return
            [
                status,
                new Result
                {
                    Title = text.Get("steamflow_api_remove_key"),
                    SubTitle = text.Format("steamflow_api_remove_key_subtitle", Label(key)),
                    IcoPath = Icons.Trash,
                    Score = 19998,
                    Action = _ =>
                    {
                        RemoveKey(key);
                        return true;
                    },
                },
                .. others,
            ];
        }

        // The save item only appears once a key is on the clipboard, so before that the first item is the key page.
        var copied = ApiKeyStore.Normalize(await ClipboardText.ReadAsync());
        var notConfigured = Message("steamflow_api_status_not_configured", text.Get("steamflow_api_status_not_configured_subtitle"));
        if (copied is null)
        {
            return
            [
                Item("steamflow_api_open_key_page", "steamflow_api_open_key_page_subtitle", Icons.Browser, 20000, steam.OpenApiKeyPage),
                Scored(notConfigured, 19999),
                .. others,
            ];
        }

        return
        [
            new Result
            {
                Title = text.Get("steamflow_api_save_key"),
                SubTitle = text.Format("steamflow_api_save_key_subtitle", copied[^4..]),
                IcoPath = Icons.Clipboard,
                Score = 20000,
                AsyncAction = async _ =>
                {
                    await SaveKeyFromClipboardAsync();
                    return true;
                },
            },
            Item("steamflow_api_open_key_page", "steamflow_api_open_key_page_subtitle", Icons.Browser, 19999, steam.OpenApiKeyPage),
            Scored(notConfigured, 19998),
            .. others,
        ];
    }

    private async Task<Result> StatusAsync(StoredApiKey key)
    {
        var view = await ownedGames.CurrentAsync();
        return view.LastSync is { } lastSync
            ? Message("steamflow_api_status_connected", text.Format("steamflow_api_status_last_sync", Label(key), RelativeTime(lastSync)))
            : Message("steamflow_api_status_connected", text.Format("steamflow_api_status_first_sync", Label(key)));
    }

    private Result RemoveOtherKey(StoredApiKey key) => new()
    {
        Title = text.Format("steamflow_api_remove_other_key", Label(key)),
        SubTitle = text.Get("steamflow_api_remove_other_key_subtitle"),
        IcoPath = Icons.Trash,
        Score = 19990,
        Action = _ =>
        {
            RemoveKey(key);
            return true;
        },
    };

    private string Label(StoredApiKey key) =>
        key.AccountLabel ?? key.SteamId64.ToString(CultureInfo.InvariantCulture);

    // Saving validates the key by fetching owned games, so a bad key never gets stored.
    private async Task SaveKeyFromClipboardAsync()
    {
        var notSaved = text.Get("steamflow_api_key_not_saved");
        if (ApiKeyStore.Normalize(await ClipboardText.ReadAsync()) is not { } key)
        {
            Notify(notSaved, text.Get("steamflow_api_clipboard_invalid"));
            return;
        }

        var snapshot = await library.GetAsync();
        if (snapshot.ActiveAccountId is not { } activeId)
        {
            Notify(notSaved, text.Get("steamflow_api_no_active_account"));
            return;
        }

        var account = snapshot.ActiveAccount ?? new SteamAccount(SteamAccount.ToSteamId64(activeId), "", "", false, 0);
        OwnedGames games;
        try
        {
            games = await ownedGames.FetchAsync(key, account.SteamId64);
        }
        catch (Exception ex) when (ex is HttpRequestException or OperationCanceledException or JsonException)
        {
            log.Warn("API key validation failed", ex);
            Notify(notSaved, text.Format("steamflow_api_validation_failed", ex.Message));
            return;
        }

        keys.Save(key, account);
        ownedGames.Store(account.SteamId64, games);
        Notify(text.Get("steamflow_api_key_saved"), text.Format("steamflow_api_key_saved_subtitle", account.DisplayName ?? account.SteamId64.ToString()));
    }

    private void RemoveKey(StoredApiKey key)
    {
        keys.Remove(key.SteamId64);
        ownedGames.Clear(key.SteamId64);
        Notify(text.Get("steamflow_api_key_removed"), text.Format("steamflow_api_key_removed_subtitle", Label(key)));
    }

    private string RelativeTime(DateTimeOffset moment)
    {
        var minutes = (int)Math.Max(0, (time.GetUtcNow() - moment).TotalMinutes);
        return minutes < 60 ? text.Format("steamflow_minutes_ago", minutes)
            : minutes < 24 * 60 ? text.Format("steamflow_hours_ago", minutes / 60)
            : text.Format("steamflow_days_short_ago", minutes / (24 * 60));
    }

    private static Result Scored(Result result, int score)
    {
        result.Score = score;
        return result;
    }

    private void Notify(string title, string subtitle) => api.ShowMsg(title, subtitle, Path.Combine(pluginDirectory, Icons.Owned));

    private Result Message(string titleKey, string subtitle) => new()
    {
        Title = text.Get(titleKey),
        SubTitle = subtitle,
        IcoPath = Icons.Owned,
    };

    private Result Item(string titleKey, string subtitleKey, string icon, int score, Action action) => new()
    {
        Title = text.Get(titleKey),
        SubTitle = text.Get(subtitleKey),
        IcoPath = icon,
        Score = score,
        Action = _ =>
        {
            action();
            return true;
        },
    };
}
