"""
Build a SCADA-ready Plant Reporter kit:
  releases/PlantReporter_SCADA/PlantReporter.exe  (+ deps)
  releases/PlantReporter_SCADA.zip

Run from apps/ops-reporter:
  python package_scada_kit.py
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RELEASES = ROOT / "releases"
EXE_NAME = "PlantReporter"
KIT_NAME = "PlantReporter_SCADA"
KIT_DIR = RELEASES / KIT_NAME
DIST_UI = ROOT / "dist"
SERVER = ROOT / "server"


def run(cmd: list[str], cwd: Path | None = None) -> None:
    print("+", " ".join(cmd))
    r = subprocess.run(cmd, cwd=cwd or ROOT)
    if r.returncode != 0:
        raise SystemExit(r.returncode)


def build_ui() -> None:
    if not (DIST_UI / "index.html").is_file():
        run(["npm.cmd", "run", "build"])
    else:
        # Always rebuild so kit matches latest UI
        run(["npm.cmd", "run", "build"])


def build_exe() -> Path:
    py = sys.executable
    run([py, "-m", "pip", "install", "-q", "pyinstaller", "fastapi", "uvicorn[standard]"])

    work = RELEASES / "_pyi_work"
    if work.exists():
        shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True, exist_ok=True)

    # Windows PyInstaller uses ; as path separator in --add-data
    sep = ";"
    add_dist = f"{DIST_UI}{sep}dist"
    add_server = f"{SERVER}{sep}server"
    add_ct = f"{SERVER / 'ct_tables.json'}{sep}server"

    cmd = [
        py,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onedir",
        "--windowed" if False else "--console",  # keep console so operators see URL
        "--name",
        EXE_NAME,
        "--distpath",
        str(work / "dist"),
        "--workpath",
        str(work / "build"),
        "--specpath",
        str(work),
        f"--add-data={add_dist}",
        f"--add-data={add_server}",
        f"--add-data={add_ct}",
        "--paths",
        str(SERVER),
        "--hidden-import=uvicorn.logging",
        "--hidden-import=uvicorn.loops",
        "--hidden-import=uvicorn.loops.auto",
        "--hidden-import=uvicorn.protocols",
        "--hidden-import=uvicorn.protocols.http",
        "--hidden-import=uvicorn.protocols.http.auto",
        "--hidden-import=uvicorn.protocols.websockets",
        "--hidden-import=uvicorn.protocols.websockets.auto",
        "--hidden-import=uvicorn.lifespan",
        "--hidden-import=uvicorn.lifespan.on",
        "--hidden-import=uvicorn.lifespan.off",
        "--hidden-import=fastapi",
        "--hidden-import=starlette",
        "--hidden-import=anyio",
        "--hidden-import=app_paths",
        "--hidden-import=main",
        "--hidden-import=plant_settings",
        "--hidden-import=dlglog_reader",
        "--hidden-import=day_cache",
        "--hidden-import=archive",
        "--hidden-import=scheduler",
        "--hidden-import=report_jobs",
        "--hidden-import=print_util",
        "--hidden-import=pdf_export",
        "--hidden-import=output_settings",
        "--hidden-import=chalk_report_builder",
        "--hidden-import=period_rollup",
        "--hidden-import=ct_calculator",
        "--hidden-import=plant_insights",
        "--hidden-import=report_prefs",
        "--hidden-import=tag_config",
        "--hidden-import=chalk_defaults",
        "--hidden-import=generic_defaults",
        "--hidden-import=plant_wipe",
        "--hidden-import=day_notes",
        "--hidden-import=profile_v2",
        "--hidden-import=trend_export",
        "--hidden-import=branding",
        "--hidden-import=site_memory",
        "--hidden-import=ftview_tags_csv",
        "--hidden-import=model_reads",
        "--hidden-import=dlglog_fast",
        "--collect-all",
        "uvicorn",
        "--collect-all",
        "fastapi",
        "--collect-all",
        "starlette",
        "--collect-all",
        "numpy",
        str(ROOT / "scada_launcher.py"),
    ]
    run(cmd)

    built = work / "dist" / EXE_NAME
    if not (built / f"{EXE_NAME}.exe").is_file():
        raise SystemExit(f"PyInstaller did not produce exe at {built}")
    return built


def stage_kit(built: Path) -> Path:
    if KIT_DIR.exists():
        shutil.rmtree(KIT_DIR, ignore_errors=True)
    KIT_DIR.mkdir(parents=True, exist_ok=True)

    # Copy onedir output
    for item in built.iterdir():
        dest = KIT_DIR / item.name
        if item.is_dir():
            shutil.copytree(item, dest)
        else:
            shutil.copy2(item, dest)

    # Writable runtime folders — blank plant, no prior site data
    for name in ("config", "cache", "cache/days", "cache/series", "archive", "PDF", "Web", "Trends", "Logo", "profiles", "examples", "logs"):
        (KIT_DIR / name).mkdir(parents=True, exist_ok=True)

    # Optional Chalk River example — Import only; not loaded until operator chooses
    example = ROOT / "profiles" / "chalk_river_example.json"
    if example.is_file():
        shutil.copy2(example, KIT_DIR / "examples" / example.name)
        (KIT_DIR / "examples" / "README.txt").write_text(
            "Optional example profiles\r\n"
            "=========================\r\n"
            "chalk_river_example.json — Import from Setup only if you want\r\n"
            "the Chalk River Water Treatment Plant sample mapping.\r\n"
            "A blank install does NOT load this automatically.\r\n",
            encoding="utf-8",
        )

    blank_plant = {
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
    (KIT_DIR / "config" / "plant.json").write_text(
        json.dumps(blank_plant, indent=2) + "\n",
        encoding="utf-8",
    )

    # Project README (no secrets) + SCADA quick start
    readme = ROOT / "README.md"
    if readme.is_file():
        shutil.copy2(readme, KIT_DIR / "README.md")

    (KIT_DIR / "README_SCADA.txt").write_text(
        f"""Plant Reporter v1.1.0 — SCADA plant kit
