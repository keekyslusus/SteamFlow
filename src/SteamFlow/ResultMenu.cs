using Flow.Launcher.Plugin;

namespace SteamFlow;

// Results carry their own context menu so Main can show it without knowing which feature built the result.
public sealed record ResultMenu(Func<List<Result>> Build);
