@echo off
setlocal
title RadioPlanner Web Studio
cd /d "%~dp0"
set "PYTHONPATH=%~dp0src;%~dp0.venv\Lib\site-packages;%PYTHONPATH%"

if exist "%LOCALAPPDATA%\Python\pythoncore-3.14-64\python.exe" (
    "%LOCALAPPDATA%\Python\pythoncore-3.14-64\python.exe" -m cli.main %*
) else (
    python -m cli.main %*
)

if errorlevel 1 (
    echo.
    echo [ERROR] RadioPlanner exited with an error.
    pause
)
endlocal
