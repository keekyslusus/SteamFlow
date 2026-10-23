using System.Globalization;
using System.Net;
using SteamFlow.Diagnostics;

namespace SteamFlow.Steam;

// The CDN in front of the store answers a client that asks too often with 429 and then blocks its IP from the
// whole store with 403 for a while. Every request sent meanwhile only prolongs the block, so after either answer
// all store requests fail right away, without reaching Steam, until the pause is over.
public sealed class StorePause(PluginLog log, TimeProvider time) : DelegatingHandler
{
    private const string StoreHost = "store.steampowered.com";

    private static readonly TimeSpan DefaultPause = TimeSpan.FromMinutes(5);

    private long pausedUntilTicks;

    protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
    {
        if (!string.Equals(request.RequestUri?.Host, StoreHost, StringComparison.OrdinalIgnoreCase))
        {
            return await base.SendAsync(request, cancellationToken);
        }

        var now = time.GetUtcNow();
        if (now.UtcTicks < Interlocked.Read(ref pausedUntilTicks))
        {
            throw new HttpRequestException("Steam store requests are paused after a rate limit", null, HttpStatusCode.TooManyRequests);
        }

        var response = await base.SendAsync(request, cancellationToken);
        if (response.StatusCode is HttpStatusCode.TooManyRequests or HttpStatusCode.Forbidden)
        {
            var pause = RetryAfter(response, now) ?? DefaultPause;
            Interlocked.Exchange(ref pausedUntilTicks, (now + pause).UtcTicks);
            log.Warn(
                "Steam store requests paused",
                new HttpRequestException($"HTTP {(int)response.StatusCode}", null, response.StatusCode),
                $"{pause.TotalSeconds.ToString("0", CultureInfo.InvariantCulture)} s");
        }

        return response;
    }

    private static TimeSpan? RetryAfter(HttpResponseMessage response, DateTimeOffset now) =>
        response.Headers.RetryAfter switch
        {
            { Delta: { } delta } when delta > TimeSpan.Zero => delta,
            { Date: { } date } when date > now => date - now,
            _ => null,
        };
}
