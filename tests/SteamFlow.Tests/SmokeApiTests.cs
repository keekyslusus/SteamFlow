using System.Text;
using SteamFlow.Localization;
using SteamFlow.Settings;
using SteamFlow.Smoke;

namespace SteamFlow.Tests;

public static class Smokes
{
    // The context menu item is off by default, so menus built with default settings never show it.
    public static SmokeApiService Disabled(Translator text) =>
        new(new SmokeApiFiles(), new AntiCheatScanner(), new SmokePayload(""), new PluginSettings(), null!, text, TimeProvider.System, TestLog.Discard(), "");
}

public sealed class SmokeApiTests : IDisposable
{
    private readonly string root = Path.Combine(Path.GetTempPath(), "steamflow-smoke-" + Guid.NewGuid().ToString("N"));
    private readonly Dictionary<string, string> smokeHashes;

    public SmokeApiTests()
    {
        Write("payload/steam_api.dll", "smoke32");
        Write("payload/steam_api64.dll", "smoke64");
        smokeHashes = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase)
        {
            ["steam_api.dll"] = SmokeApiFiles.Sha256(Path.Combine(root, "payload", "steam_api.dll")),
            ["steam_api64.dll"] = SmokeApiFiles.Sha256(Path.Combine(root, "payload", "steam_api64.dll")),
        };
    }

    private string Game => Path.Combine(root, "game");

    private string Payload => Path.Combine(root, "payload");

    [Fact]
    public void Install_BacksUpOriginalsAndWritesConfig()
    {
        Write("game/bin/steam_api64.dll", "original64");
        Write("game/Game.exe", "exe");

        var result = new SmokeApiFiles().Install(Game, Payload, smokeHashes);

        Assert.True(result.Succeeded);
        Assert.Equal(1, result.ChangedDlls);
        Assert.Equal("original64", Read("game/bin/steam_api64_o.dll"));
        Assert.Equal("smoke64", Read("game/bin/steam_api64.dll"));
        Assert.True(File.Exists(Path.Combine(Game, "bin", "SmokeAPI.config.json")));
        Assert.Equal(SmokeAction.Remove, new SmokeApiFiles().Detect(Game, smokeHashes).Action);
    }

    [Fact]
    public void Remove_RestoresOriginalsAndCleansUp()
    {
        Write("game/steam_api.dll", "original32");
        var files = new SmokeApiFiles();
        files.Install(Game, Payload, smokeHashes);
        Write("game/SmokeAPI.log", "log");

        var result = files.Remove(Game, smokeHashes);

        Assert.True(result.Succeeded);
        Assert.Equal("original32", Read("game/steam_api.dll"));
        Assert.Equal(["steam_api.dll"], Directory.EnumerateFiles(Game).Select(Path.GetFileName));
        Assert.Equal(SmokeAction.Install, files.Detect(Game, smokeHashes).Action);
    }

    [Fact]
    public void Remove_KeepsSmokeApiWhenTheBackupIsGone()
    {
        Write("game/steam_api.dll", "smoke32");
        Write("game/SmokeAPI.config.json", "{}");

        var result = new SmokeApiFiles().Remove(Game, smokeHashes);

        Assert.False(result.Succeeded);
        Assert.NotEmpty(result.BackupMissing);
        Assert.True(File.Exists(Path.Combine(Game, "steam_api.dll")));
        Assert.True(File.Exists(Path.Combine(Game, "SmokeAPI.config.json")));
    }

    [Fact]
    public void Detect_RecognizesSmokeApiByHashWithoutConfig()
    {
        Write("game/steam_api64.dll", "smoke64");

        Assert.Equal(SmokeAction.Remove, new SmokeApiFiles().Detect(Game, smokeHashes).Action);
    }

    [Fact]
    public void Detect_LeavesUnknownBackupsAlone()
    {
        Write("game/a/steam_api.dll", "original32");
        Write("game/b/steam_api64.dll", "original64");
        Write("game/b/steam_api64_o.dll", "someone else's backup");

        var state = new SmokeApiFiles().Detect(Game, smokeHashes);

        Assert.Equal(SmokeAction.None, state.Action);
        Assert.Single(state.Ambiguous);
        Assert.False(new SmokeApiFiles().Install(Game, Payload, smokeHashes).Succeeded);
        Assert.Equal("original32", Read("game/a/steam_api.dll"));
    }

    [Fact]
    public void Detect_NothingToDoWithoutSteamApi()
    {
        Write("game/Game.exe", "exe");

        Assert.Equal(SmokeAction.None, new SmokeApiFiles().Detect(Game, smokeHashes).Action);
    }

    [Theory]
    [InlineData("game/EasyAntiCheat/settings.json", "Easy Anti-Cheat")]
    [InlineData("game/bin/BEService_x64.exe", "BattlEye")]
    [InlineData("game/start_protected_game.exe", "Easy Anti-Cheat")]
    [InlineData("game/Game.exe", null)]
    public void Scanner_FindsAntiCheatMarkers(string file, string? expected)
    {
        Write(file, "x");

        Assert.Equal(expected, new AntiCheatScanner().Scan(Game));
    }

    public void Dispose()
    {
        if (Directory.Exists(root))
        {
            Directory.Delete(root, recursive: true);
        }
    }

    private void Write(string relative, string content)
    {
        var path = Path.Combine(root, relative.Replace('/', Path.DirectorySeparatorChar));
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        File.WriteAllText(path, content, Encoding.UTF8);
    }

    private string Read(string relative) => File.ReadAllText(Path.Combine(root, relative.Replace('/', Path.DirectorySeparatorChar)));
}
