using System.Globalization;

namespace SteamFlow.Localization;

public sealed class Translator(Func<string, string> lookup)
{
    // Each language file names its own culture so dates and numbers follow the plugin language, not the OS.
    public CultureInfo Culture
    {
        get
        {
            try
            {
                return CultureInfo.GetCultureInfo(lookup("steamflow_culture"));
            }
            catch (CultureNotFoundException)
            {
                return CultureInfo.InvariantCulture;
            }
        }
    }

    public string Get(string key) => lookup(key);

    public string Format(string key, params object?[] args) => string.Format(Culture, lookup(key), args);
}
