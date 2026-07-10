@echo off
title Ops Reporter — share with co-workers
cd /d "%~dp0"

echo.
echo  1) Starting Ops Reporter on http://127.0.0.1:8787 ...
echo  2) Opening a public Cloudflare Tunnel URL for co-workers
echo  Keep THIS window open while they are viewing.
echo.

where python >nul 2>&1
if errorlevel 1 (
  echo ERROR: Python not found.
  pause
  exit /b 1
)

if not exist "tools\cloudflared.exe" (
  echo Downloading cloudflared...
  mkdir tools 2>nul
  powershell -NoProfile -Command "Invoke-WebRequest -Uri 'https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe' -OutFile 'tools\cloudflared.exe' -UseBasicParsing"
)

start "OpsReporter-API" /MIN cmd /c "cd /d ""%~dp0server"" && python -m uvicorn main:app --host 127.0.0.1 --port 8787"
timeout /t 4 /nobreak >nul

echo.
echo  Public URL will appear below — copy and send to co-workers:
echo.
tools\cloudflared.exe tunnel --url http://127.0.0.1:8787 --no-autoupdate
pause
