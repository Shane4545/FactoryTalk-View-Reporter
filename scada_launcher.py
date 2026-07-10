"""
Ops Reporter — SCADA / plant PC entry point.

Frozen (OpsReporter.exe) or:  python scada_launcher.py
"""
from __future__ import annotations

import sys
import webbrowser
from pathlib import Path


def _browse_folder() -> int:
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()
    try:
        root.attributes("-topmost", True)
    except Exception:
        pass
    path = filedialog.askdirectory(title="Select FactoryTalk DLGLOG folder")
    root.destroy()
    print(path or "")
    return 0


def main() -> int:
    if "--browse-folder" in sys.argv:
        return _browse_folder()

    # Make server package importable (dev + frozen)
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS"))
        sys.path.insert(0, str(base))
        sys.path.insert(0, str(base / "server"))
    else:
        root = Path(__file__).resolve().parent
        sys.path.insert(0, str(root / "server"))

    from app_paths import ensure_runtime_dirs

    ensure_runtime_dirs()

    import uvicorn
    from main import app

    url = "http://127.0.0.1:8787/connect"
    print()
    print("  Ops Reporter")
    print(f"  Open: {url}")
    print("  Connect → Browse… → pick your DLGLOG folder → Save")
    print("  Close this window to stop.")
    print()
    try:
        webbrowser.open(url)
    except Exception:
        pass

    # Single worker — required for frozen exe reliability
    uvicorn.run(app, host="127.0.0.1", port=8787, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
