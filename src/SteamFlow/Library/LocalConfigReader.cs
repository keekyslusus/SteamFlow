using System.Globalization;
using System.Text.Json;
using SteamFlow.Diagnostics;
using SteamFlow.Steam;

namespace SteamFlow.Library;

public sealed record PlayActivity(int? PlaytimeMinutes, DateTimeOffset? LastPlayed);

public sealed record LocalConfig(IReadOnlyDictionary<int, PlayActivity> Activity, int? PersonaState)
{
    public static readonly LocalConfig Empty = new(new Dictionary<int, PlayActivity>(), null);
}

// localconfig.vdf can be several megabytes, so everything the plugin needs from it is read in one pass.
public sealed class LocalConfigReader(PluginLog log)
{
    public LocalConfig Read(string configFolder, uint? accountId)
    {
        var path = Path.Combine(configFolder, "localconfig.vdf");
        if (!File.Exists(path))
        {
            return LocalConfig.Empty;
        }

        try
        {
            using var stream = Vdf.OpenShared(path);
            return Parse(stream, accountId);
        }
        catch (Exception ex) when (Vdf.IsReadError(ex))
        {
            log.Warn("localconfig.vdf unreadable", ex);
            return LocalConfig.Empty;
        }
    }

    public static LocalConfig Parse(Stream localConfig, uint? accountId)
    {
        var root = Vdf.ReadText(localConfig);
        var activity = new Dictionary<int, PlayActivity>();
        foreach (var app in root.Child("Software").Child("Valve").Child("Steam").Child("apps")?.Items() ?? [])
        {
            if (!int.TryParse(app.Name, NumberStyles.None, CultureInfo.InvariantCulture, out var appId))
            {
                continue;
            }

            var playtime = app.Number("Playtime");
            var lastPlayed = app.Number("LastPlayed");
            if (playtime is null && lastPlayed is null)
            {
                continue;
            }

            activity[appId] = new PlayActivity(
                playtime is { } minutes ? (int)minutes : null,
                lastPlayed is > 0 and { } seconds ? DateTimeOffset.FromUnixTimeSeconds(seconds) : null);
        }

        return new LocalConfig(activity, accountId is { } id ? PersonaState(root.Child("WebStorage"), id) : null);
    }

    // The friends client keeps its own preferences as a JSON string inside the KeyValues file.
    private static int? PersonaState(ValveKeyValue.KVObject? webStorage, uint accountId)
    {
        var prefs = webStorage?.Text(string.Create(CultureInfo.InvariantCulture, $"FriendStoreLocalPrefs_{accountId}"));
        if (string.IsNullOrEmpty(prefs))
        {
            return null;
        }

        try
        {
            using var document = JsonDocument.Parse(prefs);
            return document.RootElement.ValueKind == JsonValueKind.Object
                && document.RootElement.TryGetProperty("ePersonaState", out var state)
                && state.TryGetInt32(out var value)
                    ? value
                    : null;
        }
        catch (JsonException)
        {
            return null;
        }
    }
}
