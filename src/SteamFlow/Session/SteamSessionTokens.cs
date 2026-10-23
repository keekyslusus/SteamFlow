using System.Diagnostics;
using System.Globalization;
using System.Security.Cryptography;
using System.Text.Json.Nodes;
using System.Text.Json;
using System.Text.RegularExpressions;
using System.Text;
using SteamFlow.Diagnostics;
using SteamFlow.Steam;

namespace SteamFlow.Session;

public sealed record SessionToken(string Value, ulong SteamId64, DateTimeOffset ExpiresAt, DateTimeOffset IssuedAt);

public sealed record SessionCall<T>(T Result);

// Account changes (wishlist, cart) need the signed-in user's access token. Without a password the only source
// is the Steam client's own browser cache, where store pages embed a "webapi_token" that lives for a day.
public sealed partial class SteamSessionTokens(string folder, string legacyFolder, SteamClient steam, PluginLog log, TimeProvider time)
{
    private const string TokenFolder = "download_control_tokens";
    private const int ChunkSize = 1024 * 1024;
    private const int ChunkOverlap = 8192;

    // Same entropy and layout as the Python plugin, so a token it saved can be reused after the switch.
    private static readonly byte[] Entropy = "SteamFlow-DownloadControl-v1"u8.ToArray();
    private static readonly TimeSpan MinimumLifetimeLeft = TimeSpan.FromMinutes(5);
    private static readonly TimeSpan PollInterval = TimeSpan.FromSeconds(1);
    private static readonly TimeSpan RunningSteamWait = TimeSpan.FromSeconds(10);
    private static readonly TimeSpan StartingSteamWait = TimeSpan.FromSeconds(45);

    private readonly Lock gate = new();

    // The browser cache keeps a token Steam rejected until it expires, so without this the retry would pick it again.
    private readonly HashSet<string> rejected = [];

    private string TokenDirectory => Path.Combine(folder, TokenFolder);

    public static bool SteamIsRunning()
    {
        var processes = Process.GetProcessesByName("steam");
        foreach (var process in processes)
        {
            process.Dispose();
        }

        return processes.Length > 0;
    }

    public void ImportLegacy()
    {
        var legacyDirectory = Path.Combine(legacyFolder, TokenFolder);
        if (!Directory.Exists(legacyDirectory))
        {
            return;
        }

        try
        {
            Directory.CreateDirectory(TokenDirectory);
            foreach (var file in Directory.EnumerateFiles(legacyDirectory))
            {
                var target = Path.Combine(TokenDirectory, Path.GetFileName(file));
                if (!File.Exists(target))
                {
                    File.Copy(file, target);
                }
            }
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
        }
    }

    public bool HasSavedToken(ulong steamId64) => LoadSaved(steamId64) is not null;

    // Asking Steam for a fresh token opens its account page, which starts the client when it is closed.
    public bool NeedsSteamStart(ulong steamId64) => !HasSavedToken(steamId64) && !SteamIsRunning();

    public async Task<SessionToken?> GetAsync(ulong steamId64, Action onSteamStarting, CancellationToken token)
    {
        if (LoadSaved(steamId64) is { } saved)
        {
            return saved;
        }

        if (await Task.Run(() => FromBrowserCache(steamId64), token) is { } cached)
        {
            Save(cached);
            return cached;
        }

        var wasRunning = SteamIsRunning();
        if (!wasRunning)
        {
            onSteamStarting();
        }

        var started = time.GetUtcNow();
        steam.OpenAccountPreferences();
        try
        {
            var deadline = started + (wasRunning ? RunningSteamWait : StartingSteamWait);
            while (time.GetUtcNow() < deadline)
            {
                await Task.Delay(PollInterval, token);
                // Nothing usable was cached before the page opened, so any usable token now is the new one.
                if (await Task.Run(() => FromBrowserCache(steamId64), token) is { } fresh)
                {
                    Save(fresh);
                    return fresh;
                }
            }

            return null;
        }
        finally
        {
            steam.OpenLibrary();
        }
    }

    // For background reads (favorites, join details) that must never open or start Steam.
    public async Task<SessionToken?> GetWithoutSteamAsync(ulong steamId64)
    {
        if (LoadSaved(steamId64) is { } saved)
        {
            return saved;
        }

        var cached = await Task.Run(() => FromBrowserCache(steamId64));
        if (cached is not null)
        {
            Save(cached);
        }

        return cached;
    }

    // Runs an account request with the best available token; a token Steam rejects is dropped and the call
    // is retried once with a newer one. Returns null when no token could be found at all.
    public async Task<SessionCall<T>?> CallAsync<T>(
        ulong steamId64,
        Func<string, Task<T>> call,
        Func<T, bool> rejected,
        Action onSteamStarting)
    {
        T? result = default;
        for (var attempt = 0; attempt < 2; attempt++)
        {
            if (await GetAsync(steamId64, onSteamStarting, CancellationToken.None) is not { } token)
            {
                return null;
            }

            result = await call(token.Value);
            if (!rejected(result))
            {
                break;
            }

            Reject(token);
        }

        return new SessionCall<T>(result!);
    }

    public void Reject(SessionToken token)
    {
        lock (gate)
        {
            rejected.Add(token.Value);
        }

        Forget(token.SteamId64);
    }

    public void Forget(ulong steamId64)
    {
        var (tokenPath, metadataPath) = Paths(steamId64);
        foreach (var path in new[] { tokenPath, metadataPath })
        {
            try
            {
                File.Delete(path);
            }
            catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
            {
            }
        }
    }

