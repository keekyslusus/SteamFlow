namespace SteamFlow.Library;

public sealed record InstalledGame(int AppId, string Name, string InstallPath, long StateFlags = 0, long SizeOnDisk = 0);
