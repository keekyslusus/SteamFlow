param(
    [string]$Configuration = "Debug"
)

$ErrorActionPreference = "Stop"

$project = Join-Path $PSScriptRoot "..\src\SteamFlow\SteamFlow.csproj"
$output = Join-Path $PSScriptRoot "..\src\SteamFlow\bin\$Configuration"
$pluginDir = Join-Path $env:APPDATA "FlowLauncher\Plugins\SteamFlowCS-dev"
$flowExe = Join-Path $env:LOCALAPPDATA "FlowLauncher\Flow.Launcher.exe"

dotnet build $project -c $Configuration
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

# Flow keeps the plugin assembly loaded, so the folder cannot be replaced while it runs.
Get-Process Flow.Launcher -ErrorAction SilentlyContinue | Stop-Process -Force
Get-Process Flow.Launcher -ErrorAction SilentlyContinue | Wait-Process -Timeout 10

# The process can be gone before Windows releases its file locks.
for ($attempt = 1; Test-Path $pluginDir; $attempt++) {
    try {
        Remove-Item $pluginDir -Recurse -Force
    } catch {
        if ($attempt -ge 20) { throw }
        Start-Sleep -Milliseconds 250
    }
}
Copy-Item $output $pluginDir -Recurse -Exclude "*.pdb"

# The release shares its ID and keyword with the installed store version; the dev build gets its own so both
# can be installed side by side (Flow does not load two plugins with one ID).
$manifestPath = Join-Path $pluginDir "plugin.json"
$manifest = Get-Content $manifestPath -Raw | ConvertFrom-Json
$manifest.ID = "5D1B8E0C2A4F4E7B9C3D6A1F0E2B4C8D"
$manifest.ActionKeyword = "stc"
$manifest.Name = "SteamFlow (dev)"
$manifest | ConvertTo-Json | Set-Content $manifestPath -Encoding UTF8

Start-Process $flowExe
