namespace SteamFlow.Localization;

public static class PlaytimeText
{
    public static string Format(Translator text, int minutes) =>
        minutes < 60
            ? text.Format("steamflow_playtime_minutes", minutes)
            : text.Format("steamflow_playtime_hours", minutes / 60.0);
}
