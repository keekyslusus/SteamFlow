using System.Text.Json;
using Flow.Launcher.Plugin;
using SteamFlow.Caching;
using SteamFlow.Diagnostics;
using SteamFlow.Localization;
using SteamFlow.Session;
using SteamFlow.Store;
using SteamFlow.WebApi;

namespace SteamFlow.Wishlist;

public sealed record WishlistView(ApiUnavailable Unavailable, IReadOnlyList<WishlistItem> Items)
{
    public bool Contains(int appId) => Items.Any(item => item.AppId == appId);
}

public enum WishlistMenuState
{
    Unavailable,
    CanAdd,
    CanRemove,
}

public sealed class WishlistService
{
    private static readonly TimeSpan VerifyDelay = TimeSpan.FromSeconds(1);
    private const int VerifyAttempts = 3;

    private readonly ApiAccess access;
    private readonly SteamWebApi api;
    private readonly SteamSessionTokens tokens;
    private readonly StoreRequests requests;
    private readonly PluginLog log;
    private readonly IPublicAPI flow;
    private readonly Translator text;
    private readonly string iconPath;
    private readonly TimedCache<ulong, IReadOnlyList<WishlistItem>> lists;
    private readonly Lock gate = new();
    private BoundKey? lastBound;

    public WishlistService(
        ApiAccess access,
        SteamWebApi api,
        SteamSessionTokens tokens,
        StoreRequests requests,
        PluginLog log,
        IPublicAPI flow,
        Translator text,
        string pluginDirectory,
        TimeProvider time)
    {
        this.access = access;
        this.api = api;
        this.tokens = tokens;
        this.requests = requests;
        this.log = log;
        this.flow = flow;
        this.text = text;
        iconPath = Path.Combine(pluginDirectory, Icons.Wishlist);
        lists = new(time, TimeSpan.FromMinutes(15), TimeSpan.FromMinutes(1));
    }

    public async Task<WishlistView> CurrentAsync()
    {
        var state = await access.StateAsync();
        lock (gate)
        {
            lastBound = state.Bound;
        }

        if (state.Bound is not { } bound)
        {
            return new WishlistView(state.Reason, []);
        }

        var items = await lists.GetAsync(bound.SteamId64, () => FetchAsync(bound));
        return new WishlistView(ApiUnavailable.None, items ?? []);
    }

    public void WarmUp() => _ = CurrentAsync();

    // Context menus are built synchronously, so they read what was learned before instead of waiting;
    // each call also refreshes that knowledge for the next menu.
    public (WishlistMenuState State, bool NeedsSteamStart) MenuState(int appId)
    {
        WarmUp();

        BoundKey? bound;
        lock (gate)
        {
            bound = lastBound;
        }

        if (bound is null)
        {
            return (WishlistMenuState.Unavailable, false);
        }

        var wishlisted = lists.Peek(bound.SteamId64)?.Any(item => item.AppId == appId) == true;
        return (wishlisted ? WishlistMenuState.CanRemove : WishlistMenuState.CanAdd, tokens.NeedsSteamStart(bound.SteamId64));
    }

    // Success is only reported once a fresh read of the wishlist shows the change; Steam can accept a request
    // and still leave the wishlist untouched.
    public async Task MutateAsync(int appId, string name, bool add)
    {
        if (await access.CurrentAsync() is not { } bound)
        {
            Notify(text.Get("steamflow_wishlist_unavailable"));
            return;
        }

        try
        {
            var mutation = await SendAsync(bound, appId, add);
            if (mutation is null)
            {
                Notify(text.Get("steamflow_session_no_token"));
                return;
            }

            if (!mutation.Succeeded)
            {
                Notify(text.Format("steamflow_wishlist_rejected", name, mutation.EResult?.ToString() ?? $"HTTP {mutation.StatusCode}"));
                return;
            }

            if (await VerifyAsync(bound, appId, add))
            {
                Notify(text.Format(add ? "steamflow_wishlist_added" : "steamflow_wishlist_removed", name));
            }
            else
            {
                Notify(text.Format("steamflow_wishlist_unchanged", name));
            }
        }
        catch (Exception ex) when (ex is HttpRequestException or OperationCanceledException or JsonException)
        {
            log.Warn("Wishlist change failed", ex, $"app {appId}");
            Notify(text.Format("steamflow_wishlist_failed", name, ex.Message));
        }
    }

    private async Task<ServiceResponse?> SendAsync(BoundKey bound, int appId, bool add)
    {
        var call = await tokens.CallAsync(
            bound.SteamId64,
            async token =>
            {
                using var timeout = new CancellationTokenSource(StoreRequests.Timeout);
                return await api.MutateWishlistAsync(token, appId, add, timeout.Token);
            },
            mutation => mutation.Unauthorized,
            () => Notify(text.Get("steamflow_session_starting_steam")));
        return call?.Result;
    }

    private async Task<bool> VerifyAsync(BoundKey bound, int appId, bool add)
    {
        for (var attempt = 0; attempt < VerifyAttempts; attempt++)
        {
            if (attempt > 0)
            {
                await Task.Delay(VerifyDelay);
            }

            var items = await FetchAsync(bound);
            if (items is not null && items.Any(item => item.AppId == appId) == add)
            {
                lists.Set(bound.SteamId64, items);
                return true;
            }
        }

        return false;
    }

    private Task<IReadOnlyList<WishlistItem>?> FetchAsync(BoundKey bound) =>
        requests.Quietly("Wishlist request", token => api.WishlistAsync(bound.Key, bound.SteamId64, token));

    private void Notify(string message) => flow.ShowMsg(text.Get("steamflow_wishlist_title"), message, iconPath);
}
