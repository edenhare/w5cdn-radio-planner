@echo off
setlocal
title RadioPlanner Windows Installer
set "REPO_ROOT=%~dp0"
if "%REPO_ROOT:~-1%"=="\" set "REPO_ROOT=%REPO_ROOT:~0,-1%"
set "LAUNCHER_BAT=%REPO_ROOT%\Start-RadioPlanner.bat"

echo ============================================================================
echo   RadioPlanner Web Studio -- Windows Setup (No uv / No PowerShell 7 required)
echo ============================================================================
echo.

REM 1. Register radioplanner.pth in official signed Python 3.14 site-packages
set "PY_SITE=%LOCALAPPDATA%\Python\pythoncore-3.14-64\Lib\site-packages"
if exist "%PY_SITE%" (
    echo import sys; sys.path[:0] = [r'%REPO_ROOT%\src', r'%REPO_ROOT%\.venv\Lib\site-packages'] > "%PY_SITE%\radioplanner.pth"
    echo [OK] Registered Python path in: "%PY_SITE%\radioplanner.pth"
)

REM 2. Install global CLI command in %USERPROFILE%\.local\bin\radioplanner.cmd
set "LOCAL_BIN=%USERPROFILE%\.local\bin"
if not exist "%LOCAL_BIN%" mkdir "%LOCAL_BIN%"
(
    echo @echo off
    echo call "%LAUNCHER_BAT%" %%*
) > "%LOCAL_BIN%\radioplanner.cmd"
echo [OK] Installed global CLI command: "%LOCAL_BIN%\radioplanner.cmd"

REM 3. Create Desktop shortcut using built-in Windows Script Host (VBScript)
set "VBS_TMP=%TEMP%\create_rp_shortcut.vbs"
(
    echo Set oWS = WScript.CreateObject^("WScript.Shell"^)
    echo sDesktop = oWS.SpecialFolders^("Desktop"^)
    echo Set oLink = oWS.CreateShortcut^(sDesktop ^& "\RadioPlanner Web Studio.lnk"^)
    echo oLink.TargetPath = "%LAUNCHER_BAT%"
    echo oLink.WorkingDirectory = "%REPO_ROOT%"
    echo oLink.Description = "Launch RadioPlanner Web Studio"
    echo oLink.IconLocation = "%SystemRoot%\System32\shell32.dll,13"
    echo oLink.Save
    echo WScript.Echo "[OK] Created Desktop shortcut: " ^& sDesktop ^& "\RadioPlanner Web Studio.lnk"
) > "%VBS_TMP%"
cscript //nologo "%VBS_TMP%"
del /q "%VBS_TMP%" >nul 2>nul

echo.
echo Setup complete! You can now:
echo   1. Double-click "RadioPlanner Web Studio" on your Desktop, OR
echo   2. Double-click Start-RadioPlanner.bat, OR
echo   3. Type "radioplanner" in any Command Prompt or terminal window.
echo.
endlocal
