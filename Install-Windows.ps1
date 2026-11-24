# Install-Windows.ps1
# Sets up W5CDN RadioPlanner on Windows under the unified W5CDN Suite layout:
# 1. Installs a Smart App Control-safe global `radioplanner` command into ~/.local/bin (on PATH)
# 2. Installs a launcher stub under %LOCALAPPDATA%\Programs\W5CDN\RadioPlanner (alongside Net-Logger & NTS)
# 3. Creates a Start Menu shortcut under Start Menu -> W5CDN -> W5CDN RadioPlanner
# 4. Creates a "W5CDN RadioPlanner" shortcut on the Windows Desktop

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$LauncherBat = Join-Path $RepoRoot "Start-RadioPlanner.bat"
$IconPath = Join-Path $RepoRoot "src\web\static\icon.ico"
$ResolvedIcon = if (Test-Path $IconPath) { $IconPath } else { "$env:SystemRoot\System32\shell32.dll,13" }

# 1. Create global CLI shim in ~/.local/bin/radioplanner.cmd
$LocalBin = Join-Path $HOME ".local\bin"
if (-not (Test-Path $LocalBin)) {
    New-Item -ItemType Directory -Path $LocalBin -Force | Out-Null
}
$GlobalCmd = Join-Path $LocalBin "radioplanner.cmd"
$CmdContent = @"
@echo off
call "$LauncherBat" %*
"@
Set-Content -Path $GlobalCmd -Value $CmdContent -Encoding Ascii
[Console]::WriteLine("[OK] Installed global CLI command: $GlobalCmd")

# 2. Place suite launcher under %LOCALAPPDATA%\Programs\W5CDN\RadioPlanner
$SuiteInstallDir = Join-Path $env:LOCALAPPDATA "Programs\W5CDN\RadioPlanner"
if (-not (Test-Path $SuiteInstallDir)) {
    New-Item -ItemType Directory -Path $SuiteInstallDir -Force | Out-Null
}
$SuiteLauncher = Join-Path $SuiteInstallDir "W5CDN-RadioPlanner.cmd"
Set-Content -Path $SuiteLauncher -Value $CmdContent -Encoding Ascii
[Console]::WriteLine("[OK] Installed W5CDN Suite launcher: $SuiteLauncher")

$WshShell = New-Object -ComObject WScript.Shell

# 3. Create Start Menu shortcut under W5CDN group (matches Net-Logger & NTS)
$StartMenuPrograms = [Environment]::GetFolderPath("Programs")
if (Test-Path $StartMenuPrograms) {
    $W5cdnMenuDir = Join-Path $StartMenuPrograms "W5CDN"
    if (-not (Test-Path $W5cdnMenuDir)) {
        New-Item -ItemType Directory -Path $W5cdnMenuDir -Force | Out-Null
    }
    $MenuShortcutPath = Join-Path $W5cdnMenuDir "W5CDN RadioPlanner.lnk"
    $MenuShortcut = $WshShell.CreateShortcut($MenuShortcutPath)
    $MenuShortcut.TargetPath = $LauncherBat
    $MenuShortcut.WorkingDirectory = $RepoRoot
    $MenuShortcut.Description = "Launch W5CDN RadioPlanner Cockpit Studio"
    $MenuShortcut.IconLocation = $ResolvedIcon
    $MenuShortcut.Save()
    [Console]::WriteLine("[OK] Created Start Menu shortcut: $MenuShortcutPath")
}

# 4. Create Windows Desktop Shortcut
$DesktopDir = [Environment]::GetFolderPath("Desktop")
if (Test-Path $DesktopDir) {
    $ShortcutPath = Join-Path $DesktopDir "W5CDN RadioPlanner.lnk"
    $Shortcut = $WshShell.CreateShortcut($ShortcutPath)
    $Shortcut.TargetPath = $LauncherBat
    $Shortcut.WorkingDirectory = $RepoRoot
    $Shortcut.Description = "Launch W5CDN RadioPlanner Cockpit Studio"
    $Shortcut.IconLocation = $ResolvedIcon
    $Shortcut.Save()
    [Console]::WriteLine("[OK] Created Desktop shortcut: $ShortcutPath")
}
