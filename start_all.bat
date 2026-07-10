@echo off
title Ops Reporter (dev)
cd /d "%~dp0"
start "Ops Reporter API" cmd /k "cd /d "%~dp0server" && python -m uvicorn main:app --host 127.0.0.1 --port 8787 --workers 2"
timeout /t 2 /nobreak >nul
start "Ops Reporter UI" cmd /k "cd /d "%~dp0" && npm.cmd run dev -- --host 127.0.0.1 --port 5173"
start "" http://127.0.0.1:5173/reports/daily
echo API :8787  UI :5173
echo Close the two console windows to stop.
pause
