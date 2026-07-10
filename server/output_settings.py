"""Output folder settings — mirrors XLReporter Project Settings PDF/Web/Reports folders."""
from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from app_paths import app_home
from plant_settings import load_config, save_config

# Verified XLReporter convention (project-settings.pdf p.2–3):
# if last folder segment is not PDF / Web / Reports, that name is appended.


DEFAULT_OUTPUTS: dict[str, Any] = {
    "archive_folder": "",  # blank → <app>/archive  (JSON + HTML working store)
    "pdf_folder": "",  # blank → <app>/PDF
    "web_folder": "",  # blank → <app>/Web
    "subfolders": True,  # kind/YYYY/MM under PDF and Web
    "save_pdf": True,
    "save_html": True,
    "save_json": True,
    "copy_to": "",  # optional secondary folder (network share), like File Manager Copy
}


def default_outputs() -> dict[str, Any]:
    import json

    return json.loads(json.dumps(DEFAULT_OUTPUTS))


def get_outputs() -> dict[str, Any]:
    cfg = load_config()
    out = default_outputs()
    raw = cfg.get("outputs")
    if isinstance(raw, dict):
        out.update({k: v for k, v in raw.items() if v is not None})
    return out


def save_outputs(updates: dict[str, Any]) -> dict[str, Any]:
    current = get_outputs()
    for k, v in (updates or {}).items():
        if k in DEFAULT_OUTPUTS:
            current[k] = v
    # XLReporter-style: ensure trailing folder name PDF / Web when user picks a parent
    current["pdf_folder"] = _ensure_named_leaf(str(current.get("pdf_folder") or ""), "PDF")
    current["web_folder"] = _ensure_named_leaf(str(current.get("web_folder") or ""), "Web")
    if current.get("archive_folder"):
        current["archive_folder"] = _ensure_named_leaf(
            str(current["archive_folder"]), "archive"
        )
    save_config({"outputs": current})
    return current


def _ensure_named_leaf(path: str, leaf: str) -> str:
    path = (path or "").strip().strip('"')
    if not path:
        return ""
    p = Path(path)
    if p.name.lower() != leaf.lower():
        p = p / leaf
    return str(p)


def archive_root() -> Path:
    out = get_outputs()
    custom = (out.get("archive_folder") or "").strip()
    root = Path(custom) if custom else (app_home() / "archive")
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


def pdf_root() -> Path:
    out = get_outputs()
    custom = (out.get("pdf_folder") or "").strip()
    root = Path(custom) if custom else (app_home() / "PDF")
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


def web_root() -> Path:
    out = get_outputs()
    custom = (out.get("web_folder") or "").strip()
    root = Path(custom) if custom else (app_home() / "Web")
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


def dated_subpath(kind: str, start_date: str) -> Path:
    """kind/YYYY/MM from start date (XLReporter-style year/month folders)."""
    day = (start_date or "")[:10]
    try:
        dt = datetime.strptime(day, "%Y-%m-%d")
        return Path(kind) / f"{dt.year:04d}" / f"{dt.month:02d}"
    except ValueError:
        return Path(kind)


def safe_report_stem(kind: str, start: str, end: str) -> str:
    start_d = (start or "unknown")[:10].replace(":", "")
    end_d = (end or start_d)[:10].replace(":", "")
    if end_d == start_d:
        return f"{kind}_{start_d}"
    return f"{kind}_{start_d}_to_{end_d}"