======================================

1. Copy this WHOLE folder to the SCADA / HMI PC
   (example: C:\\PlantReporter\\)

2. Double-click {EXE_NAME}.exe  (or START.bat)

3. Browser opens to Connect (http://127.0.0.1:8787).
   This kit starts BLANK — no plant name, no DLGLOG, no tags, no archives.

4. Connect → Browse… → select the plant’s FactoryTalk DLGLOG folder
   (the folder that contains the datalog model subfolders)
   → enter Plant name + Township → optional logo → Save & connect

5. Setup → Scan DLGLOG tags → map instruments/motors → tick Use →
   Activate profile

6. Reports → Daily → pick a day that has DLGLOG data → Update from DLGLOG

To wipe back to blank anytime: Connect → Default
   (or Setup → Load blank template). That clears tags, disconnects DLGLOG,
   forgets remembered sites, and deletes cache/archives/PDF/Web/Trends.

Optional: examples\\chalk_river_example.json — Setup → Import only if you
want the Chalk River sample mapping (not loaded by default).

Notes
-----
- Keep the console window open while using the app.
- Config: config\\plant.json next to the .exe
- Logo: CCI until you upload a plant crest on Connect
- Localhost only: http://127.0.0.1:8787 — do not expose on the LAN
- If SmartScreen warns: More info → Run anyway

See also: PLANT_TEST_CHECKLIST.txt
""",
        encoding="utf-8",
    )

    (KIT_DIR / "PLANT_TEST_CHECKLIST.txt").write_text(
        f"""Plant Reporter v1.1.0 — SCADA plant test checklist
=================================================

Must-do
-------
[ ] Extract WHOLE kit ({EXE_NAME}.exe next to _internal/, config/)
[ ] Place on plant PC (e.g. C:\\PlantReporter\\)
[ ] Know DLGLOG root (folder that contains the data-log model folders)

Launch + Connect
----------------
[ ] {EXE_NAME}.exe → http://127.0.0.1:8787
[ ] Connect → Browse DLGLOG → Save & connect
[ ] Models show on disk

Blank template → this plant
---------------------------
[ ] Confirm Connect shows no DLGLOG path / blank plant name
[ ] Connect → Browse DLGLOG → Save & connect
[ ] Setup → Scan DLGLOG tags
[ ] Map instruments / motors / feedback, set sections, tick Use
[ ] Activate profile
[ ] Reports → Daily → known good day → Update from DLGLOG
[ ] Compare to PLC Daily for the same date

Revert
------
[ ] Connect → Default to wipe back to blank (clears cache + archives too)
[ ] Export profile from Setup first if you need a backup

Smoke
-----
[ ] Weekly / Monthly open
[ ] Trends load a tag
[ ] Insights opens
[ ] Archive Save to archive for one day
""",
        encoding="utf-8",
    )

    # Convenience shortcut bat (same folder)
    (KIT_DIR / "START.bat").write_text(
        f'@echo off\r\ncd /d "%~dp0"\r\nstart "" {EXE_NAME}.exe\r\n',
        encoding="utf-8",
    )
    return KIT_DIR


def _remove_legacy_opsreporter_artifacts() -> None:
    """Drop old OpsReporter-named kits so Plant Reporter is the only handoff."""
    for pattern in ("OpsReporter_SCADA*", "OpsReporter.exe"):
        for p in RELEASES.glob(pattern):
            try:
                if p.is_dir():
                    shutil.rmtree(p, ignore_errors=True)
                elif p.is_file():
                    p.unlink(missing_ok=True)
            except OSError:
                pass


def zip_kit(kit: Path) -> Path:
    from datetime import date

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
    return dated  # prefer dated path as primary handoff


def main() -> int:
    RELEASES.mkdir(parents=True, exist_ok=True)
    print("Building UI…")
    build_ui()
    print(f"Building {EXE_NAME}.exe…")
    built = build_exe()
    print("Staging kit…")
    kit = stage_kit(built)
    print("Removing legacy OpsReporter kit names…")
    _remove_legacy_opsreporter_artifacts()
    print("Zipping…")
    z = zip_kit(kit)
    print()
    print("DONE")
    print(f"  Folder: {kit}")
    print(f"  Zip:    {z}")
    print(f"  Copy the zip to the SCADA PC, extract, run {EXE_NAME}.exe")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
