using System.Text.Json;
using Flow.Launcher.Plugin;
using SteamFlow.Diagnostics;
using SteamFlow.Library;
using SteamFlow.Localization;
using SteamFlow.Session;
using SteamFlow.Steam;
using SteamFlow.Store;
using SteamFlow.WebApi;

namespace SteamFlow.Cart;

public sealed class CartService(
    CartApi api,
    SteamSessionTokens tokens,
    LocalLibrary library,
    StoreCatalog catalog,
    SteamClient steam,
    IPublicAPI flow,
    Translator text,
    PluginLog log,
    string pluginDirectory)
{
    private static readonly TimeSpan VerifyDelay = TimeSpan.FromSeconds(1);
    private const int VerifyAttempts = 3;

    // Unlike the wishlist, the cart needs no Web API key: only the signed-in account's session token.
    public (bool Available, bool NeedsSteamStart) MenuState()
    {
        var snapshot = library.GetAsync();
        return snapshot.IsCompletedSuccessfully && snapshot.Result.ActiveAccountId is { } accountId
            ? (true, tokens.NeedsSteamStart(SteamAccount.ToSteamId64(accountId)))
            : (false, false);
    }

    // Like the wishlist, success is only reported once Steam's own cart shows the package.
    public async Task AddAsync(int appId, string name)
    {
        var snapshot = await library.GetAsync();
        if (snapshot.ActiveAccountId is not { } accountId)
        {
            Notify(text.Get("steamflow_cart_no_account"));
            return;
        }

        var steamId64 = SteamAccount.ToSteamId64(accountId);
        try
        {
            var country = await catalog.CountryCodeAsync();
            int? package;
            using (var timeout = new CancellationTokenSource(StoreRequests.Timeout))
            {
                package = await api.PackageForAppAsync(appId, country, timeout.Token);
            }

            if (package is not { } packageId)
            {
                Notify(text.Format("steamflow_cart_no_package", name));
                return;
            }

            var call = await tokens.CallAsync(
                steamId64,
                async token =>
                {
                    using var timeout = new CancellationTokenSource(StoreRequests.Timeout);
                    return (Token: token, Response: await api.AddAsync(token, country, packageId, timeout.Token));
                },
                result => result.Response.Unauthorized,
                () => Notify(text.Get("steamflow_session_starting_steam")));
            if (call is null)
            {
                Notify(text.Get("steamflow_session_no_token"));
                return;
            }

            var (accessToken, response) = call.Result;
            if (!response.Succeeded)
            {
                Notify(text.Format("steamflow_cart_rejected", name, response.EResult?.ToString() ?? $"HTTP {response.StatusCode}"));
                return;
            }

            if (await VerifyAsync(accessToken, country, packageId))
            {
                Notify(text.Format("steamflow_cart_added", name));
                steam.OpenCart();
            }
            else
            {
                Notify(text.Format("steamflow_cart_unchanged", name));
            }
        }
        catch (Exception ex) when (ex is HttpRequestException or OperationCanceledException or JsonException)
        {
            log.Warn("Add to cart failed", ex, $"app {appId}");
            Notify(text.Format("steamflow_cart_failed", name, ex.Message));
        }
    }

    private async Task<bool> VerifyAsync(string accessToken, string country, int packageId)
    {
        for (var attempt = 0; attempt < VerifyAttempts; attempt++)
        {
            if (attempt > 0)
            {
                await Task.Delay(VerifyDelay);
            }

            using var timeout = new CancellationTokenSource(StoreRequests.Timeout);
            if ((await api.PackagesInCartAsync(accessToken, country, timeout.Token))?.Contains(packageId) == true)
            {
                return true;
            }
        }

        return false;
    }

    private void Notify(string message) =>
        flow.ShowMsg(text.Get("steamflow_cart_title"), message, Path.Combine(pluginDirectory, Icons.Buy));
}
