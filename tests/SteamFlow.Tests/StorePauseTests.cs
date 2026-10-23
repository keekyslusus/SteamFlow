using System.Net;
using System.Net.Http.Headers;
using SteamFlow.Steam;

namespace SteamFlow.Tests;

public class StorePauseTests
{
    private const string Store = "https://store.steampowered.com/api/appdetails?appids=570";
    private const string WebApi = "https://api.steampowered.com/ISteamUserStats/GetNumberOfCurrentPlayers/v1/?appid=570";

    [Theory]
    [InlineData(HttpStatusCode.TooManyRequests)]
    [InlineData(HttpStatusCode.Forbidden)]
    public async Task RateLimit_StopsStoreRequestsWithoutReachingSteam(HttpStatusCode status)
    {
        var steam = new Steam(status);
        var http = Client(steam, new ManualTime());

        Assert.Equal(status, (await http.GetAsync(Store)).StatusCode);
        steam.Status = HttpStatusCode.OK;
        var paused = await Assert.ThrowsAsync<HttpRequestException>(() => http.GetAsync(Store));

        Assert.Equal(HttpStatusCode.TooManyRequests, paused.StatusCode);
        Assert.Equal(1, steam.Requests);
    }

    [Fact]
    public async Task Pause_EndsAfterDefaultWindow()
    {
        var steam = new Steam(HttpStatusCode.Forbidden);
        var time = new ManualTime();
        var http = Client(steam, time);

        await http.GetAsync(Store);
        steam.Status = HttpStatusCode.OK;
        time.Advance(TimeSpan.FromMinutes(4));
        await Assert.ThrowsAsync<HttpRequestException>(() => http.GetAsync(Store));
        time.Advance(TimeSpan.FromMinutes(1));

        Assert.Equal(HttpStatusCode.OK, (await http.GetAsync(Store)).StatusCode);
    }

    [Fact]
    public async Task Pause_FollowsRetryAfter()
    {
        var steam = new Steam(HttpStatusCode.TooManyRequests) { RetryAfter = TimeSpan.FromSeconds(30) };
        var time = new ManualTime();
        var http = Client(steam, time);

        await http.GetAsync(Store);
        steam.Status = HttpStatusCode.OK;
        time.Advance(TimeSpan.FromSeconds(31));

        Assert.Equal(HttpStatusCode.OK, (await http.GetAsync(Store)).StatusCode);
    }

    [Fact]
    public async Task OtherHosts_AreNotPaused()
    {
        var steam = new Steam(HttpStatusCode.TooManyRequests);
        var http = Client(steam, new ManualTime());

        await http.GetAsync(Store);
        steam.Status = HttpStatusCode.OK;

        Assert.Equal(HttpStatusCode.OK, (await http.GetAsync(WebApi)).StatusCode);
        Assert.Equal(2, steam.Requests);
    }

    private static HttpClient Client(Steam steam, TimeProvider time) =>
        new(new StorePause(TestLog.Discard(), time) { InnerHandler = steam });

    private sealed class Steam(HttpStatusCode status) : HttpMessageHandler
    {
        public HttpStatusCode Status { get; set; } = status;

        public TimeSpan? RetryAfter { get; init; }

        public int Requests { get; private set; }

        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            Requests++;
            var response = new HttpResponseMessage(Status);
            if (RetryAfter is { } delay)
            {
                response.Headers.RetryAfter = new RetryConditionHeaderValue(delay);
            }

            return Task.FromResult(response);
        }
    }

    private sealed class ManualTime : TimeProvider
    {
        private DateTimeOffset now = new(2026, 10, 23, 12, 0, 0, TimeSpan.Zero);

        public override DateTimeOffset GetUtcNow() => now;

        public void Advance(TimeSpan by) => now += by;
    }
}
