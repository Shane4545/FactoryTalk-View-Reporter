"""
Build a blank Plant Reporter portable folder (Python + START.bat) for handoff.

Does NOT include Chalk River plant.json, cache, or archives.
Requires Python 3.11+ on the destination PC (see START_OPS_REPORTER.bat).

For a self-contained .exe kit, use package_scada_kit.py instead.

Run from apps/ops-reporter:
  python package_blank_portable.py
"""
from __future__ import annotations

import json
import shutil
import zipfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RELEASES = ROOT / "releases"
KIT_NAME = "PlantReporter_Blank"
KIT_DIR = RELEASES / KIT_NAME

# Copy these trees (skip huge/dev noise)
COPY_DIRS = ("server", "dist", "public", "tools", "service")
SKIP_DIR_NAMES = {
    "__pycache__",
    ".pytest_cache",
    "node_modules",
    "evidence",
    "releases",
    "cache",
    "archive",
    "PDF",
    "Web",
    "Trends",
}


def _blank_plant() -> dict:
    return {
        "product": "Plant Reporter",
        "version": "1.1.0",
        "plant": {
            "id": "new-plant",
            "name": "My Water Treatment Plant",
            "municipality": "",
        },
        "dlglog_path": "",
        "dlglog_candidates": [],
        "models": {"trend": "", "motors": "", "feedback": ""},
        "sites": {},
        "report_prefs": {
            "hidden_trend_tags": [],
            "hidden_motor_tags": [],
            "hidden_feedback_tags": [],
            "hidden_sections": [],
        },
        "schedule": {"enabled": False},
        "tag_config": {
            "schema_version": 2,
            "profile_name": "New plant",
            "signals": [],
            "trend": [],
            "motors": [],
            "feedback": [],
            "roles": {},
            "status": "draft",
            "revision": 0,
            "configured": False,
            "builtin": False,
        },
        "tag_config_draft": None,
        "api_port": 8787,
    }


def _copy_tree(src: Path, dest: Path) -> None:
    if not src.is_dir():
        return
    for path in src.rglob("*"):
        rel = path.relative_to(src)
        if any(part in SKIP_DIR_NAMES for part in rel.parts):
            continue
        if path.is_dir():
            (dest / rel).mkdir(parents=True, exist_ok=True)
            continue
        if path.suffix in {".pyc", ".pyo"}:
            continue
        out = dest / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, out)


def stage() -> Path:
    if KIT_DIR.exists():
        shutil.rmtree(KIT_DIR, ignore_errors=True)
    KIT_DIR.mkdir(parents=True, exist_ok=True)

    for name in COPY_DIRS:
        _copy_tree(ROOT / name, KIT_DIR / name)

    for fname in (
        "START_OPS_REPORTER.bat",
        "README.md",
        "requirements.txt",
        "package.json",
    ):
        src = ROOT / fname
        if src.is_file():
            shutil.copy2(src, KIT_DIR / fname)

    for name in (
        "config",
        "cache",
        "cache/days",
        "cache/series",
        "archive",
        "PDF",
        "Web",
        "Trends",
        "Logo",
        "profiles",
        "examples",
        "logs",
    ):
        (KIT_DIR / name).mkdir(parents=True, exist_ok=True)

    (KIT_DIR / "config" / "plant.json").write_text(
        json.dumps(_blank_plant(), indent=2) + "\n",
        encoding="utf-8",
    )

    example = ROOT / "profiles" / "chalk_river_example.json"
    if example.is_file():
        shutil.copy2(example, KIT_DIR / "examples" / example.name)
        (KIT_DIR / "examples" / "README.txt").write_text(
            "Optional — Setup → Import only. Not loaded by default.\r\n",
            encoding="utf-8",
        )

    (KIT_DIR / "README_BLANK.txt").write_text(
        """Plant Reporter — BLANK portable kit
===================================

This folder has NO plant data (no Chalk River, no DLGLOG path, no tags,
no cache, no archives).

Requires: Python 3.11+ on the plant PC.

1. Copy this whole folder to the plant PC
2. Double-click START_OPS_REPORTER.bat
3. Browser → Connect → Browse DLGLOG → Plant name → Save & connect
4. Setup → Scan → map tags → Activate
5. Reports → Daily

To wipe again anytime: Connect → Default

For a single .exe with no Python install, ask for PlantReporter_SCADA.zip
""",
        encoding="utf-8",
    )

    (KIT_DIR / "START.bat").write_text(
        '@echo off\r\ncd /d "%~dp0"\r\ncall START_OPS_REPORTER.bat\r\n',
        encoding="utf-8",
    )
    return KIT_DIR


def zip_kit(kit: Path) -> Path:
    stamp = date.today().strftime("%Y%m%d")
    zip_path = RELEASES / f"{KIT_NAME}.zip"
    dated = RELEASES / f"{KIT_NAME}_{stamp}.zip"
    for path in (zip_path, dated):
        if path.exists():
            path.unlink()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in kit.rglob("*"):
            if f.is_file():
                zf.write(f, f.relative_to(kit.parent).as_posix())
    shutil.copy2(zip_path, dated)
    return dated


def main() -> int:
    # Ensure UI is built
    if not (ROOT / "dist" / "index.html").is_file():
        raise SystemExit("dist/ missing — run: npm.cmd run build")
    RELEASES.mkdir(parents=True, exist_ok=True)
    kit = stage()
    z = zip_kit(kit)
    print("DONE")
    print(f"  Folder: {kit}")
    print(f"  Zip:    {z}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
