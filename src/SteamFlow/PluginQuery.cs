namespace SteamFlow;

public static class PluginQuery
{
    // A global action keyword ("*") reaches the plugin as an empty keyword, so the query is then just the command.
    public static string Build(string actionKeyword, string command) => $"{actionKeyword} {command}".Trim();
}
