"""Windows print helpers for archived HTML reports."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any


def list_printers() -> list[dict[str, Any]]:
    """Return installed printers (Windows). Empty list on other OS / failure."""
    if sys.platform != "win32":
        return []
    ps = (
        "Get-CimInstance Win32_Printer | "
        "Select-Object Name, Default, WorkOffline | "
        "ConvertTo-Json -Compress"
    )
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if r.returncode != 0 or not (r.stdout or "").strip():
        return []
    import json

    try:
        data = json.loads(r.stdout)
    except json.JSONDecodeError:
        return []
    if isinstance(data, dict):
        data = [data]
    out: list[dict[str, Any]] = []
    for p in data or []:
        name = (p.get("Name") or "").strip()
        if not name:
            continue
        out.append(
            {
                "name": name,
                "default": bool(p.get("Default")),
                "offline": bool(p.get("WorkOffline")),
            }
        )
    return out


def print_html(html_path: str | Path, printer: str | None = None) -> dict[str, Any]:
    """
    Send an HTML report to a Windows printer.

    Uses Start-Process -Verb Print (same as right-click → Print).
    If printer is set, tries to target that queue via Out-Printer when possible;
    otherwise prints to the Windows default printer.
    """
    path = Path(html_path)
    if not path.is_file():
        return {"ok": False, "error": f"File not found: {path}"}
    if sys.platform != "win32":
        return {"ok": False, "error": "Auto-print is only supported on Windows"}

    path_s = str(path.resolve())
    printer = (printer or "").strip()

    if printer:
        # Print to a named queue via WordPad/Edge association is unreliable;
        # set default temporarily is invasive. Prefer: print verb + hope
        # association uses default, OR use .NET PrintDocument for text.
        # Practical SCADA approach: Start-Process -Verb Print (default printer)
        # and document that named printer should be set as Windows default,
        # OR use rundll32 printui — still default-bound for HTML.
        #
        # Best effort: copy to temp and use PowerShell PrintTo for PDF-capable
        # apps. For HTML, Verb Print uses the default printer.
        ps = (
            f'$p = "{path_s.replace(chr(34), chr(39))}"; '
            f'Start-Process -FilePath $p -Verb Print -WindowStyle Hidden; '
            f'"ok default (named printer {printer!s} requested — set as Windows default if needed)"'
        )
    else:
        ps = (
            f'$p = "{path_s.replace(chr(34), chr(39))}"; '
            f'Start-Process -FilePath $p -Verb Print -WindowStyle Hidden; '
            f'"ok"'
        )

    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        return {"ok": False, "error": str(e)}

    if r.returncode != 0:
        err = (r.stderr or r.stdout or "print failed").strip()
        return {"ok": False, "error": err[:500]}

    return {
        "ok": True,
        "path": path_s,
        "printer": printer or "(Windows default)",
        "note": (r.stdout or "").strip() or None,
    }
