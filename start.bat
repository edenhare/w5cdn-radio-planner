@echo off
setlocal
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
    set "PY_BIN=.venv\Scripts\python.exe"
    goto :run
)

where uv >nul 2>nul
if %errorlevel%==0 (
    echo Setting up virtual environment with uv...
    uv sync
    if exist ".venv\Scripts\python.exe" (
        set "PY_BIN=.venv\Scripts\python.exe"
        goto :run
    )
)

where py >nul 2>nul
if %errorlevel%==0 (
    echo Creating Python virtual environment with py launcher...
    py -3 -m venv .venv
) else (
    where python >nul 2>nul
    if %errorlevel%==0 (
        echo Creating Python virtual environment...
        python -m venv .venv
    ) else (
        echo Error: Python 3.11+ or uv is required to run from source.
        echo Install Python from https://www.python.org/downloads/ and try again.
        pause
        exit /b 1
    )
)

echo Installing dependencies...
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -e .
set "PY_BIN=.venv\Scripts\python.exe"

:run
set "PYTHONPATH=%~dp0src;%PYTHONPATH%"
"%PY_BIN%" -m web.desktop %*
if %errorlevel% neq 0 (
    echo.
    echo W5CDN RadioPlanner exited with error code %errorlevel%.
    pause
)
endlocal
