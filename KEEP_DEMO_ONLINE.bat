@echo off
REM Free public demo — no credit card. Your PC must stay on.
REM Restarts the Cloudflare quick tunnel if it dies.
title Ops Reporter — free public demo
cd /d "%~dp0"

if not exist "tools\cloudflared.exe" (
  echo Downloading cloudflared...
  mkdir tools 2>nul
  powershell -NoProfile -Command "Invoke-WebRequest -Uri 'https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe' -OutFile 'tools\cloudflared.exe' -UseBasicParsing"
)

powershell -NoProfile -Command "try { (Invoke-WebRequest http://127.0.0.1:8787/api/health -UseBasicParsing -TimeoutSec 3).StatusCode } catch { exit 1 }" >nul 2>&1
if errorlevel 1 (
  echo Starting Ops Reporter API...
  start "OpsReporter-API" /MIN cmd /c "cd /d ""%~dp0server"" && python -m uvicorn main:app --host 127.0.0.1 --port 8787"
  timeout /t 5 /nobreak >nul
)

echo.
echo  Free public tunnel — leave this window open.
echo.

:loop
taskkill /IM cloudflared.exe /F >nul 2>&1
timeout /t 1 /nobreak >nul
del /q tools\tunnel.out tools\tunnel.err tools\url.tmp >nul 2>&1
start /B "" cmd /c "tools\cloudflared.exe tunnel --url http://127.0.0.1:8787 --no-autoupdate >tools\tunnel.out 2>tools\tunnel.err"

set URL=
for /L %%i in (1,1,40) do (
  powershell -NoProfile -Command "$t=(Get-Content tools\tunnel.err,tools\tunnel.out -ErrorAction SilentlyContinue)-join \"`n\"; $m=[regex]::Match($t,'https://[a-z0-9-]+\.trycloudflare\.com'); if($m.Success){$m.Value}" > tools\url.tmp 2>nul
  set /p URL=<tools\url.tmp
  if defined URL if not "%URL%"=="" goto goturl
  timeout /t 2 /nobreak >nul
)
echo Failed to get tunnel URL — retrying in 10s...
timeout /t 10 /nobreak >nul
goto loop

:goturl
echo %URL%> PUBLIC_URL.txt
echo.
echo  ============================================================
echo   SEND THIS LINK TO CO-WORKERS:
echo   %URL%
echo  ============================================================
echo.

:watch
timeout /t 45 /nobreak >nul
powershell -NoProfile -Command "try { $r=Invoke-WebRequest '%URL%/api/health' -UseBasicParsing -TimeoutSec 20; if($r.StatusCode -ne 200){exit 1}; exit 0 } catch { exit 1 }"
if errorlevel 1 (
  echo Tunnel dead at %TIME% — restarting...
  goto loop
)
goto watch
