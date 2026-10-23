using System.Globalization;
using System.Numerics;
using SteamFlow.Diagnostics;
using SteamFlow.Steam;
using ValveKeyValue;

namespace SteamFlow.Library;

public sealed record AchievementProgress(int Unlocked, int Total);

public sealed record AchievementsState(AchievementProgress? Progress, bool HasStatsFile);

public sealed class AchievementsReader(PluginLog log)
{
    public AchievementsState Read(string steamPath, uint accountId, int appId)
    {
        var statsFolder = Path.Combine(steamPath, "appcache", "stats");
        var schemaPath = Path.Combine(statsFolder, $"UserGameStatsSchema_{appId}.bin");
        var userStatsPath = Path.Combine(statsFolder, string.Create(CultureInfo.InvariantCulture, $"UserGameStats_{accountId}_{appId}.bin"));
        var hasStatsFile = File.Exists(userStatsPath);
        if (!File.Exists(schemaPath))
        {
            return new AchievementsState(null, hasStatsFile);
        }

        try
        {
            IReadOnlyDictionary<string, uint> masks;
            using (var schema = Vdf.OpenShared(schemaPath))
            {
                masks = ReadAchievementMasks(schema);
            }

            var total = masks.Values.Sum(mask => BitOperations.PopCount(mask));
            if (total <= 0)
            {
                return new AchievementsState(null, hasStatsFile);
            }

            var unlocked = 0;
            if (hasStatsFile)
            {
                using var userStats = Vdf.OpenShared(userStatsPath);
                unlocked = CountUnlocked(userStats, masks);
            }

            return new AchievementsState(new AchievementProgress(unlocked, total), hasStatsFile);
        }
        catch (Exception ex) when (Vdf.IsReadError(ex))
        {
            log.Warn("Achievement stats unreadable", ex, $"app {appId}");
            return new AchievementsState(null, hasStatsFile);
        }
    }

    // Achievements live in stats that list their "bits"; every other stat is a plain counter.
    public static IReadOnlyDictionary<string, uint> ReadAchievementMasks(Stream schema)
    {
        var masks = new Dictionary<string, uint>();
        foreach (var stat in Vdf.ReadBinary(schema).Child("stats")?.Items() ?? [])
        {
            var mask = 0u;
            foreach (var bit in stat.Child("bits")?.Items() ?? [])
            {
                if (int.TryParse(bit.Name, NumberStyles.None, CultureInfo.InvariantCulture, out var index) && index < 32)
                {
                    mask |= 1u << index;
                }
            }

            if (mask != 0)
            {
                masks[stat.Name] = mask;
            }
        }

        return masks;
    }

    public static int CountUnlocked(Stream userStats, IReadOnlyDictionary<string, uint> masks)
    {
        var unlocked = 0;
        foreach (var stat in Vdf.ReadBinary(userStats).Items())
        {
            if (!masks.TryGetValue(stat.Name, out var mask) || stat.Child("data") is not { } data)
            {
                continue;
            }

            var bits = data.Value.ValueType switch
            {
                KVValueType.Int32 => unchecked((uint)data.Value.ToInt32(CultureInfo.InvariantCulture)),
                KVValueType.UInt64 => unchecked((uint)data.Value.ToUInt64(CultureInfo.InvariantCulture)),
                _ => 0u,
            };
            unlocked += BitOperations.PopCount(bits & mask);
        }

        return unlocked;
    }
}
