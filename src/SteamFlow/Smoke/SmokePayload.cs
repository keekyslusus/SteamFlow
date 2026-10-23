using Flow.Launcher.Plugin;

namespace SteamFlow.Smoke;

// The SmokeAPI DLLs are not shipped with the plugin; they are downloaded on first use and pinned by hash.
public sealed class SmokePayload(string folder)
{
    private const long MaxFileBytes = 16 * 1024 * 1024;
    private const string BaseUrl = "https://raw.githubusercontent.com/keekyslusus/SteamFlow/smapi/smokeapi/";

    public static readonly IReadOnlyDictionary<string, string> Hashes = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase)
    {
        ["steam_api.dll"] = "145AADFFFDE5140991995D76DCA8F2423E9D7F9DBB66BC21565CEE59746F027B",
        ["steam_api64.dll"] = "3891CD70B8E06CAD474B9EA5B6D7C3D19B9948C41DF2495E3CF02D2A256498EF",
    };

    public string Folder => folder;

    public bool Ready() => Missing().Count == 0;

    // Downloads into a temporary file and only moves a file into place once its hash matches,
    // so a broken download can never be installed into a game.
    public async Task DownloadAsync(IPublicAPI flow, Action<double> progress, CancellationToken token)
    {
        var missing = Missing();
        Directory.CreateDirectory(folder);
        for (var index = 0; index < missing.Count; index++)
        {
            var name = missing[index];
            var temporary = Path.Combine(folder, name + ".download");
            var offset = index * 100.0 / missing.Count;
            await flow.HttpDownloadAsync(BaseUrl + name, temporary, percent => progress(offset + percent / missing.Count), token);

            var size = new FileInfo(temporary).Length;
            if (size is 0 or > MaxFileBytes || !SmokeApiFiles.Sha256(temporary).Equals(Hashes[name], StringComparison.OrdinalIgnoreCase))
            {
                File.Delete(temporary);
                throw new InvalidDataException($"{name} failed verification");
            }

            File.Move(temporary, Path.Combine(folder, name), overwrite: true);
        }
    }

    private List<string> Missing() =>
        Hashes
            .Where(file =>
            {
                var path = Path.Combine(folder, file.Key);
                try
                {
                    return !File.Exists(path) || !SmokeApiFiles.Sha256(path).Equals(file.Value, StringComparison.OrdinalIgnoreCase);
                }
                catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
                {
                    return true;
                }
            })
            .Select(file => file.Key)
            .ToList();
}
