using System.Text;
using SteamFlow.Steam;

namespace SteamFlow.Accounts;

// loginusers.vdf is a flat two-level map of strings, so it is edited as ordered key/value lists and written
// back by hand; every key Steam stores is kept, only the auto-login flags change.
public sealed class LoginUsersFile
{
    private readonly List<(string SteamId64, List<KeyValuePair<string, string>> Values)> users;

    private LoginUsersFile(List<(string, List<KeyValuePair<string, string>>)> users) => this.users = users;

    public static LoginUsersFile Parse(Stream stream) =>
        new([.. Vdf.ReadText(stream).Items().Select(user => (
            user.Name,
            user.Items()
                .Select(value => new KeyValuePair<string, string>(value.Name, user.Text(value.Name) ?? ""))
                .ToList()))]);

    public static LoginUsersFile Read(string path)
    {
        using var stream = Vdf.OpenShared(path);
        return Parse(stream);
    }

    // Current Steam reads "AutoLogin"; older builds used "MostRecent" and "AllowAutoLogin", which are
    // updated only where the file already has them.
    public bool MakeAutoLogin(string steamId64)
    {
        if (users.All(user => user.SteamId64 != steamId64))
        {
            return false;
        }

        foreach (var (id, values) in users)
        {
            var target = id == steamId64;
            Set(values, "AutoLogin", target ? "1" : "0", addIfMissing: target);
            Set(values, "MostRecent", target ? "1" : "0", addIfMissing: false);
            if (target)
            {
                Set(values, "RememberPassword", "1", addIfMissing: true);
                Set(values, "AllowAutoLogin", "1", addIfMissing: false);
            }
        }

        return true;
    }

    public string? AccountName(string steamId64) =>
        users.FirstOrDefault(user => user.SteamId64 == steamId64).Values?
            .FirstOrDefault(value => value.Key.Equals("AccountName", StringComparison.OrdinalIgnoreCase)).Value;

    public string Serialize()
    {
        var text = new StringBuilder("\"users\"\n{\n");
        foreach (var (steamId64, values) in users)
        {
            text.Append('\t').Append(Quote(steamId64)).Append("\n\t{\n");
            foreach (var (key, value) in values)
            {
                text.Append("\t\t").Append(Quote(key)).Append("\t\t").Append(Quote(value)).Append('\n');
            }

            text.Append("\t}\n");
        }

        return text.Append("}\n").ToString();
    }

    // A backup is kept and the file is replaced atomically so a crash mid-write cannot leave Steam without it.
    public void Write(string path)
    {
        var temporary = path + ".tmp";
        File.WriteAllText(temporary, Serialize(), new UTF8Encoding(encoderShouldEmitUTF8Identifier: false));
        File.Copy(path, path + ".steamflow.bak", overwrite: true);
        File.Move(temporary, path, overwrite: true);
    }

    private static void Set(List<KeyValuePair<string, string>> values, string key, string value, bool addIfMissing)
    {
        var index = values.FindIndex(pair => pair.Key.Equals(key, StringComparison.OrdinalIgnoreCase));
        if (index >= 0)
        {
            values[index] = new KeyValuePair<string, string>(values[index].Key, value);
        }
        else if (addIfMissing)
        {
            values.Add(new KeyValuePair<string, string>(key, value));
        }
    }

    private static string Quote(string value) => '"' + value.Replace("\\", "\\\\").Replace("\"", "\\\"") + '"';
}
