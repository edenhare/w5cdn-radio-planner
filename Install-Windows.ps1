# Install-Windows.ps1
# Sets up RadioPlanner Web Studio on Windows:
# 1. Installs a Smart App Control-safe global `radioplanner` command into ~/.local/bin (on PATH)
# 2. Creates a "RadioPlanner Web Studio" shortcut on the Windows Desktop

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$LauncherBat = Join-Path $RepoRoot "Start-RadioPlanner.bat"

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

# 2. Create Windows Desktop Shortcut
$DesktopDir = [Environment]::GetFolderPath("Desktop")
if (Test-Path $DesktopDir) {
    $ShortcutPath = Join-Path $DesktopDir "RadioPlanner Web Studio.lnk"
    $WshShell = New-Object -ComObject WScript.Shell
    $Shortcut = $WshShell.CreateShortcut($ShortcutPath)
    $IconPath = Join-Path $RepoRoot "src\web\static\icon.ico"
    $Shortcut.TargetPath = $LauncherBat
    $Shortcut.WorkingDirectory = $RepoRoot
    $Shortcut.Description = "Launch W5CDN RadioPlanner Cockpit Studio"
    $Shortcut.IconLocation = if (Test-Path $IconPath) { $IconPath } else { "$env:SystemRoot\System32\shell32.dll,13" }
    $Shortcut.Save()
    [Console]::WriteLine("[OK] Created Desktop shortcut: $ShortcutPath")
}
