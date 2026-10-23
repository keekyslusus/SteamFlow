using System.Xml.Linq;
using SteamFlow.Localization;

namespace SteamFlow.Tests;

public static class EnglishText
{
    private static readonly XNamespace Xaml = "http://schemas.microsoft.com/winfx/2006/xaml";

    private static readonly Lazy<Dictionary<string, string>> Strings = new(() =>
        XDocument.Load(Path.Combine(AppContext.BaseDirectory, "Languages", "en.xaml"))
            .Root!
            .Elements()
            .ToDictionary(element => (string)element.Attribute(Xaml + "Key")!, element => element.Value));

    // Unknown keys throw so a typo in a key fails the test instead of rendering the key name.
    public static Translator Translator() => new(key => Strings.Value[key]);
}