    public static SessionToken? Decode(string value)
    {
        var parts = value.Split('.');
        if (parts.Length < 2)
        {
            return null;
        }

        try
        {
            var segment = parts[1].Replace('-', '+').Replace('_', '/');
            segment = segment.PadRight(segment.Length + (4 - segment.Length % 4) % 4, '=');
            using var payload = JsonDocument.Parse(Convert.FromBase64String(segment));
            var root = payload.RootElement;
            return root.TryGetProperty("sub", out var sub)
                && ulong.TryParse(sub.GetString(), NumberStyles.None, CultureInfo.InvariantCulture, out var steamId64)
                && root.TryGetProperty("exp", out var exp)
                && exp.TryGetInt64(out var expiresAt)
                    ? new SessionToken(
                        value,
                        steamId64,
                        DateTimeOffset.FromUnixTimeSeconds(expiresAt),
                        DateTimeOffset.FromUnixTimeSeconds(root.TryGetProperty("iat", out var iat) && iat.TryGetInt64(out var issuedAt) ? issuedAt : 0))
                    : null;
        }
        catch (Exception ex) when (ex is FormatException or JsonException or InvalidOperationException)
        {
            return null;
        }
    }

    public static IEnumerable<string> ExtractTokens(string text) =>
        TokenPatterns().Matches(text)
            .Select(match => match.Groups.Values.Skip(1).First(group => group.Success).Value)
            .Distinct();

    public SessionToken? SelectBest(IEnumerable<string> candidates, ulong steamId64) =>
        candidates
            .Select(Decode)
            .Where(candidate => candidate is not null && candidate.SteamId64 == steamId64 && IsUsable(candidate))
            .MaxBy(candidate => (candidate!.ExpiresAt, candidate.IssuedAt));

    private bool IsUsable(SessionToken candidate)
    {
        lock (gate)
        {
            if (rejected.Contains(candidate.Value))
            {
                return false;
            }
        }

        return candidate.ExpiresAt - time.GetUtcNow() > MinimumLifetimeLeft;
    }

    // Every cache file is scanned: Chromium appends to its data_* block files without updating their
    // modified time, so a fresh token can sit in a file that looks days old.
    private SessionToken? FromBrowserCache(ulong steamId64)
    {
        var cacheFolder = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Steam", "htmlcache", "Default", "Cache", "Cache_Data");
        if (!Directory.Exists(cacheFolder))
        {
            return null;
        }

        var files = new DirectoryInfo(cacheFolder).EnumerateFiles()
            .Where(file => file.Name.StartsWith("data_", StringComparison.Ordinal) || file.Name.StartsWith("f_", StringComparison.Ordinal));
        return SelectBest(files.SelectMany(file => ScanFile(file.FullName)), steamId64);
    }

    // Cache entries are binary; Latin-1 keeps every byte so the ASCII token text survives the decoding.
    private static IEnumerable<string> ScanFile(string path)
    {
        var found = new List<string>();
        try
        {
            using var stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete);
            var buffer = new byte[ChunkSize + ChunkOverlap];
            var carried = 0;
            int read;
            while ((read = stream.Read(buffer, carried, ChunkSize)) > 0)
            {
                var length = carried + read;
                found.AddRange(ExtractTokens(Encoding.Latin1.GetString(buffer, 0, length)));
                carried = Math.Min(ChunkOverlap, length);
                Array.Copy(buffer, length - carried, buffer, 0, carried);
            }
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
        }

        return found;
    }

    private SessionToken? LoadSaved(ulong steamId64)
    {
        var (tokenPath, _) = Paths(steamId64);
        if (!File.Exists(tokenPath))
        {
            return null;
        }

        try
        {
            var value = Encoding.UTF8.GetString(
                ProtectedData.Unprotect(File.ReadAllBytes(tokenPath), Entropy, DataProtectionScope.CurrentUser)).Trim();
            if (Decode(value) is { } saved && saved.SteamId64 == steamId64 && IsUsable(saved))
            {
                return saved;
            }
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or CryptographicException)
        {
            log.Warn("Saved session token unreadable", ex);
        }

        Forget(steamId64);
        return null;
    }

    private void Save(SessionToken token)
    {
        try
        {
            Directory.CreateDirectory(TokenDirectory);
            var (tokenPath, metadataPath) = Paths(token.SteamId64);
            File.WriteAllBytes(
                tokenPath,
                ProtectedData.Protect(Encoding.UTF8.GetBytes(token.Value), Entropy, DataProtectionScope.CurrentUser));
            File.WriteAllText(metadataPath, new JsonObject
            {
                ["steamid64"] = token.SteamId64.ToString(CultureInfo.InvariantCulture),
                ["exp"] = token.ExpiresAt.ToUnixTimeSeconds(),
                ["iat"] = token.IssuedAt.ToUnixTimeSeconds(),
                ["source"] = "htmlcache",
                ["saved_at"] = time.GetUtcNow().ToUnixTimeSeconds(),
            }.ToJsonString(new JsonSerializerOptions { WriteIndented = true }));
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or CryptographicException)
        {
            log.Warn("Session token not saved", ex);
        }
    }

    private (string Token, string Metadata) Paths(ulong steamId64)
    {
        var name = steamId64.ToString(CultureInfo.InvariantCulture);
        return (Path.Combine(TokenDirectory, name + ".bin"), Path.Combine(TokenDirectory, name + ".meta.json"));
    }

    [GeneratedRegex("""
        "webapi_token"\s*:\s*"([^"]+)"|&quot;webapi_token&quot;\s*:\s*&quot;([^&"]+)&quot;|"loyalty_webapi_token"\s*:\s*"([^"]+)"|access_token=([A-Za-z0-9\-_]+\.[A-Za-z0-9\-_]+\.[A-Za-z0-9\-_]+)
        """)]
    private static partial Regex TokenPatterns();
}
