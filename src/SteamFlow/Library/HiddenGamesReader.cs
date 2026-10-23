using System.Text.Json;
using SteamFlow.Diagnostics;
using SteamFlow.Steam;

namespace SteamFlow.Library;

public sealed class HiddenGamesReader(PluginLog log)
{
    public const string CloudStorageFolder = "cloudstorage";
    public const string CloudStorageFile = "cloud-storage-namespace-1.json";

    public IReadOnlySet<int> Read(string configFolder)
    {
        var path = Path.Combine(configFolder, CloudStorageFolder, CloudStorageFile);
        if (!File.Exists(path))
        {
            return new HashSet<int>();
        }

        try
        {
            using var stream = Vdf.OpenShared(path);
            using var reader = new StreamReader(stream);
            return Parse(reader.ReadToEnd());
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or JsonException)
        {
            log.Warn("Hidden collection unreadable", ex);
            return new HashSet<int>();
        }
    }

    // The file is a list of [key, entry] pairs; the hidden collection's value is itself a JSON string.
    public static IReadOnlySet<int> Parse(string cloudStorageJson)
    {
        using var document = JsonDocument.Parse(cloudStorageJson);
        if (document.RootElement.ValueKind != JsonValueKind.Array)
        {
            return new HashSet<int>();
        }

        foreach (var entry in document.RootElement.EnumerateArray())
        {
            if (entry.ValueKind != JsonValueKind.Array
                || entry.GetArrayLength() < 2
                || entry[0].ValueKind != JsonValueKind.String
                || entry[0].GetString() != "user-collections.hidden")
            {
                continue;
            }

            if (entry[1].ValueKind != JsonValueKind.Object
                || !entry[1].TryGetProperty("value", out var value)
                || value.ValueKind != JsonValueKind.String
                || string.IsNullOrEmpty(value.GetString()))
            {
                return new HashSet<int>();
            }

            using var collection = JsonDocument.Parse(value.GetString()!);
            var removed = AppIds(collection.RootElement, "removed").ToHashSet();
            return AppIds(collection.RootElement, "added").Where(appId => !removed.Contains(appId)).ToHashSet();
        }

        return new HashSet<int>();
    }

    private static IEnumerable<int> AppIds(JsonElement collection, string property)
    {
        if (!collection.TryGetProperty(property, out var list) || list.ValueKind != JsonValueKind.Array)
        {
            yield break;
        }

        foreach (var item in list.EnumerateArray())
        {
            if (item.ValueKind == JsonValueKind.Number && item.TryGetInt32(out var appId))
            {
                yield return appId;
            }
        }
    }
}
