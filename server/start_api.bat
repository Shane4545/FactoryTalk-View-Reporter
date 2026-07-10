@echo off
cd /d "%~dp0"
echo Starting Ops Reporter API on http://127.0.0.1:8787 (2 workers)
python -m uvicorn main:app --host 127.0.0.1 --port 8787 --workers 2
