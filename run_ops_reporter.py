"""
Ops Reporter — production entry.

Serves API + built UI from dist/ on one port.
Run:  python run_ops_reporter.py
Or:   START_OPS_REPORTER.bat
"""
from __future__ import annotations

import subprocess
import sys
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SERVER = ROOT / "server"
DIST = ROOT / "dist"


def main() -> int:
    if not DIST.is_dir() or not (DIST / "index.html").is_file():
        print("Building UI (first run)...")
        r = subprocess.run(["npm.cmd", "run", "build"], cwd=ROOT)
        if r.returncode != 0:
            print("UI build failed")
            return r.returncode

    sys.path.insert(0, str(SERVER))
    import uvicorn

    print("Ops Reporter → http://127.0.0.1:8787")
    webbrowser.open("http://127.0.0.1:8787/reports/daily")
    uvicorn.run(
        "main:app",
        app_dir=str(SERVER),
        host="127.0.0.1",
        port=8787,
        workers=2,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
