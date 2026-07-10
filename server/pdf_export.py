"""Export archived HTML reports to PDF (Windows Edge/Chrome headless)."""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


def _browser_candidates() -> list[Path]:
    names = [
        Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
        Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
        Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
        Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
    ]
    found: list[Path] = []
    for p in names:
        if p.is_file():
            found.append(p)
    # Also try PATH
    for cmd in ("msedge", "chrome", "google-chrome"):
        which = shutil.which(cmd)
        if which:
            found.append(Path(which))
    # de-dupe
    out: list[Path] = []
    seen: set[str] = set()
    for p in found:
        key = str(p).lower()
        if key not in seen:
            seen.add(key)
            out.append(p)
    return out


def html_to_pdf(html_path: str | Path, pdf_path: str | Path) -> dict[str, Any]:
    """
    Render HTML to PDF via Edge/Chrome --print-to-pdf.
    Returns {ok, path, error?}.
    """
    html = Path(html_path).resolve()
    pdf = Path(pdf_path).resolve()
    if not html.is_file():
        return {"ok": False, "error": f"HTML not found: {html}"}
    pdf.parent.mkdir(parents=True, exist_ok=True)

    if sys.platform != "win32":
        return {"ok": False, "error": "PDF export currently requires Windows (Edge/Chrome)"}

    browsers = _browser_candidates()
    if not browsers:
        return {
            "ok": False,
            "error": "No Edge/Chrome found for PDF export. Install Microsoft Edge.",
        }

    # file:/// URL with forward slashes
    uri = html.as_uri()
    last_err = ""
    for browser in browsers:
        cmd = [
            str(browser),
            "--headless=new",
            "--disable-gpu",
            "--no-pdf-header-footer",
            f"--print-to-pdf={pdf}",
            uri,
        ]
        try:
            r = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=90,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as e:
            last_err = str(e)
            continue
        if pdf.is_file() and pdf.stat().st_size > 0:
            return {
                "ok": True,
                "path": str(pdf),
                "browser": str(browser),
                "bytes": pdf.stat().st_size,
            }
        last_err = (r.stderr or r.stdout or f"exit {r.returncode}").strip()[:400]

    return {"ok": False, "error": last_err or "PDF export failed"}