def publish_outputs(
    *,
    kind: str,
    start: str,
    end: str,
    html_path: Path,
    json_path: Path | None = None,
) -> dict[str, Any]:
    """
    Copy/publish HTML (+ optional PDF) into configured Web/PDF folders,
    and optional copy_to secondary folder (File Manager–style Copy).
    """
    from pdf_export import html_to_pdf

    out = get_outputs()
    result: dict[str, Any] = {"ok": True, "pdf": None, "web": None, "copy": None}
    stem = safe_report_stem(kind, start, end)
    sub = dated_subpath(kind, start) if out.get("subfolders") else Path()

    # Web (HTML) — project-settings.pdf Web folder
    if out.get("save_html", True) and html_path.is_file():
        dest_dir = web_root() / sub
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f"{stem}.html"
        shutil.copy2(html_path, dest)
        result["web"] = str(dest)

    # PDF — project-settings.pdf PDF folder + scheduler Save*PDF
    if out.get("save_pdf", True) and html_path.is_file():
        dest_dir = pdf_root() / sub
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f"{stem}.pdf"
        printed = html_to_pdf(html_path, dest)
        result["pdf"] = printed
        if not printed.get("ok"):
            result["ok"] = False
            result["pdf_error"] = printed.get("error")

    # Secondary copy (file-manager.pdf Copy → Target Folder)
    copy_to = (out.get("copy_to") or "").strip()
    if copy_to:
        target = Path(copy_to)
        if out.get("subfolders"):
            target = target / sub
        target.mkdir(parents=True, exist_ok=True)
        copied: list[str] = []
        if result.get("web"):
            p = Path(result["web"])
            shutil.copy2(p, target / p.name)
            copied.append(str(target / p.name))
        pdf_info = result.get("pdf") or {}
        if isinstance(pdf_info, dict) and pdf_info.get("ok") and pdf_info.get("path"):
            p = Path(pdf_info["path"])
            shutil.copy2(p, target / p.name)
            copied.append(str(target / p.name))
        elif json_path and json_path.is_file():
            shutil.copy2(json_path, target / json_path.name)
            copied.append(str(target / json_path.name))
        result["copy"] = {"ok": True, "files": copied, "folder": str(target)}

    return result


def list_output_files(kind: str = "pdf", limit: int = 80) -> list[dict[str, Any]]:
    root = pdf_root() if kind == "pdf" else web_root() if kind == "web" else archive_root()
    if not root.is_dir():
        return []
    pattern = "*.pdf" if kind == "pdf" else "*.html" if kind == "web" else "*/report.html"
    items: list[dict[str, Any]] = []
    if kind == "archive":
        for d in sorted(root.iterdir(), reverse=True):
            if not d.is_dir():
                continue
            html = d / "report.html"
            if html.is_file():
                items.append(
                    {
                        "name": d.name,
                        "path": str(html),
                        "folder": str(d),
                        "modified": datetime.fromtimestamp(html.stat().st_mtime).isoformat(
                            timespec="seconds"
                        ),
                        "size": html.stat().st_size,
                    }
                )
            if len(items) >= limit:
                break
        return items

    files = sorted(root.rglob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    for f in files[:limit]:
        items.append(
            {
                "name": f.name,
                "path": str(f),
                "rel": str(f.relative_to(root)).replace("\\", "/"),
                "modified": datetime.fromtimestamp(f.stat().st_mtime).isoformat(
                    timespec="seconds"
                ),
                "size": f.stat().st_size,
            }
        )
    return items


def open_folder(path: str | Path | None = None, *, kind: str = "pdf") -> dict[str, Any]:
    """Open a folder in Windows Explorer (File Manager–style browse)."""
    import os
    import subprocess
    import sys

    if path:
        target = Path(str(path))
    elif kind == "web":
        target = web_root()
    elif kind == "archive":
        target = archive_root()
    else:
        target = pdf_root()
    target.mkdir(parents=True, exist_ok=True)
    if sys.platform != "win32":
        return {"ok": False, "error": "Open folder is Windows-only", "path": str(target)}
    try:
        os.startfile(str(target))  # type: ignore[attr-defined]
        return {"ok": True, "path": str(target)}
    except OSError:
        try:
            subprocess.Popen(["explorer", str(target)])
            return {"ok": True, "path": str(target)}
        except OSError as e:
            return {"ok": False, "error": str(e), "path": str(target)}
