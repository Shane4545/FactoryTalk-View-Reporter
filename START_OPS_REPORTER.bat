@echo off
title Ops Reporter
cd /d "%~dp0"

echo.
echo  Ops Reporter v1 — starting...
echo.

where python >nul 2>&1
if errorlevel 1 (
  echo ERROR: Python not found on PATH. Install Python 3.11+ and retry.
  pause
  exit /b 1
)

where npm.cmd >nul 2>&1
if errorlevel 1 (
  echo ERROR: npm not found. Install Node.js LTS and retry.
  pause
  exit /b 1
)

echo [1/3] Python packages...
python -m pip install -q -r server\requirements.txt

if not exist "dist\index.html" (
  echo [2/3] Building UI...
  call npm.cmd install --silent
  call npm.cmd run build
  if errorlevel 1 (
    echo ERROR: UI build failed.
    pause
    exit /b 1
  )
) else (
  echo [2/3] UI already built.
)

echo [3/3] http://127.0.0.1:8787  — close this window to stop
echo.
start "" http://127.0.0.1:8787/reports/daily
cd /d "%~dp0server"
python -m uvicorn main:app --host 127.0.0.1 --port 8787 --workers 2
pause
