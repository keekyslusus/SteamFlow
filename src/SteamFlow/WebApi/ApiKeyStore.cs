using System.Globalization;
using System.Security.Cryptography;
using System.Text.Json.Nodes;
using System.Text.Json;
using System.Text.RegularExpressions;
using System.Text;
using SteamFlow.Diagnostics;
using SteamFlow.Steam;

namespace SteamFlow.WebApi;

public sealed record StoredApiKey(string Key, ulong SteamId64, string? PersonaName, string? AccountName)
{
    public string? AccountLabel => !string.IsNullOrEmpty(PersonaName) ? PersonaName : AccountName;
}

// Keeps one Web API key per Steam account, so switching accounts does not require saving the key again.
public sealed partial class ApiKeyStore(string folder, string legacyFolder, PluginLog log)
{
    private const string KeysFile = "owned_api_keys.bin";

    // The single-key layout of the Python plugin and of earlier builds of this one.
    private const string SingleKeyFile = "owned_api_key.bin";
    private const string SingleMetadataFile = "owned_api_key.meta.json";

    // Same entropy as the Python plugin, so its key file still decrypts.
    private static readonly byte[] Entropy = "SteamFlow-OwnedGames-Key-v1"u8.ToArray();

    private readonly Lock gate = new();
    private Dictionary<ulong, StoredApiKey>? cached;

    public static string? Normalize(string? text) =>
        text?.Trim() is { } trimmed && KeyPattern().IsMatch(trimmed) ? trimmed.ToUpperInvariant() : null;

    // Brings over a single saved key: from an earlier build of this plugin, else copied from the Python plugin,
    // which keeps its own file until it is uninstalled.
    public void ImportLegacy()
    {
        if (File.Exists(Path.Combine(folder, KeysFile)))
        {
            return;
        }

        var key = ReadSingle(folder) ?? ReadSingle(legacyFolder);
        if (key is not null)
        {
            lock (gate)
            {
                var keys = Loaded();
                keys[key.SteamId64] = key;
                Write(keys);
            }
        }

        DeleteSingle();
    }

    public StoredApiKey? For(ulong steamId64)
    {
        lock (gate)
        {
            return Loaded().GetValueOrDefault(steamId64);
        }
    }

    public IReadOnlyList<StoredApiKey> All()
    {
        lock (gate)
        {
            return [.. Loaded().Values];
        }
    }

    public StoredApiKey Save(string key, SteamAccount account)
    {
        var stored = new StoredApiKey(key, account.SteamId64, account.PersonaName, account.AccountName);
        lock (gate)
        {
            var keys = Loaded();
            keys[account.SteamId64] = stored;
            Write(keys);
        }

        return stored;
    }

    public void Remove(ulong steamId64)
    {
        lock (gate)
        {
            var keys = Loaded();
            if (keys.Remove(steamId64))
            {
                Write(keys);
            }
        }
    }

    private Dictionary<ulong, StoredApiKey> Loaded() => cached ??= Read();

    private Dictionary<ulong, StoredApiKey> Read()
    {
        var keys = new Dictionary<ulong, StoredApiKey>();
        try
        {
            var path = Path.Combine(folder, KeysFile);
            if (!File.Exists(path))
            {
                return keys;
            }

            var json = Encoding.UTF8.GetString(
                ProtectedData.Unprotect(File.ReadAllBytes(path), Entropy, DataProtectionScope.CurrentUser));
            if (JsonNode.Parse(json)?["accounts"] is not JsonArray accounts)
            {
                return keys;
            }

            foreach (var entry in accounts.OfType<JsonObject>())
            {
                if (Normalize(Text(entry, "key")) is { } key && SteamId(entry, "steamid64") is { } steamId64)
                {
                    keys[steamId64] = new StoredApiKey(key, steamId64, Text(entry, "persona_name"), Text(entry, "account_name"));
                }
            }
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or CryptographicException or JsonException)
        {
            log.Warn("Saved API keys unreadable", ex);
        }

        return keys;
    }

    // An empty list is still written, so removing the last key does not make the Python key come back on import.
    private void Write(Dictionary<ulong, StoredApiKey> keys)
    {
        var path = Path.Combine(folder, KeysFile);
        var accounts = new JsonArray();
        foreach (var key in keys.Values)
        {
            accounts.Add(new JsonObject
            {
                ["steamid64"] = key.SteamId64.ToString(CultureInfo.InvariantCulture),
                ["key"] = key.Key,
                ["persona_name"] = key.PersonaName,
                ["account_name"] = key.AccountName,
            });
        }

        try
        {
            Directory.CreateDirectory(folder);
            var json = new JsonObject { ["accounts"] = accounts }.ToJsonString();
            File.WriteAllBytes(
                path,
                ProtectedData.Protect(Encoding.UTF8.GetBytes(json), Entropy, DataProtectionScope.CurrentUser));
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or CryptographicException)
        {
            log.Warn("API keys not saved", ex);
        }
    }

    // A single key without a bound account cannot be assigned to anyone, so it is dropped.
    private StoredApiKey? ReadSingle(string directory)
    {
        var keyPath = Path.Combine(directory, SingleKeyFile);
        if (!File.Exists(keyPath))
        {
            return null;
        }

        try
        {
            var key = Normalize(Encoding.UTF8.GetString(
                ProtectedData.Unprotect(File.ReadAllBytes(keyPath), Entropy, DataProtectionScope.CurrentUser)));
            var metadataPath = Path.Combine(directory, SingleMetadataFile);
            var metadata = File.Exists(metadataPath) ? JsonNode.Parse(File.ReadAllText(metadataPath)) as JsonObject : null;
            return key is not null && SteamId(metadata, "bound_steamid64") is { } steamId64
                ? new StoredApiKey(key, steamId64, Text(metadata, "persona_name"), Text(metadata, "account_name"))
                : null;
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or CryptographicException or JsonException)
        {
            log.Warn("Single saved API key unreadable", ex, directory);
            return null;
        }
    }

    private void DeleteSingle()
    {
        Delete(Path.Combine(folder, SingleKeyFile));
        Delete(Path.Combine(folder, SingleMetadataFile));
    }

    private static void Delete(string path)
    {
        try
        {
            File.Delete(path);
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
        }
    }

    private static ulong? SteamId(JsonObject? json, string name) =>
        ulong.TryParse(Text(json, name), NumberStyles.None, CultureInfo.InvariantCulture, out var steamId64) ? steamId64 : null;

    // Python wrote the bound SteamID64 as a string; a number is accepted too.
    private static string? Text(JsonObject? json, string name) =>
        json?[name] is JsonValue value
            ? value.TryGetValue<string>(out var text) ? text : value.ToJsonString()
            : null;

    [GeneratedRegex("^[A-Fa-f0-9]{32}$")]
    private static partial Regex KeyPattern();
}
