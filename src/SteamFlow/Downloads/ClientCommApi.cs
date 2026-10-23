using System.Globalization;
using System.Text.Json;
using SteamFlow.WebApi;

namespace SteamFlow.Downloads;

public sealed record AppProgress(int Percent, int? SecondsLeft);

// The remote-download service the Steam mobile app uses: requests go to Steam's servers, which relay them
// to the client signed in on a PC. It is the only place live download progress can be read; the
// appmanifest is not rewritten while bytes are coming in.
public sealed class ClientCommApi(HttpClient http)
{
    private const string Url = "https://api.steampowered.com/IClientCommService";

    public async Task<(ServiceResponse Response, string? Instance)> ClientInstanceAsync(string accessToken, CancellationToken token)
    {
        using var response = await http.GetAsync($"{Url}/GetAllClientLogonInfo/v1/?access_token={accessToken}", token);
        return response.IsSuccessStatusCode
            ? (new ServiceResponse((int)response.StatusCode, EResult(response)),
                ClientInstance(await response.Content.ReadAsStringAsync(token), Environment.MachineName))
            : (new ServiceResponse((int)response.StatusCode, EResult(response)), null);
    }

    public async Task<ServiceResponse> SetUpdateStateAsync(string accessToken, string instance, int appId, bool pause, CancellationToken token)
    {
        using var request = new HttpRequestMessage(HttpMethod.Post, $"{Url}/SetClientAppUpdateState/v1/")
        {
            Content = new FormUrlEncodedContent(new Dictionary<string, string>
            {
                ["access_token"] = accessToken,
                ["appid"] = appId.ToString(CultureInfo.InvariantCulture),
                ["action"] = pause ? "0" : "1",
                ["client_instanceid"] = instance,
            }),
        };
        request.Headers.Add("Origin", "https://store.steampowered.com");
        using var response = await http.SendAsync(request, token);
        return new ServiceResponse((int)response.StatusCode, EResult(response));
    }

    // "changing" limits the answer to apps with pending or running updates instead of the whole library.
    public async Task<IReadOnlyDictionary<int, AppProgress>> ProgressAsync(string accessToken, string instance, CancellationToken token)
    {
        var input = Uri.EscapeDataString(JsonSerializer.Serialize(new { fields = "all", filters = "changing", language = "english", client_instanceid = instance }));
        return ParseProgress(await http.GetStringAsync($"{Url}/GetClientAppList/v1/?access_token={accessToken}&input_json={input}", token));
    }

    public static IReadOnlyDictionary<int, AppProgress> ParseProgress(string json)
    {
        using var document = JsonDocument.Parse(json);
        var progress = new Dictionary<int, AppProgress>();
        if (!document.RootElement.TryGetProperty("response", out var response)
            || !response.TryGetProperty("apps", out var apps)
            || apps.ValueKind != JsonValueKind.Array)
        {
            return progress;
        }

        foreach (var app in apps.EnumerateArray())
        {
            if (Number(app, "appid") is not { } appId || Number(app, "update_percentage") is not { } percent)
            {
                continue;
            }

            progress[(int)appId] = new AppProgress((int)Math.Clamp(percent, 0, 100), Number(app, "estimated_seconds_remaining") is > 0 and var seconds ? (int)seconds : null);
        }

        return progress;
    }

    // Several PCs can be signed in at once; the one named like this machine is the one whose download was shown.
    public static string? ClientInstance(string json, string machineName)
    {
        using var document = JsonDocument.Parse(json);
        if (!document.RootElement.TryGetProperty("response", out var response)
            || !response.TryGetProperty("sessions", out var sessions)
            || sessions.ValueKind != JsonValueKind.Array)
        {
            return null;
        }

        var all = sessions.EnumerateArray()
            .Select(session => (
                Id: session.TryGetProperty("client_instanceid", out var id) ? id.ToString() : "",
                Machine: session.TryGetProperty("machine_name", out var machine) && machine.ValueKind == JsonValueKind.String ? machine.GetString() : null))
            .Where(session => session.Id.Length > 0)
            .ToList();
        return all.FirstOrDefault(session => string.Equals(session.Machine, machineName, StringComparison.OrdinalIgnoreCase)).Id
            ?? all.FirstOrDefault().Id;
    }

    // 64-bit counters arrive as strings and small values as numbers.
    private static long? Number(JsonElement element, string name)
    {
        if (!element.TryGetProperty(name, out var value))
        {
            return null;
        }

        return value.ValueKind switch
        {
            JsonValueKind.Number when value.TryGetInt64(out var number) => number,
            JsonValueKind.String when long.TryParse(value.GetString(), NumberStyles.Integer, CultureInfo.InvariantCulture, out var number) => number,
            _ => null,
        };
    }

    private static int? EResult(HttpResponseMessage response) =>
        response.Headers.TryGetValues("x-eresult", out var values)
        && int.TryParse(values.FirstOrDefault(), NumberStyles.Integer, CultureInfo.InvariantCulture, out var code)
            ? code
            : null;
}
