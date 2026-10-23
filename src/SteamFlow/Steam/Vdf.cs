using System.Globalization;
using ValveKeyValue;

namespace SteamFlow.Steam;

public static class Vdf
{
    private static readonly KVSerializer TextSerializer = KVSerializer.Create(KVSerializationFormat.KeyValues1Text);
    private static readonly KVSerializer BinarySerializer = KVSerializer.Create(KVSerializationFormat.KeyValues1Binary);

    // Steam escapes backslashes and quotes in every text KeyValues file it writes.
    private static readonly KVSerializerOptions TextOptions = new() { HasEscapeSequences = true };

    public static KVObject ReadText(Stream stream) => TextSerializer.Deserialize(stream, TextOptions);

    public static KVObject ReadText(string path)
    {
        using var stream = OpenShared(path);
        return ReadText(stream);
    }

    public static KVObject ReadBinary(Stream stream) => BinarySerializer.Deserialize(stream);

    // Steam keeps its files open while running; a plain read would fail with a sharing violation.
    public static FileStream OpenShared(string path) =>
        new(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete);

    public static bool IsReadError(Exception ex) =>
        ex is IOException or UnauthorizedAccessException or KeyValueException or InvalidDataException or FormatException;

    public static IEnumerable<KVObject> Items(this KVObject obj) =>
        obj.Value.ValueType == KVValueType.Collection ? obj.Children : [];

    public static KVObject? Child(this KVObject? obj, string name) =>
        obj?.Items().FirstOrDefault(child => string.Equals(child.Name, name, StringComparison.OrdinalIgnoreCase));

    public static string? Text(this KVObject obj, string name) =>
        obj.Child(name) is { } child && child.Value.ValueType != KVValueType.Collection
            ? child.Value.ToString(CultureInfo.InvariantCulture)
            : null;

    public static long? Number(this KVObject obj, string name) =>
        long.TryParse(obj.Text(name), NumberStyles.Integer, CultureInfo.InvariantCulture, out var value) ? value : null;
}
