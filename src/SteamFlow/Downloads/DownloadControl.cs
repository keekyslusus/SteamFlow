using System.Globalization;
using System.Text.Json;
using Flow.Launcher.Plugin;
using SteamFlow.Diagnostics;
using SteamFlow.Library;
using SteamFlow.Localization;
using SteamFlow.Session;
using SteamFlow.Steam;
using SteamFlow.Store;
using SteamFlow.WebApi;

namespace SteamFlow.Downloads;

public sealed class DownloadControl(
    ClientCommApi api,
    SteamSessionTokens tokens,
    LocalLibrary library,
    DownloadStatuses statuses,
    IPublicAPI flow,
    Translator text,
    PluginLog log,
    string pluginDirectory)
{
    private static readonly TimeSpan ConfirmTimeout = TimeSpan.FromSeconds(8);
    private static readonly TimeSpan ConfirmPoll = TimeSpan.FromMilliseconds(500);

    public async Task ChangeAsync(int appId, string name, bool pause)
    {
        var snapshot = await library.GetAsync();
        if (snapshot.ActiveAccountId is not { } accountId)
        {
            Notify(text.Get("steamflow_download_no_client"));
            return;
        }

        try
        {
            var call = await tokens.CallAsync(
                SteamAccount.ToSteamId64(accountId),
                token => SendAsync(token, appId, pause),
                response => response.Unauthorized,
                () => { });
            if (call is null)
            {
                Notify(text.Get("steamflow_session_no_token"));
                return;
            }

            var response = call.Result;
            if (response.StatusCode == 0)
            {
                Notify(text.Get("steamflow_download_no_client"));
                return;
            }

            if (!response.Succeeded)
            {
                Notify(text.Format("steamflow_download_rejected", name, response.EResult?.ToString(CultureInfo.InvariantCulture) ?? $"HTTP {response.StatusCode}"));
                return;
            }

            Notify(await ConfirmedAsync(appId, pause)
                ? text.Format(pause ? "steamflow_download_paused" : "steamflow_download_resumed", name)
                : text.Format("steamflow_download_unconfirmed", name));
        }
        catch (Exception ex) when (ex is HttpRequestException or OperationCanceledException or JsonException)
        {
            log.Warn("Download pause or resume failed", ex, $"app {appId}");
            Notify(text.Format("steamflow_download_failed", name, ex.Message));
        }
    }

    // A status code of 0 means Steam reported no signed-in client to send the request to.
    private async Task<ServiceResponse> SendAsync(string accessToken, int appId, bool pause)
    {
        using var timeout = new CancellationTokenSource(StoreRequests.Timeout);
        var (logon, instance) = await api.ClientInstanceAsync(accessToken, timeout.Token);
        if (logon.StatusCode != 200)
        {
            return logon;
        }

        return instance is null
            ? new ServiceResponse(0, null)
            : await api.SetUpdateStateAsync(accessToken, instance, appId, pause, timeout.Token);
    }

    // Steam's answer only says the request was forwarded; the client's own log shows whether it acted on it.
    private async Task<bool> ConfirmedAsync(int appId, bool pause)
    {
        var deadline = DateTime.UtcNow + ConfirmTimeout;
        while (DateTime.UtcNow < deadline)
        {
            await Task.Delay(ConfirmPoll);
            var status = statuses.Snapshot().Logged.GetValueOrDefault(appId)?.Status;
            if (pause ? status == DownloadStatus.Paused : status is DownloadStatus.Updating or DownloadStatus.Queued)
            {
                return true;
            }
        }

        return false;
    }

    private void Notify(string message) =>
        flow.ShowMsg(text.Get("steamflow_download_title"), message, Path.Combine(pluginDirectory, Icons.Download));
}
