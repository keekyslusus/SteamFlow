using SteamFlow.Diagnostics;

namespace SteamFlow.Tests;

internal static class TestLog
{
    // Tests that do not check the log still need one; it only gets a file if something is written.
    public static PluginLog Discard() =>
        new(Path.Combine(Path.GetTempPath(), "steamflow-tests-log", Guid.NewGuid().ToString("N") + ".log"), TimeProvider.System);
}
